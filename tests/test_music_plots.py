"""Check that frequency plots preserve complex-I/Q sideband and voltage units."""
import numpy as np
import pytest

from airsim_rf.music_plots import frequency_psd


@pytest.mark.parametrize('tone_hz',[31250.,-93750.])
def test_two_sided_psd_preserves_sideband_and_integrated_voltage_power(tone_hz):
    fs=2_000_000
    samples=(3+4j)*np.exp(2j*np.pi*tone_hz*np.arange(16384)/fs)
    frequency,time,density=frequency_psd(samples,fs)
    assert frequency[np.argmax(density.mean(axis=1))]==tone_hz
    np.testing.assert_allclose(density.sum(axis=0)*(frequency[1]-frequency[0]),25.,rtol=1e-12)
    np.testing.assert_allclose(np.diff(time),2048/fs,rtol=1e-12)
