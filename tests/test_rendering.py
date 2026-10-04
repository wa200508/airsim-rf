"""Independent signal equations, coherent Doppler evolution and kernel checks."""
import numpy as np
import pytest

from airsim_rf.rendering import LFMChirpWaveform, ToneWaveform, render_paths


@pytest.fixture(autouse=True)
def require_cuda_for_cuda_cases(request):
    if getattr(request.node, 'callspec', None) and request.node.callspec.params.get('backend') == 'cuda':
        import drjit as dr
        if not dr.has_backend(dr.JitBackend.CUDA):
            pytest.skip('CUDA device unavailable')


@pytest.mark.parametrize('backend', ['numpy', 'llvm', 'cuda'])
@pytest.mark.parametrize('waveform', [ToneWaveform(12340., .3), LFMChirpWaveform(40000., .002)])
def test_paths_match_independent_analytic_equation(backend, waveform):
    if backend == 'cuda':
        import drjit as dr
        if not dr.has_backend(dr.JitBackend.CUDA):
            pytest.skip('CUDA device unavailable')
    fs, count = 200000., 537
    gains = np.array([.2+.4j, -.1j, .31, -1+2j])
    delays = np.array([0., 2.37/fs, 21.25/fs, -1.])
    dopplers = np.array([733., -1371., 23., 999.])
    start_ns, epoch_ns = 120000, 100000
    t = start_ns*1e-9+np.arange(count)/fs
    expected = sum(g*waveform(t-delay)*np.exp(2j*np.pi*fd*(t-epoch_ns*1e-9))
                   for g, delay, fd in zip(gains[:3], delays[:3], dopplers[:3]))
    actual = render_paths(gains, delays, dopplers, waveform, sample_rate_hz=fs,
                          num_samples=count, sim_time_ns=start_ns, channel_epoch_ns=epoch_ns,
                          backend=backend, path_tile=2, sample_tile=17)
    np.testing.assert_allclose(actual, expected, atol=3e-12, rtol=3e-12)


@pytest.mark.parametrize('backend', ['numpy', 'llvm', 'cuda'])
def test_distinct_dopplers_at_same_delay_remain_distinct(backend):
    fs = 100000.
    n = np.arange(1024)
    # Equal delays and opposing coefficients cancel only at the initial epoch.
    actual = render_paths([1., -1.], [0., 0.], [1000., -700.], ToneWaveform(0.),
                          sample_rate_hz=fs, num_samples=n.size, backend=backend)
    expected = np.exp(2j*np.pi*1000*n/fs)-np.exp(-2j*np.pi*700*n/fs)
    np.testing.assert_allclose(actual, expected, atol=2e-12)
    assert abs(actual[0]) < 1e-12 and np.max(abs(actual)) > 1.9


@pytest.mark.parametrize('backend', ['numpy', 'llvm', 'cuda'])
def test_large_epoch_lfm_and_doppler_do_not_reset_between_blocks(backend):
    epoch = 1790976000000000000
    fs = 1000000.
    wave = LFMChirpWaveform(300000., .002, reference_time_ns=epoch)
    kw = dict(sample_rate_hz=fs, channel_epoch_ns=epoch, backend=backend,
              path_tile=2, sample_tile=31)
    args = ([1+.2j, .3j], [1.37/fs, 10.25/fs], [1234., -300.], wave)
    whole = render_paths(*args, num_samples=1700, sim_time_ns=epoch, **kw)
    first = render_paths(*args, num_samples=731, sim_time_ns=epoch, **kw)
    second = render_paths(*args, num_samples=969, sim_time_ns=epoch+731000, **kw)
    np.testing.assert_allclose(np.concatenate([first, second]), whole, atol=2e-11, rtol=2e-11)


@pytest.mark.parametrize('backend', ['numpy', 'llvm', 'cuda'])
def test_tx_clock_and_lo_are_applied_before_fractional_delay(backend):
    fs, count, start_ns = 200000., 901, 123456789
    scale, offset, phase = 1.000013, 12000., .4
    wave = ToneWaveform(15000., .2)
    delay, fd, gain = 2.71/fs, -123., .3+.6j
    t = start_ns*1e-9+np.arange(count)/fs
    expected = gain*wave((t-delay)*scale)*np.exp(1j*(2*np.pi*offset*(t-delay)+phase))
    expected *= np.exp(2j*np.pi*fd*np.arange(count)/fs)
    actual = render_paths([gain], [delay], [fd], wave, sample_rate_hz=fs,
                          num_samples=count, sim_time_ns=start_ns, time_scale=scale,
                          frequency_offset_hz=offset, phase_offset_rad=phase, backend=backend)
    np.testing.assert_allclose(actual, expected, atol=4e-12, rtol=4e-12)


def test_empty_padding_and_invalid_inputs():
    kw = dict(sample_rate_hz=1e6, num_samples=13)
    np.testing.assert_array_equal(render_paths([np.nan], [-1.], [np.nan], ToneWaveform(0.), **kw), 0.)
    with pytest.raises(ValueError, match='Nonfinite'):
        render_paths([np.nan], [0.], [0.], ToneWaveform(0.), **kw)
    with pytest.raises(ValueError, match='paths'):
        render_paths([1.], [0.], [1., 2.], ToneWaveform(0.), **kw)
    with pytest.raises(TypeError, match='requires'):
        render_paths([1.], [0.], [0.], lambda t: t, **kw)


def test_direct_network_renderer_matches_existing_physical_frontend():
    from airsim_rf.sdr import PlutoSDRProfile, RadioClock, SDREmitter, SDRNetworkReceiver
    from test_sdr import free_space_scene
    def capture(renderer):
        scene = free_space_scene([[0, 0, 10], [0, 30, 10]], [[100, 0, 10]])
        scene.transmitters['tx0'].velocity = [10, 0, 0]
        scene.receivers['rx0'].velocity = [-3, 0, 0]
        emitters = {'tx0': SDREmitter(ToneWaveform(80000.), clock=RadioClock(10, .4)),
                    'tx1': SDREmitter(ToneWaveform(-130000.), clock=RadioClock(-7, -.8))}
        receiver = SDRNetworkReceiver(scene, emitters, PlutoSDRProfile(noise_enabled=False),
                    clocks={'rx0': RadioClock(-20, .8)}, max_depth=0, renderer=renderer)
        return receiver.capture(123456789, num_samples=513)['rx0']
    expected, actual = capture('numpy'), capture('direct-llvm')
    np.testing.assert_allclose(actual.input_iq_volts, expected.input_iq_volts, rtol=3e-7, atol=2e-10)
    for name in actual.link_power_w:
        assert actual.link_power_w[name] == pytest.approx(expected.link_power_w[name], rel=2e-7)
    assert np.max(abs(actual.adc_codes.astype(int)-expected.adc_codes.astype(int))) <= 1


def test_compact_lfm_radar_matches_reference_with_moving_target():
    from airsim_rf.radar import PointTargetRadar, PointTarget
    target = PointTarget('moving', (300, 0, 50), velocity_m_s=(5, 0, 0))
    args = dict(position_m=[0, 0, 50], velocity_m_s=[-10, 0, 0],
                sim_time_ns=1790976000000000000)
    reference = PointTargetRadar().capture([target], **args)
    direct = PointTargetRadar(renderer='direct-llvm').capture([target], **args)
    np.testing.assert_allclose(direct.block.iq_volts, reference.block.iq_volts, rtol=2e-7, atol=1e-13)
    assert direct.block.sim_time_ns == args['sim_time_ns']
    np.testing.assert_array_equal(direct.target_doppler_hz, reference.target_doppler_hz)
