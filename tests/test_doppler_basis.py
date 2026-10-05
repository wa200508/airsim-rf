import numpy as np
import pytest

from airsim_rf.batched_rendering import BatchedPathRenderer, PathRenderJob
from airsim_rf.sampled_waveform import SampledWaveform
from airsim_rf.research.doppler_basis import DopplerBasisRenderer, doppler_degree


def job(seed=12, paths=64, taps=32, boundary='error'):
    rng = np.random.default_rng(seed)
    wave = SampledWaveform(rng.normal(size=3000)+1j*rng.normal(size=3000), 2e6, -200_000,
                           interpolation_taps=taps, boundary=boundary)
    delay = rng.uniform(0, 100e-6, paths)
    delay[:3] = [0, 100e-6, 20e-6]  # Include support and exact-grid boundaries.
    return PathRenderJob((rng.normal(size=paths)+1j*rng.normal(size=paths))/np.sqrt(paths),
                         delay, rng.uniform(-2500, 2500, paths), wave,
                         frequency_offset_hz=12000., phase_offset_rad=.37)


@pytest.mark.parametrize('taps', [8, 32, 64])
def test_basis_matches_all_path_sampled_reference_and_split_continuity(taps):
    jobs = [job(taps=taps), job(73, taps=taps)]
    engine = DopplerBasisRenderer(sample_rate_hz=2e6, max_delay_s=100e-6,
                                  max_doppler_hz=2500, block_samples=256, temporal_tolerance=1e-12)
    output = engine.render(jobs, num_samples=1025, channel_epoch_ns=-123_000)
    direct = BatchedPathRenderer().render(jobs, sample_rate_hz=2e6, num_samples=1025,
                                          channel_epoch_ns=-123_000)
    np.testing.assert_allclose(output, direct, rtol=2e-10, atol=2e-10)
    left = engine.render(jobs, num_samples=137, channel_epoch_ns=-123_000)
    right = engine.render(jobs, num_samples=888, sim_time_ns=68_500, channel_epoch_ns=-123_000)
    np.testing.assert_allclose(np.c_[left, right], output, rtol=2e-10, atol=2e-10)


def test_doppler_degree_bound_and_cancelled_equal_delay_paths():
    degree, bound = doppler_degree(2500., .0010235, 1e-12)
    assert bound <= 1e-12
    u = np.linspace(-1, 1, 113)
    for fd in [-2500, -1311., 0., 1499., 2500]:
        q = np.arange(degree+1)
        from scipy.special import jv
        c = jv(q, np.pi*fd*.0010235)*np.where(q == 0, 1, 2)*(1j**q)
        np.testing.assert_allclose(np.polynomial.chebyshev.chebval(u, c),
                                   np.exp(1j*np.pi*fd*.0010235*u), atol=bound+2e-14, rtol=0)
    source = job().waveform
    linked = PathRenderJob(np.array([1., -1.]), np.array([30e-6]*2), np.array([2500., -2500.]), source)
    engine = DopplerBasisRenderer(sample_rate_hz=2e6, max_delay_s=100e-6, max_doppler_hz=2500)
    output = engine.render([linked], num_samples=1025)[0]
    t = np.arange(1025)/2e6
    reference = source(t-30e-6)*(np.exp(2j*np.pi*2500*t)-np.exp(-2j*np.pi*2500*t))
    np.testing.assert_allclose(output, reference, atol=2e-9, rtol=2e-9)
    assert abs(output[100]) > 1e-3  # Opposing Dopplers were not averaged away.


def test_rebuild_and_private_inputs():
    engine = DopplerBasisRenderer(sample_rate_hz=2e6, max_delay_s=100e-6, max_doppler_hz=2500)
    first = engine.render([job()], num_samples=512)
    changed = engine.render([job(99)], num_samples=512)
    assert not np.allclose(first, changed)
    np.testing.assert_allclose(engine.render([job()], num_samples=512), first, atol=1e-12)
    assert engine.last_metrics['valid_paths'] == 64


@pytest.mark.parametrize('offset', [12000., 12000.1234567, -12000.125])
def test_unix_epoch_keeps_sample_phase_precision(offset):
    from dataclasses import replace
    linked = job()
    epoch = 1_790_000_000_000_000_000
    wave = replace(linked.waveform, reference_time_ns=epoch-200_000)
    linked = replace(linked, waveform=wave, frequency_offset_hz=offset)
    engine = DopplerBasisRenderer(sample_rate_hz=2e6, max_delay_s=100e-6, max_doppler_hz=2500)
    kw = dict(num_samples=1025, sim_time_ns=epoch, channel_epoch_ns=epoch-123_000)
    output = engine.render([linked], **kw)
    reference = BatchedPathRenderer().render([linked], sample_rate_hz=2e6, **kw)
    np.testing.assert_allclose(output, reference, atol=2e-9, rtol=2e-9)
    left = engine.render([linked], num_samples=137, sim_time_ns=epoch, channel_epoch_ns=epoch-123_000)
    right = engine.render([linked], num_samples=888, sim_time_ns=epoch+68_500, channel_epoch_ns=epoch-123_000)
    np.testing.assert_allclose(np.c_[left, right], output, atol=2e-9, rtol=2e-9)


def test_reject_unqualified_clock_and_channel_range():
    from dataclasses import replace
    engine = DopplerBasisRenderer(sample_rate_hz=2e6, max_delay_s=100e-6, max_doppler_hz=2500)
    with pytest.raises(ValueError, match='equal clocks'):
        engine.render([replace(job(), time_scale=1.00002)], num_samples=512)
    with pytest.raises(ValueError, match='outside declared'):
        engine.render([replace(job(), doppler_hz=np.ones(64)*2501)], num_samples=512)
    with pytest.raises(ValueError, match='align'):
        engine.render([job()], num_samples=512, sim_time_ns=1)


def test_finite_zero_buffer_has_no_circular_wraparound():
    source = SampledWaveform(np.array([2.+1j, 0., 0.]), 2e6, boundary='zero')
    linked = PathRenderJob(np.array([1.+0j]), np.array([0.]), np.array([0.]), source)
    engine = DopplerBasisRenderer(sample_rate_hz=2e6, max_delay_s=100e-6, max_doppler_hz=2500, block_samples=37)
    output = engine.render([linked], num_samples=100)[0]
    np.testing.assert_allclose(output, np.r_[2.+1j, np.zeros(99)], atol=1e-14)
