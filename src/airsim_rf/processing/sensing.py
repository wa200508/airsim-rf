"""Measured-I/Q power, ambiguity and waterfall operators."""
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



def received_waterfall(iq, *, sample_rate_hz, impedance_ohm=50., window_samples=512, hop_samples=128):
    """Frequency × elapsed-time PSD from one contiguous received I/Q block.

    No padding or bridging between disjoint captures. Frames are Hann-windowed
    and dated at their centers; PSD is input-referred W/Hz, two-sided.
    """
    from scipy.signal import spectrogram
    values = np.asarray(iq)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError('Finite one-dimensional I/Q required')
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0 or not np.isfinite(impedance_ohm) or impedance_ohm <= 0:
        raise ValueError('Positive finite sample rate and impedance required')
    if not 1 <= hop_samples <= window_samples <= len(values):
        raise ValueError('Window/hop must fit the contiguous capture')
    frequency, time, psd = spectrogram(values, fs=sample_rate_hz,window='hann',
        nperseg=window_samples,noverlap=window_samples-hop_samples,nfft=window_samples,
        detrend=False,return_onesided=False,scaling='density',mode='psd')
    order = np.argsort(frequency)
    return frequency[order], time, psd[order]/impedance_ohm
