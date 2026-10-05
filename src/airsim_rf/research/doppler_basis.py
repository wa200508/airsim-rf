"""All-path Chebyshev Doppler expansion and private overlap-save FFT filtering.

Research implementation: equal source/output clocks only. Physical Dopplers are
not quantized or averaged. Finite Lanczos interpolation matches SampledWaveform;
the additional temporal approximation has an explicit conservative tail bound.
"""
from dataclasses import dataclass, field
from numbers import Integral
from time import perf_counter

import numpy as np
from scipy.fft import fft, ifft, next_fast_len
from scipy.sparse import csr_matrix
from scipy.special import gammaln, jv

from ..batched_rendering import PathRenderJob
from ..sampled_waveform import SampledWaveform
from ..rendering import _epoch, _oscillator_cycles


def doppler_degree(max_doppler_hz, duration_s, tolerance):
    """Bound the Chebyshev exponential tail uniformly over the declared range.

    |J_q(z)| <= (z/2)^q/q! * exp(z^2/(4*(q+1))). Starting beyond z,
    subsequent bounds decrease at least geometrically with ratio z/(2*(q+1)).
    The two-sided Chebyshev tail is bounded by 2*B_q/(1-ratio).
    """
    if not np.isfinite([max_doppler_hz, duration_s, tolerance]).all():
        raise ValueError('Finite Doppler bound, duration and tolerance required')
    if max_doppler_hz < 0 or duration_s < 0 or not 0 < tolerance < 1:
        raise ValueError('Nonnegative ranges and tolerance in (0,1) required')
    z = np.pi*max_doppler_hz*duration_s
    if z == 0:
        return 0, 0.
    q = max(1, int(np.ceil(z)))
    while q < 4096:
        ratio = z/(2*(q+1))
        log_bound = np.log(2.)+q*np.log(z/2)-gammaln(q+1)+z*z/(4*(q+1))-np.log1p(-ratio)
        if log_bound <= np.log(tolerance):
            return q-1, float(np.exp(log_bound))
        q += 1
    raise ValueError('Temporal degree exceeds research resource limit; use shorter blocks')


@dataclass
class _Link:
    job: PathRenderJob
    interpolation: csr_matrix
    min_lag: int
    max_lag: int
    source_start: int
    gains: np.ndarray
    temporal_coefficients: dict = field(default_factory=dict)


class DopplerBasisRenderer:
    """Research renderer; freshly rebuild path-dependent state per render call.

    max_delay_s and max_doppler_hz are declared qualification limits, not values
    inferred from favorable scene paths. Every supplied path contributes. Each
    job pays for its own FFT and data; no transforms are shared across jobs.
    """
    def __init__(self, *, sample_rate_hz, max_delay_s, max_doppler_hz,
                 block_samples=2048, temporal_tolerance=1e-10, fft_workers=2):
        if not np.isfinite([sample_rate_hz, max_delay_s, max_doppler_hz]).all():
            raise ValueError('Finite sample rate and channel ranges required')
        if sample_rate_hz <= 0 or min(max_delay_s, max_doppler_hz) < 0:
            raise ValueError('Positive sample rate and nonnegative channel ranges required')
        for v in (block_samples, fft_workers):
            if isinstance(v, bool) or not isinstance(v, Integral) or v < 1:
                raise ValueError('Positive integer block size and FFT workers required')
        self.fs, self.max_delay_s, self.max_doppler_hz = sample_rate_hz, max_delay_s, max_doppler_hz
        self.block_samples, self.temporal_tolerance, self.fft_workers = block_samples, temporal_tolerance, fft_workers
        self.degree, self.tail_bound = doppler_degree(max_doppler_hz, (block_samples-1)/self.fs, temporal_tolerance)
        self.last_metrics = {}

    def _prepare(self, job, sim_time_ns, num_samples):
        wave = job.waveform
        if not isinstance(wave, SampledWaveform):
            raise TypeError('Research FFT backend requires arbitrary sampled I/Q')
        if wave.sample_rate_hz != self.fs or job.time_scale != 1.:
            raise ValueError('Research FFT backend requires equal clocks; resampling is not yet qualified')
        gains = np.array(job.coefficients, dtype=np.complex128, copy=True)
        delays = np.array(job.delays_s, dtype=float, copy=True)
        fd = np.array(job.doppler_hz, dtype=float, copy=True)
        if gains.ndim != 1 or delays.shape != gains.shape or fd.shape != gains.shape:
            raise ValueError('Expected path arrays [paths]')
        if not np.isfinite(gains).all() or not np.isfinite(delays).all() or not np.isfinite(fd).all():
            raise ValueError('All supplied paths must be finite')
        if np.any(delays < 0) or np.any(delays > self.max_delay_s) or np.any(abs(fd) > self.max_doppler_hz):
            raise ValueError('Path lies outside declared delay/Doppler range')
        if not np.isfinite([job.amplitude_scale, job.frequency_offset_hz, job.phase_offset_rad]).all():
            raise ValueError('Finite amplitude and oscillator parameters required')
        source_position = (int(sim_time_ns)-int(wave.reference_time_ns))*self.fs*1e-9
        source_start = int(round(source_position))
        if abs(source_start-source_position) > 1e-7:
            raise ValueError('Output start must align with source sample grid in research backend')
        # x[n-lag] at t-delay uses exactly the finite interpolation convention
        # of SampledWaveform. The delay map is sparse: taps entries per path.
        half = wave.interpolation_taps//2
        min_lag = -half
        max_lag = int(np.ceil(self.max_delay_s*self.fs))+half
        if max_lag-min_lag+1 > 1_000_000:
            raise ValueError('Declared delay support exceeds research memory limit')
        coordinate = -delays*self.fs
        anchor = np.floor(coordinate).astype(np.int64)
        indices = anchor[:, None]+np.arange(-half+1, half+1)
        distances = coordinate[:, None]-indices
        weights = np.sinc(distances)*np.sinc(distances/half)
        weights /= weights.sum(axis=1, keepdims=True)
        lag = -indices
        interpolation = csr_matrix((weights.ravel(),
            (np.repeat(np.arange(gains.size), wave.interpolation_taps), (lag-min_lag).ravel())),
            shape=(gains.size, max_lag-min_lag+1))
        if wave.boundary == 'error' and (source_start-max_lag < 0 or source_start+num_samples-min_lag > wave.samples.size):
            raise ValueError('Insufficient private source history/lookahead for declared delay support')
        gains *= job.amplitude_scale*np.exp(1j*(job.phase_offset_rad-2*np.pi*job.frequency_offset_hz*delays))
        return _Link(job, interpolation, min_lag, max_lag, source_start, gains)

    def render(self, jobs, *, num_samples, sim_time_ns=0, channel_epoch_ns=None):
        if isinstance(num_samples, bool) or not isinstance(num_samples, Integral) or num_samples < 1:
            raise ValueError('Positive integer output count required')
        _epoch(sim_time_ns)
        channel_epoch_ns = sim_time_ns if channel_epoch_ns is None else channel_epoch_ns
        _epoch(channel_epoch_ns)
        started = perf_counter()
        links = [self._prepare(job, sim_time_ns, num_samples) for job in jobs]
        preparation_ms = (perf_counter()-started)*1000
        output = np.zeros((len(links), num_samples), dtype=np.complex128)
        construction_ms = fft_ms = 0.
        blocks = []
        for start in range(0, num_samples, self.block_samples):
            count = min(self.block_samples, num_samples-start)
            duration = (count-1)/self.fs
            # Rank uses declared Doppler, never favorable realized Dopplers.
            degree, tail = doppler_degree(self.max_doppler_hz, duration, self.temporal_tolerance)
            q = np.arange(degree+1)
            u = np.linspace(-1., 1., count) if count > 1 else np.zeros(1)
            basis = np.polynomial.chebyshev.chebvander(u, degree).T
            epoch_delta_s = (int(sim_time_ns)-int(channel_epoch_ns))*1e-9
            local_centre_s = (start+(count-1)/2)/self.fs
            multiplier = np.where(q == 0, 1., 2.)*(1j**q)
            for j, link in enumerate(links):
                tick = perf_counter()
                fd = np.asarray(link.job.doppler_hz)
                if count not in link.temporal_coefficients:
                    link.temporal_coefficients[count] = jv(q[:, None], np.pi*fd[None, :]*duration)*multiplier[:, None]
                centre_cycles = np.remainder(fd*epoch_delta_s, 1.)+fd*local_centre_s
                weights = link.temporal_coefficients[count]*(link.gains*np.exp(2j*np.pi*np.remainder(centre_cycles, 1.)))[None, :]
                # Every physical path enters every temporal coefficient.
                # No sample-expanded channel or path/sample tensor is stored.
                kernels = np.asarray(link.interpolation.T @ weights.T).T
                construction_ms += (perf_counter()-tick)*1000
                tick = perf_counter()
                wave = link.job.waveform
                lo = link.source_start+start-link.max_lag
                hi = link.source_start+start+count-link.min_lag
                private_source = np.zeros(hi-lo, dtype=np.complex128)
                clipped_lo, clipped_hi = max(0, lo), min(wave.samples.size, hi)
                if clipped_hi > clipped_lo:
                    private_source[clipped_lo-lo:clipped_hi-lo] = wave.samples[clipped_lo:clipped_hi]
                size = next_fast_len(private_source.size)
                source_fft = fft(private_source, size, workers=self.fft_workers)
                # Reuse within THIS private job's basis filters only; separate
                # transmitters/receivers never share input FFTs or input data.
                filtered = ifft(fft(kernels, size, axis=1, workers=self.fft_workers)*source_fft[None, :],
                                axis=1, workers=self.fft_workers)
                first = link.max_lag-link.min_lag
                result = np.sum(filtered[:, first:first+count]*basis, axis=0)
                # Oscillator offsets are separate from physical Doppler rank.
                oscillator_cycles = _oscillator_cycles(link.job.frequency_offset_hz, sim_time_ns)
                oscillator_cycles += link.job.frequency_offset_hz*(start+np.arange(count))/self.fs
                result *= np.exp(2j*np.pi*np.remainder(oscillator_cycles, 1.))
                output[j, start:start+count] = result
                fft_ms += (perf_counter()-tick)*1000
            blocks.append(dict(samples=count, degree=degree, temporal_tail_bound=tail))
        # Absolute temporal-only error bound for each output sample. Finite
        # interpolation error and floating-point roundoff are separate.
        bounds = [self.temporal_tolerance*np.max(abs(l.job.waveform.samples))
                  * float(np.sum(abs(l.gains)*np.asarray(abs(l.interpolation).sum(axis=1)).ravel())) for l in links]
        self.last_metrics = dict(preparation_ms=preparation_ms, channel_construction_ms=construction_ms,
                                 fft_and_reconstruction_ms=fft_ms, total_ms=(perf_counter()-started)*1000,
                                 blocks=blocks, valid_paths=sum(l.gains.size for l in links),
                                 delay_coefficients=[l.max_lag-l.min_lag+1 for l in links],
                                 temporal_only_absolute_error_bound=bounds)
        return output
