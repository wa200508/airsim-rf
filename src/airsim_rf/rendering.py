"""Bounded-memory direct path renderer with per-path narrowband Doppler.

No taps are merged or pruned. Dr.Jit executes the same recurrence kernel on
LLVM/CUDA; NumPy is an independent analytic reference. Channel coefficients
include carrier-delay phase at channel_epoch_ns. Do not add that phase twice.
"""
from dataclasses import dataclass
from numbers import Integral

import numpy as np


@dataclass(frozen=True)
class ToneWaveform:
    frequency_hz: float
    phase_rad: float = 0.0
    reference_time_ns: int = 0

    def __post_init__(self):
        _finite(self.frequency_hz, self.phase_rad)
        _epoch(self.reference_time_ns)

    def __call__(self, time_s):
        return np.exp(1j*(2*np.pi*self.frequency_hz*(np.asarray(time_s)-self.reference_time_ns*1e-9)
                         + self.phase_rad))


@dataclass(frozen=True)
class LFMChirpWaveform:
    """One unit-amplitude pulse, sweeping -B/2 to +B/2 on [0, width)."""
    bandwidth_hz: float
    pulse_width_s: float
    reference_time_ns: int = 0
    phase_rad: float = 0.0

    def __post_init__(self):
        _finite(self.bandwidth_hz, self.pulse_width_s, self.phase_rad)
        _epoch(self.reference_time_ns)
        if self.bandwidth_hz <= 0 or self.pulse_width_s <= 0:
            raise ValueError("Bandwidth and pulse width must be positive")

    def __call__(self, time_s):
        u = np.asarray(time_s)-self.reference_time_ns*1e-9
        inside = (u >= 0) & (u < self.pulse_width_s)
        u = np.where(inside, u, 0.)
        return np.where(inside, np.exp(1j*(np.pi*self.bandwidth_hz/self.pulse_width_s*u*u
                                         - np.pi*self.bandwidth_hz*u+self.phase_rad)), 0j)


def _finite(*values):
    if not all(np.isfinite(v) for v in values):
        raise ValueError("Parameters must be finite")


def _epoch(value):
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("Epoch must be integer nanoseconds")


def _oscillator_cycles(frequency_hz, time_ns):
    """Reduce absolute LO phase exactly before converting to binary64.

    Treat the supplied binary64 frequency as its exact integer ratio. Integer
    nanoseconds never pass through large floating-point seconds or cycles.
    """
    numerator, denominator = float(frequency_hz).as_integer_ratio()
    modulus = denominator * 1_000_000_000
    return ((int(time_ns) * numerator) % modulus) / modulus


def render_paths(coefficients, delays_s, doppler_hz, waveform, *, sample_rate_hz,
                 num_samples, sim_time_ns=0, channel_epoch_ns=None,
                 amplitude_scale=1., time_scale=1., frequency_offset_hz=0., phase_offset_rad=0.,
                 backend="numpy", path_tile=128, sample_tile=32,
                 accumulation="partial"):
    """Return complex128 envelope; caller supplies sqrt(R*P) voltage scaling.

    Waveform time is (physical time - path delay)*time_scale, modeling TX clock
    error. frequency_offset_hz/phase_offset_rad model the TX LO before delay.
    Doppler is referenced to channel_epoch_ns, not reset to the block boundary.
    Integer epoch subtraction precedes conversion to seconds. Geometry and
    Doppler stay fixed in a block; this is not wideband time stretching.

    CUDA requests fail if CUDA is unavailable. No implicit CPU fallback.
    Analytic tone/LFM descriptors are supported; arbitrary callbacks remain
    supported by receiver.synthesize_voltage's existing NumPy implementation.
    accumulation="local" experimentally pre-reduces within SIMD packets/CUDA
    warps, then atomically adds to the output. It avoids path/sample buffers
    but can suffer contention and nondeterministic summation rounding. The
    default "partial" keeps the original separate contribution/reduction path.
    """
    if not isinstance(waveform, (ToneWaveform, LFMChirpWaveform)):
        raise TypeError("Direct renderer requires ToneWaveform or LFMChirpWaveform")
    if backend not in ("numpy", "llvm", "cuda"):
        raise ValueError("backend must be numpy, llvm or cuda")
    if accumulation not in ("partial", "local"):
        raise ValueError("accumulation must be partial or local")
    for value in (num_samples, path_tile, sample_tile):
        if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
            raise ValueError("Sample counts and tile sizes must be positive integers")
    _finite(sample_rate_hz, amplitude_scale, time_scale, frequency_offset_hz, phase_offset_rad)
    if sample_rate_hz <= 0 or time_scale <= 0:
        raise ValueError("Sample rate and time scale must be positive")
    _epoch(sim_time_ns)
    channel_epoch_ns = sim_time_ns if channel_epoch_ns is None else channel_epoch_ns
    _epoch(channel_epoch_ns)
    a = np.asarray(coefficients, dtype=np.complex128)
    tau = np.asarray(delays_s, dtype=np.float64)
    fd = np.asarray(doppler_hz, dtype=np.float64)
    if a.ndim != 1 or tau.shape != a.shape or fd.shape != a.shape:
        raise ValueError("Expected coefficients, delays and Dopplers [paths]")
    valid = np.isfinite(tau) & (tau >= 0)
    a, tau, fd = a[valid], tau[valid], fd[valid]
    if not np.isfinite(a).all() or not np.isfinite(fd).all():
        raise ValueError("Nonfinite coefficients or Dopplers")

    # Derive local polynomial phase in double precision on the host. Large
    # absolute epochs never enter GPU phase arithmetic. LO phase is reduced
    # modulo one cycle before adding the small delayed/sample-time terms.
    epoch_s = int(sim_time_ns)*1e-9
    local_s = (int(sim_time_ns)-int(waveform.reference_time_ns))*1e-9
    u = local_s + epoch_s*(time_scale-1.) - tau*time_scale
    delta = (int(sim_time_ns)-int(channel_epoch_ns))*1e-9
    lo_phase = 2*np.pi*_oscillator_cycles(frequency_offset_hz, sim_time_ns) + phase_offset_rad
    if isinstance(waveform, ToneWaveform):
        slope = 0.
        initial_phase = 2*np.pi*np.remainder(waveform.frequency_hz*u, 1.) + waveform.phase_rad
        initial_frequency = np.full(a.size, waveform.frequency_hz*time_scale)
    else:
        slope = waveform.bandwidth_hz/waveform.pulse_width_s
        initial_phase = np.pi*slope*u*u-np.pi*waveform.bandwidth_hz*u+waveform.phase_rad
        initial_frequency = (slope*u-waveform.bandwidth_hz/2)*time_scale
    initial_phase += lo_phase - 2*np.pi*frequency_offset_hz*tau + 2*np.pi*np.remainder(fd*delta, 1.)
    phase0 = np.remainder(initial_phase, 2*np.pi)
    omega = 2*np.pi*(initial_frequency+frequency_offset_hz+fd)/sample_rate_hz
    curvature = 2*np.pi*slope*time_scale**2/sample_rate_hz**2
    gain = a*amplitude_scale
    if isinstance(waveform, LFMChirpWaveform):
        # Resolve half-open pulse gates once in sample coordinates, including
        # sub-sample delays. Snap roundoff within 1e-9 sample of an integer.
        gate_begin = np.ceil(-u*sample_rate_hz/time_scale-1e-9)
        gate_end = np.ceil((waveform.pulse_width_s-u)*sample_rate_hz/time_scale-1e-9)

    if backend == "numpy":
        n = np.arange(num_samples, dtype=np.float64)
        out = np.zeros(num_samples, dtype=np.complex128)
        for path_index, (g, p, w) in enumerate(zip(gain, phase0, omega)):
            contribution = g*np.exp(1j*(p+w*n+.5*curvature*n*n))
            if isinstance(waveform, LFMChirpWaveform):
                contribution *= (n >= gate_begin[path_index]) & (n < gate_end[path_index])
            out += contribution
        return out

    import drjit as dr
    from drjit import cuda, llvm
    kind = dr.JitBackend.CUDA if backend == "cuda" else dr.JitBackend.LLVM
    if not dr.has_backend(kind):
        raise RuntimeError(f"Requested {backend} backend unavailable; no CPU fallback")
    types = cuda if backend == "cuda" else llvm
    Float, UInt = types.Float64, types.UInt
    out_r, out_i = dr.zeros(Float, num_samples), dr.zeros(Float, num_samples)
    time_tiles = (num_samples+sample_tile-1)//sample_tile
    for begin in range(0, a.size, path_tile):
        end = min(begin+path_tile, a.size)
        count = end-begin
        rot_s, rot_c = dr.sincos(dr.full(Float, curvature, count*time_tiles))
        lane = dr.arange(UInt, count*time_tiles)
        path = lane % count
        base = (lane // count)*sample_tile
        p = dr.gather(Float, Float(phase0[begin:end]), path)
        w = dr.gather(Float, Float(omega[begin:end]), path)
        g_r = dr.gather(Float, Float(gain[begin:end].real), path)
        g_i = dr.gather(Float, Float(gain[begin:end].imag), path)
        if isinstance(waveform, LFMChirpWaveform):
            first_sample = dr.gather(Float, Float(gate_begin[begin:end]), path)
            last_sample = dr.gather(Float, Float(gate_end[begin:end]), path)
        n0 = Float(base)
        s, c = dr.sincos(p+w*n0+.5*curvature*n0*n0)
        step_s, step_c = dr.sincos(w+curvature*(n0+.5))
        # Local reduction keeps the same paths and recurrence, but combines
        # neighboring lane values before updating the output. Each link owns
        # its output; no transmitter data or buffers are shared across calls.
        partial_r = dr.zeros(Float, count*num_samples) if accumulation == "partial" else out_r
        partial_i = dr.zeros(Float, count*num_samples) if accumulation == "partial" else out_i

        def body(k, c, s, dc, ds, real, imag):
            n = base+k
            active = n < num_samples
            if isinstance(waveform, LFMChirpWaveform):
                active &= (Float(n) >= first_sample) & (Float(n) < last_sample)
            if accumulation == "partial":
                dr.scatter(real, g_r*c-g_i*s, n*count+path, active)
                dr.scatter(imag, g_r*s+g_i*c, n*count+path, active)
            else:
                dr.scatter_reduce(dr.ReduceOp.Add, real, g_r*c-g_i*s, n, active,
                                  mode=dr.ReduceMode.Local)
                dr.scatter_reduce(dr.ReduceOp.Add, imag, g_r*s+g_i*c, n, active,
                                  mode=dr.ReduceMode.Local)
            return k+1, c*dc-s*ds, s*dc+c*ds, dc*rot_c-ds*rot_s, ds*rot_c+dc*rot_s, real, imag

        _, _, _, _, _, partial_r, partial_i = dr.while_loop(
            (UInt(0), c, s, step_c, step_s, partial_r, partial_i),
            lambda k, *state: k < sample_tile, body, mode="symbolic",
            label="rf_direct_path_recurrence")
        if accumulation == "partial":
            out_r += dr.block_sum(partial_r, count)
            out_i += dr.block_sum(partial_i, count)
        else:
            out_r, out_i = partial_r, partial_i
        dr.eval(out_r, out_i)  # Bound pending graphs and temporary storage.
    # NumPy export synchronizes execution: timing includes H2D/D2H and reduction.
    return np.asarray(out_r)+1j*np.asarray(out_i)
