from dataclasses import replace

import numpy as np
import pytest
from scipy.special import jv

from airsim_rf.research.doppler_basis_cuda import CudaDopplerBasisRenderer, temporal_coefficients
from airsim_rf.research.doppler_basis import DopplerBasisRenderer, doppler_degree
from airsim_rf.batched_rendering import BatchedPathRenderer, PathRenderJob
from airsim_rf.sampled_waveform import SampledWaveform


@pytest.mark.parametrize('doppler', [0., 2500., 25000.])
def test_fft_chebyshev_coefficients_against_bessel_and_phase(doppler):
    duration = 2047/2e6
    degree, _ = doppler_degree(doppler, duration, 5e-11)
    z = np.linspace(-np.pi*doppler*duration, np.pi*doppler*duration, 13)
    coeff = temporal_coefficients(np, z, degree)
    q = np.arange(degree+1)
    expected = jv(q[None, :], z[:, None])*np.where(q == 0, 1, 2)*(1j**q)
    np.testing.assert_allclose(coeff, expected, atol=3e-13, rtol=1e-11)
    u = np.linspace(-1, 1, 100)
    actual = np.polynomial.chebyshev.chebvander(u, degree) @ coeff.T
    np.testing.assert_allclose(actual, np.exp(1j*u[:, None]*z), atol=1e-10, rtol=0)


def gpu():
    try:
        import cupy as cp
        if cp.cuda.runtime.getDeviceCount() == 0:
            pytest.skip('No CUDA device')
    except Exception as exc:
        pytest.skip(f'CuPy CUDA unavailable: {exc}')


def test_pascal_kernels_compile_without_claiming_gpu_execution():
    try:
        import cupy as cp
        cp.cuda.nvrtc.getVersion()
    except Exception as exc:
        pytest.skip(f'CUDA 12 NVRTC unavailable: {exc}')
    from airsim_rf.research.doppler_basis_cuda import _PROJECT, _PROJECT_WARP, _RECONSTRUCT
    for name,source in [('projection',_PROJECT),('projection_warp',_PROJECT_WARP),('reconstruction',_RECONSTRUCT)]:
        program=cp.cuda.nvrtc.createProgram(source,name+'.cu',(),())
        try:
            cp.cuda.nvrtc.compileProgram(program,('--gpu-architecture=compute_60','--std=c++11'))
        except Exception:
            pytest.fail(cp.cuda.nvrtc.getProgramLog(program))
        finally:
            cp.cuda.nvrtc.destroyProgram(program)


@pytest.mark.parametrize('projection', ['gather', 'warp', 'dense'])
def test_real_cuda_high_rank_projection(projection):
    gpu()
    jobs = [replace(linked(42, 103), doppler_hz=linked(42, 103).doppler_hz*10), linked(53, 8)]
    cfg = dict(sample_rate_hz=2e6, max_delay_s=100e-6, max_doppler_hz=25000, block_samples=512)
    engine = CudaDopplerBasisRenderer(**cfg, projection=projection)
    actual = engine.render(jobs, num_samples=1025)
    expected = DopplerBasisRenderer(**cfg).render(jobs, num_samples=1025)
    assert max(b['degree'] for b in engine.last_metrics['blocks']) >= 32
    np.testing.assert_allclose(actual, expected, atol=2e-9, rtol=2e-9)


def linked(seed=42, paths=64, taps=32):
    rng = np.random.default_rng(seed)
    source = SampledWaveform(rng.normal(size=3000)+1j*rng.normal(size=3000), 2e6,
                             reference_time_ns=-200000, interpolation_taps=taps)
    delays = rng.uniform(0, 100e-6, paths)
    delays[:3] = [0., 100e-6, 20e-6]
    return PathRenderJob((rng.normal(size=paths)+1j*rng.normal(size=paths))/np.sqrt(paths),
                         delays, rng.uniform(-2500, 2500, paths), source,
                         frequency_offset_hz=12000., phase_offset_rad=.27)


@pytest.mark.parametrize('batch_links', [1, 3])
@pytest.mark.parametrize('projection', ['gather', 'warp', 'dense'])
def test_real_cuda_private_jobs_all_paths_and_new_data(batch_links, projection):
    gpu()
    jobs = [linked(42, 64), linked(53, 103), linked(7, 8, taps=16), linked(11, 19)]
    engine = CudaDopplerBasisRenderer(sample_rate_hz=2e6, max_delay_s=100e-6,
                                      max_doppler_hz=2500, block_samples=256, batch_links=batch_links,
                                      projection=projection)
    kw = dict(num_samples=1025, channel_epoch_ns=-123000)
    output = engine.render(jobs, profile=True, **kw)
    reference = BatchedPathRenderer(backend='llvm').render(jobs, sample_rate_hz=2e6, **kw)
    np.testing.assert_allclose(output, reference, atol=2e-9, rtol=2e-9)
    assert any(e['name'] == 'basis.path_projection' and e['cuda_ms'] > 0 for e in engine.last_metrics['events'])
    np.testing.assert_allclose(engine.render(jobs, sum_output=True, **kw), reference.sum(axis=0), atol=2e-9, rtol=2e-9)
    changed = [linked(92, 64), linked(83, 103), linked(37, 8, taps=16), linked(61, 19)]
    actual = engine.render(changed, **kw)
    expected = DopplerBasisRenderer(sample_rate_hz=2e6, max_delay_s=100e-6, max_doppler_hz=2500).render(changed, **kw)
    np.testing.assert_allclose(actual, expected, atol=2e-9, rtol=2e-9)


@pytest.mark.parametrize('offset', [12000., 12000.1234567, -12000.125])
@pytest.mark.parametrize('projection', ['gather', 'warp', 'dense'])
def test_real_cuda_split_unix_epoch_cancellation_and_boundaries(offset, projection):
    gpu()
    epoch = 1790000000000000000
    source = replace(linked().waveform, reference_time_ns=epoch-200000)
    job = PathRenderJob(np.array([1., -1.]), np.array([30e-6, 30e-6]),
                        np.array([2500., -2500.]), source, frequency_offset_hz=offset)
    engine = CudaDopplerBasisRenderer(sample_rate_hz=2e6, max_delay_s=100e-6, max_doppler_hz=2500,
                                      projection=projection)
    full = engine.render([job], num_samples=1025, sim_time_ns=epoch, channel_epoch_ns=epoch)
    left = engine.render([job], num_samples=137, sim_time_ns=epoch, channel_epoch_ns=epoch)
    right = engine.render([job], num_samples=888, sim_time_ns=epoch+68500, channel_epoch_ns=epoch)
    np.testing.assert_allclose(np.c_[left, right], full, atol=2e-9, rtol=2e-9)
    reference = BatchedPathRenderer(backend='llvm').render([job], sample_rate_hz=2e6,
                    num_samples=1025, sim_time_ns=epoch, channel_epoch_ns=epoch)
    np.testing.assert_allclose(full, reference, atol=2e-9, rtol=2e-9)
    with pytest.raises(ValueError, match='equal sample clocks'):
        engine.render([replace(job, time_scale=1.00002)], num_samples=128, sim_time_ns=epoch)
    finite = SampledWaveform(np.array([2.+1j, 0., 0.]), 2e6, boundary='zero')
    impulse = PathRenderJob(np.array([1.+0j]), np.array([0.]), np.array([0.]), finite)
    out = engine.render([impulse], num_samples=128)[0]
    np.testing.assert_allclose(out, np.r_[2.+1j, np.zeros(127)], atol=1e-12)
