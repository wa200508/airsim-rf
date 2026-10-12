"""The live-flight estimator must recover signed sub-bin Doppler from ADC codes."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('motion',Path(__file__).resolve().parents[1]/'scripts/qualify_live_motion.py')
motion=importlib.util.module_from_spec(spec);spec.loader.exec_module(motion)


@pytest.mark.parametrize('offset',[-8.7,0.,8.7])
def test_signed_sub_bin_frequency_estimate(offset):
    fs=2e6;t=np.arange(24000)/fs
    values=500*np.exp(1j*(.8+2*np.pi*(150000+offset)*t))
    codes=np.round(values.real)+1j*np.round(values.imag)
    assert abs(motion.estimate_tone_offset(codes,fs,150000)-offset)<.01


def test_phase_estimator_rejects_zero_signal():
    with pytest.raises(ValueError,match='nonzero'):
        motion.estimate_tone_offset(np.zeros(24000,dtype=complex),2e6,150000)
