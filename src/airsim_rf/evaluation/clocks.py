"""Oracle clock correction for held-out studies, not a deployed estimator."""
import numpy as np

def align_known_receiver_clocks(iq, *, actual_rates_hz, receiver_clocks,
                                carrier_hz, nominal_rate_hz):
    """Oracle clock correction for analysis; not a clock estimator.

    Interpolate nominal-time samples with the declared 32-tap Lanczos operator,
    then remove receiver LO error using recorded truth. Edge support is excluded
    later by the CAF's common interior. Absolute phase constants do not affect
    ambiguity power.
    """
    from ..sampled_waveform import SampledWaveform
    times = np.arange(iq.shape[-1])/nominal_rate_hz
    corrected = []
    for values, rate, clock in zip(iq, actual_rates_hz, receiver_clocks):
        wave = SampledWaveform(values, rate, boundary='zero')
        offset = carrier_hz*clock['error_ppm']*1e-6
        corrected.append(wave(times)*np.exp(1j*(2*np.pi*offset*times+clock['phase_rad'])))
    return np.asarray(corrected)
