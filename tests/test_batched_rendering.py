"""Independent signal equations, changing runtime data and receiver equivalence."""
import numpy as np
import pytest

from airsim_rf.batched_rendering import BatchedPathRenderer, PathRenderJob
from airsim_rf.rendering import ToneWaveform, LFMChirpWaveform
from airsim_rf.sampled_waveform import SampledWaveform


def renderer(backend, **kw):
    import drjit as dr
    if backend == 'cuda' and not dr.has_backend(dr.JitBackend.CUDA):
        pytest.skip('CUDA device unavailable')
    return BatchedPathRenderer(backend=backend, **kw)


def equation(job, fs, samples, epoch, channel):
    t = np.arange(samples)/fs+epoch*1e-9
    return sum((job.amplitude_scale*g*job.waveform((t-delay)*job.time_scale)
                * np.exp(1j*(2*np.pi*job.frequency_offset_hz*(t-delay)+job.phase_offset_rad))
                * np.exp(2j*np.pi*fd*(t-channel*1e-9))
                for g, delay, fd in zip(job.coefficients, job.delays_s, job.doppler_hz)
                if np.isfinite(delay) and delay >= 0), start=np.zeros(samples, complex))


@pytest.mark.parametrize('backend', ['llvm', 'cuda'])
@pytest.mark.parametrize('replay', [True, False])
@pytest.mark.parametrize('sample_tile', [17, 128])
@pytest.mark.parametrize('reduction', ['auto', 'local'])
def test_bounded_private_jobs_match_equations_when_runtime_values_change(backend, replay, sample_tile, reduction):
    fs, samples = 200000., 537
    # Two jobs per group and small path tiles force both levels of batching.
    engine = renderer(backend, path_tile=4, sample_tile=sample_tile,
                      max_lanes=4*((samples+sample_tile-1)//sample_tile)*2, replay=replay, reduction=reduction)
    rng = np.random.default_rng(123)
    for update in range(3):
        jobs = []
        for j, count in enumerate((3+update, 9, 0, 6)):
            gain = rng.normal(size=count)+1j*rng.normal(size=count)
            delay = rng.uniform(0, 50/fs, count)
            fd = rng.uniform(-5000, 5000, count)
            wave = ToneWaveform(12000+update*1000, .4) if j % 2 else LFMChirpWaveform(40000+update*2000, .002, phase_rad=.1)
            jobs.append(PathRenderJob(gain, delay, fd, wave, .7, 1.000013, 1200+update*100, .3))
        epoch, channel = 123456+update*100000, 100000
        expected = np.array([equation(j, fs, samples, epoch, channel) for j in jobs])
        actual = engine.render(jobs, sample_rate_hz=fs, num_samples=samples,
                               sim_time_ns=epoch, channel_epoch_ns=channel)
        np.testing.assert_allclose(actual, expected, atol=5e-11, rtol=5e-11)
        np.testing.assert_array_equal(actual[2], 0)
        assert engine.last_metrics['retained_paths'] == sum(len(j.coefficients) for j in jobs)
        assert all(g['lanes'] <= engine.max_lanes for g in engine.last_metrics['groups'])


@pytest.mark.parametrize('backend', ['llvm', 'cuda'])
def test_replay_padding_and_overflow_preserve_all_paths(backend):
    engine = renderer(backend, path_tile=4, sample_tile=7)
    for count in (3, 4, 3, 5, 9, 0):
        job = PathRenderJob(np.ones(count), np.zeros(count), np.zeros(count), ToneWaveform(0))
        actual = engine.render([job], sample_rate_hz=1e6, num_samples=31)
        np.testing.assert_allclose(actual, count, atol=1e-13)
        assert engine.last_metrics['retained_paths'] == count
        if count:
            assert engine.last_metrics['groups'][0]['capacity_paths_per_job'] >= count
    # Return to an existing capacity with new values; recorded execution must
    # not retain gains or padding from an earlier call.
    job = PathRenderJob(np.array([2j, -1, .7]), np.zeros(3), np.zeros(3), ToneWaveform(0))
    np.testing.assert_allclose(engine.render([job], sample_rate_hz=1e6, num_samples=31), 2j-.3, atol=1e-13)
    assert engine.last_metrics['recordings_added'] == 0


@pytest.mark.parametrize('backend', ['llvm', 'cuda'])
def test_device_sum_cancellation_and_distinct_dopplers(backend):
    fs, samples = 100000., 901
    engine = renderer(backend, path_tile=2, sample_tile=31, max_lanes=2*30*2)
    jobs = [PathRenderJob(np.array([g]), np.array([2.71/fs]), np.array([fd]), ToneWaveform(14000))
            for g, fd in ((1+.2j, 1300), (-1-.2j, 1300), (.5, -700), (-.5, 123))]
    expected = sum(equation(j, fs, samples, 0, 0) for j in jobs)
    actual = engine.render(jobs, sample_rate_hz=fs, num_samples=samples, sum_output=True)
    np.testing.assert_allclose(actual, expected, atol=1e-11, rtol=1e-11)
    assert engine.last_metrics['sum_output'] is True


@pytest.mark.parametrize('backend', ['llvm', 'cuda'])
def test_large_epoch_and_changed_block_lengths_preserve_phase(backend):
    epoch, fs = 1790976000000000000, 1e6
    job = PathRenderJob(np.array([1+.2j, .3j]), np.array([1.37/fs, 10.25/fs]),
                        np.array([1234., -300.]), LFMChirpWaveform(300000., .002, reference_time_ns=epoch))
    engine = renderer(backend, path_tile=2, sample_tile=31)
    kw = dict(sample_rate_hz=fs, channel_epoch_ns=epoch)
    whole = engine.render([job], num_samples=1700, sim_time_ns=epoch, **kw)[0]
    first = engine.render([job], num_samples=731, sim_time_ns=epoch, **kw)[0]
    second = engine.render([job], num_samples=969, sim_time_ns=epoch+731000, **kw)[0]
    np.testing.assert_allclose(np.r_[first, second], whole, atol=3e-11, rtol=3e-11)


@pytest.mark.parametrize('diagnostics', [True, False])
def test_complete_sdr_frontend_matches_independent_link_renderer(diagnostics):
    from airsim_rf.sdr import PlutoSDRProfile, RadioClock, SDREmitter, SDRNetworkReceiver
    from test_sdr import free_space_scene
    def capture(mode):
        scene = free_space_scene([[0, 0, 10], [0, 30, 10]], [[100, 0, 10], [150, 10, 20]])
        scene.transmitters['tx0'].velocity = [10, 0, 0]
        scene.receivers['rx0'].velocity = [-3, 0, 0]
        emitters = {'tx0': SDREmitter(ToneWaveform(80000), clock=RadioClock(10, .4)),
                    'tx1': SDREmitter(ToneWaveform(-130000), clock=RadioClock(-7, -.8))}
        receiver = SDRNetworkReceiver(scene, emitters, PlutoSDRProfile(),
            clocks={'rx0': RadioClock(-20, .8), 'rx1': RadioClock(10, .5)},
            max_depth=0, renderer=mode, link_diagnostics=diagnostics)
        return receiver.capture(123456789, num_samples=513)
    expected, actual = capture('direct-llvm'), capture('batched-llvm')
    for name, reference in expected.items():
        result = actual[name]
        np.testing.assert_allclose(result.input_iq_volts, reference.input_iq_volts, atol=1e-11, rtol=1e-8)
        assert np.max(abs(result.adc_codes.astype(int)-reference.adc_codes.astype(int))) <= 1
        assert result.retained_paths == reference.retained_paths
        if diagnostics:
            for tx in result.link_power_w:
                assert result.link_power_w[tx] == pytest.approx(reference.link_power_w[tx], rel=1e-8)
        else:
            assert result.link_power_w == {}


@pytest.mark.parametrize('backend', ['llvm', 'cuda'])
def test_arbitrary_private_inputs_fractional_delays_clock_resampling_and_replay(backend):
    rng = np.random.default_rng(18)
    fs, samples = 1e6, 257
    engine = renderer(backend, path_tile=4, sample_tile=17)
    for update in range(2):
        jobs = []
        for j, taps in enumerate((8, 16)):
            data = rng.normal(size=700)+1j*rng.normal(size=700)
            wave = SampledWaveform(data, fs*(1+j*.01), -128000, taps)
            assert not np.shares_memory(data, wave.samples)
            job = PathRenderJob(np.array([1+.2j, -.3j, .1]), np.array([1.3, 4.7, 31.21])/fs,
                                np.array([2500., -3100., 123.]), wave,
                                time_scale=1.000019, frequency_offset_hz=4300., phase_offset_rad=.3)
            jobs.append(job)
        actual = engine.render(jobs, sample_rate_hz=fs, num_samples=samples, sim_time_ns=30000,
                               channel_epoch_ns=10000)
        expected = np.array([equation(j, fs, samples, 30000, 10000) for j in jobs])
        np.testing.assert_allclose(actual, expected, atol=2e-10, rtol=2e-10)
        if update:
            assert engine.last_metrics['recordings_added'] == 0


@pytest.mark.parametrize('backend', ['llvm', 'cuda'])
def test_finite_input_never_reads_another_jobs_buffer(backend):
    engine = renderer(backend, path_tile=2, sample_tile=7)
    first = SampledWaveform(np.ones(8), 1e6, boundary='zero', interpolation_taps=8)
    second = SampledWaveform(np.full(8, 1e9j), 1e6, boundary='zero', interpolation_taps=8)
    jobs = [PathRenderJob(np.array([1.]), np.array([0.]), np.array([0.]), w) for w in (first, second)]
    actual = engine.render(jobs, sample_rate_hz=1e6, num_samples=32)
    expected = np.array([j.waveform(np.arange(32)/1e6) for j in jobs])
    np.testing.assert_allclose(actual, expected, atol=1e-6, rtol=1e-12)
    np.testing.assert_array_equal(actual[:, 16:], 0)
    # Far-outside coordinates must become zero, not wrap signed indices.
    actual = engine.render(jobs, sample_rate_hz=1e6, num_samples=32, sim_time_ns=10**15)
    np.testing.assert_array_equal(actual, 0)


def test_sampled_input_history_is_required_and_interpolation_matches_fourier_signal():
    fs, samples, guard = 1e6, 256, 128
    rng = np.random.default_rng(28)
    frequency = np.array([-230000., -112312., -40000., 81234., 230000.])
    amplitude = rng.normal(size=5)+1j*rng.normal(size=5)
    source_times = (np.arange(samples+2*guard)-guard)/fs
    source = np.sum(amplitude[:, None]*np.exp(2j*np.pi*frequency[:, None]*source_times), axis=0)
    wave = SampledWaveform(source, fs, -guard*1000, 64)
    job = PathRenderJob(np.array([1+.2j, .3j]), np.array([1.3, 31.7])/fs,
                        np.array([2531., -1700.]), wave)
    t = np.arange(samples)/fs
    expected = sum(g*np.sum(amplitude[:, None]*np.exp(2j*np.pi*frequency[:, None]*(t-delay)), axis=0)
                   * np.exp(2j*np.pi*fd*t)
                   for g, delay, fd in zip(job.coefficients, job.delays_s, job.doppler_hz))
    actual = renderer('llvm', path_tile=2).render([job], sample_rate_hz=fs, num_samples=samples)[0]
    rms_error = np.sqrt(np.mean(abs(actual-expected)**2)/np.mean(abs(expected)**2))
    assert rms_error < 1e-4  # Qualified only for this 64-tap, <=0.23*fs case.
    short = SampledWaveform(np.ones(samples), fs)
    with pytest.raises(ValueError, match='history/lookahead'):
        renderer('llvm').render([PathRenderJob(np.ones(1), np.zeros(1), np.zeros(1), short)],
                                sample_rate_hz=fs, num_samples=samples)


@pytest.mark.parametrize('ratio', [.4, .95, 1., 1.4, 2.6])
def test_sampled_interpolation_recurrence_handles_general_rate_ratios(ratio):
    rng = np.random.default_rng(55)
    fs, samples = 1e6, 151
    wave = SampledWaveform(rng.normal(size=900)+1j*rng.normal(size=900), fs, -128000, 16)
    job = PathRenderJob(np.array([1., .3j]), np.array([0., 1.231e-6]), np.array([7300., -5100.]),
                        wave, time_scale=ratio)
    engine = renderer('llvm', path_tile=2, sample_tile=128)
    expected = equation(job, fs, samples, 0, 0)
    actual = engine.render([job], sample_rate_hz=fs, num_samples=samples)[0]
    np.testing.assert_allclose(actual, expected, atol=3e-10, rtol=3e-10)
    # Stateful blocks retain the same input history/epoch; samples stay coherent.
    first = engine.render([job], sample_rate_hz=fs, num_samples=73)[0]
    second = engine.render([job], sample_rate_hz=fs, num_samples=78, sim_time_ns=73000,
                           channel_epoch_ns=0)[0]
    np.testing.assert_allclose(np.r_[first, second], actual, atol=3e-10, rtol=3e-10)


@pytest.mark.parametrize('diagnostics', [True, False])
def test_sampled_waveforms_through_sionna_clocks_noise_filter_and_adc(diagnostics):
    from airsim_rf.sdr import PlutoSDRProfile, RadioClock, SDREmitter, SDRNetworkReceiver
    from test_sdr import free_space_scene
    rng = np.random.default_rng(91)
    emitters = {}
    for j in range(2):
        data = rng.normal(size=4096)+1j*rng.normal(size=4096)
        spectrum = np.fft.fft(data)
        spectrum[abs(np.fft.fftfreq(data.size)) > .2] = 0
        wave = SampledWaveform(np.fft.ifft(spectrum), 2e6, 123000000, 16)
        emitters[f'tx{j}'] = SDREmitter(wave, clock=RadioClock(10-j*17, .4-j),
                                      baseband_frequency_bounds_hz=(-400000, 400000))
    def capture(mode):
        scene = free_space_scene([[0, 0, 10], [0, 30, 10]], [[100, 0, 10]])
        scene.transmitters['tx0'].velocity = [10, 0, 0]
        scene.receivers['rx0'].velocity = [-3, 0, 0]
        receiver = SDRNetworkReceiver(scene, emitters, PlutoSDRProfile(),
            clocks={'rx0': RadioClock(-20, .8)}, max_depth=0, renderer=mode,
            link_diagnostics=diagnostics)
        return receiver.capture(123456789, num_samples=513)['rx0']
    expected, actual = capture('numpy'), capture('batched-llvm')
    np.testing.assert_allclose(actual.input_iq_volts, expected.input_iq_volts, rtol=3e-7, atol=1e-11)
    assert np.max(abs(actual.adc_codes.astype(int)-expected.adc_codes.astype(int))) <= 1
    assert actual.retained_paths == expected.retained_paths
