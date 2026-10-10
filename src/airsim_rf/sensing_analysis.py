"""Measured-I/Q analysis with explicit normalization and ambiguity conventions."""
import numpy as np


def power_db(power, reference=None, floor_db=-60.):
    power = np.asarray(power, dtype=float)
    if np.any(power < 0) or not np.isfinite(power).all():
        raise ValueError('Power must be finite and nonnegative')
    reference = power.max() if reference is None else reference
    if not np.isfinite(reference) or reference <= 0:
        raise ValueError('A positive finite reference is required')
    return 10*np.log10(np.maximum(power/reference, 10**(floor_db/10)))


def cross_ambiguity(reference, surveillance, *, sample_rate_hz, max_lag=20,
                    padding=4, backend='numpy'):
    """C(lag,nu)=sum w[n] s[n] conj(r[n-lag]) exp(-j2pi nu n/fs).

    Common interior support and a Hann taper avoid lag-dependent overlap length.
    Power is normalized by weighted channel energies, giving coherence <=1.
    Positive lag means surveillance arrives later; positive nu means its
    frequency is higher. FFT zero-padding interpolates, not improves resolution.
    Returns lags in seconds, frequency in Hz, and dimensionless power.
    """
    r, s = np.asarray(reference), np.asarray(surveillance)
    if r.ndim != 1 or r.shape != s.shape or not np.isfinite(r).all() or not np.isfinite(s).all():
        raise ValueError('Equal finite one-dimensional receiver buffers required')
    if max_lag < 0 or 2*max_lag+4 >= len(r) or padding < 1 or sample_rate_hz <= 0:
        raise ValueError('Invalid lag, padding or sample rate')
    if backend == 'cuda':
        import cupy as xp
    elif backend == 'numpy':
        xp = np
    else:
        raise ValueError('Backend must be numpy or cuda')
    lags = np.arange(-max_lag, max_lag+1)
    n = xp.arange(max_lag, len(r)-max_lag)
    rr = xp.asarray(r, dtype=xp.complex128)[n[None, :]-xp.asarray(lags)[:, None]]
    ss = xp.asarray(s, dtype=xp.complex128)[n]
    w = xp.hanning(len(n))
    denominator = xp.sum(w*xp.abs(rr)**2, axis=1)*xp.sum(w*xp.abs(ss)**2)
    if bool(xp.any(denominator <= 0)):
        raise ValueError('Nonzero energy required in both channels')
    nfft = 1 << (padding*len(n)-1).bit_length()
    spectra = xp.fft.fftshift(xp.fft.fft(w*ss[None, :]*xp.conj(rr), n=nfft, axis=1), axes=1)
    power = xp.abs(spectra)**2/denominator[:, None]
    if backend == 'cuda':
        power = power.get()
    return lags/sample_rate_hz, np.fft.fftshift(np.fft.fftfreq(nfft, 1/sample_rate_hz)), power


def align_known_receiver_clocks(iq, *, actual_rates_hz, receiver_clocks,
                                carrier_hz, nominal_rate_hz):
    """Oracle clock correction for analysis; not a clock estimator.

    Interpolate nominal-time samples with the declared 32-tap Lanczos operator,
    then remove receiver LO error using recorded truth. Edge support is excluded
    later by the CAF's common interior. Absolute phase constants do not affect
    ambiguity power.
    """
    from .sampled_waveform import SampledWaveform
    times = np.arange(iq.shape[-1])/nominal_rate_hz
    corrected = []
    for values, rate, clock in zip(iq, actual_rates_hz, receiver_clocks):
        wave = SampledWaveform(values, rate, boundary='zero')
        offset = carrier_hz*clock['error_ppm']*1e-6
        corrected.append(wave(times)*np.exp(1j*(2*np.pi*offset*times+clock['phase_rad'])))
    return np.asarray(corrected)
