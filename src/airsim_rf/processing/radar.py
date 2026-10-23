"""Receiver-only pulsed/FMCW range processing using waveform configuration."""
import numpy as np
from scipy.signal import correlate
C=299792458.

def range_compress(iq_volts, config):
    """Complex matched filter, normalized by pulse energy; zero lag is 0 m."""
    iq = np.asarray(iq_volts)
    if iq.ndim != 1 or iq.size != config.num_samples:
        raise ValueError("Expected one receive window with config.num_samples samples")
    template = config.template()
    result = correlate(iq, template, mode="full", method="fft")
    # Full correlation lags start at -(len(template)-1).
    result = result[template.size - 1:] / np.sum(np.abs(template)**2)
    ranges = np.arange(result.size) * C / (2 * config.sample_rate_hz)
    return ranges, result


def range_fft(iq, profile, *, zero_padding=4):
    """Positive beat range FFT, Hann window; range-Doppler coupling retained."""
    iq = np.asarray(iq)
    if iq.shape != (profile.num_samples,):
        raise ValueError("Expected one ADC chirp")
    if not isinstance(zero_padding, int) or isinstance(zero_padding, bool) or zero_padding < 1:
        raise ValueError("zero_padding must be a positive integer")
    nfft = profile.num_samples*zero_padding
    window = np.hanning(profile.num_samples)
    spectrum = np.fft.fft(iq*window, n=nfft)[:nfft//2]/window.sum()
    frequencies = np.arange(spectrum.size)*profile.sample_rate_hz/nfft
    return frequencies*C/(2*profile.slope_hz_s), spectrum
