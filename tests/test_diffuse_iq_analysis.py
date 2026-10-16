"""Independent analytic reference checks, including changing/empty paths."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('diffuse_iq',Path(__file__).resolve().parents[1]/'scripts/analyze_diffuse_iq.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_cw_reference_crosses_batch_boundary():
    n=35;count=100;fs=1000.;tone=123.;start=.75;scale=2.
    tau=np.arange(n)*1e-6;fd=np.arange(n)*.1
    gains=np.exp(1j*np.arange(n))
    channel={'delay_s':tau,'doppler_hz':fd,'coefficient_real':gains.real,'coefficient_imag':gains.imag}
    t=np.arange(count)/fs
    expected=sum(scale*g*np.exp(2j*np.pi*(tone*(start+t-delay)+doppler*t))
                 for g,delay,doppler in zip(gains,tau,fd))
    np.testing.assert_allclose(module.cw_reference(channel,count,fs,tone,start,scale),expected,atol=1e-11)


def test_empty_channel_and_malformed_arrays():
    channel={k:[] for k in ('delay_s','doppler_hz','coefficient_real','coefficient_imag')}
    np.testing.assert_array_equal(module.cw_reference(channel,5,1000,123,0,1),np.zeros(5))
    channel['delay_s']=[0]
    with pytest.raises(ValueError,match='aligned'):module.cw_reference(channel,5,1000,123,0,1)
