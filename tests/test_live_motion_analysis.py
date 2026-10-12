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


def test_boundary_phase_fit_detects_reset():
    spec=importlib.util.spec_from_file_location('phase',Path(__file__).resolve().parents[1]/'scripts/analyze_live_phase.py')
    phase=importlib.util.module_from_spec(spec);spec.loader.exec_module(phase)
    fs=2e6;n=24000;frequency=150008.7
    first=500*np.exp(2j*np.pi*frequency*np.arange(n)/fs)
    second=500*np.exp(1j*(2*np.pi*frequency*(np.arange(n)+n)/fs+.8))
    before=phase.phase_fit(first,fs,150000,0);after=phase.phase_fit(second,fs,150000,n)
    jump=phase.wrap(after[1]-np.polyval(before,n/fs))
    assert abs(jump-.8)<1e-8


def test_ground_image_geometry_has_distinct_radial_velocity():
    spec=importlib.util.spec_from_file_location('phase',Path(__file__).resolve().parents[1]/'scripts/analyze_live_phase.py')
    phase=importlib.util.module_from_spec(spec);spec.loader.exec_module(phase)
    def state(x,z,vx):
        return {'pose':{'position':{'x':x,'y':0,'z':z},'orientation':{'x':0,'y':0,'z':0,'w':1}},
            'twist':{'linear':{'x':vx,'y':0,'z':0},'angular':{'x':0,'y':0,'z':0}}}
    tx,rx=state(0,-2,3),state(3,-2,0)
    assert phase.geometry(tx,rx)==(3.,3.)
    distance,radial=phase.geometry(tx,rx,True)
    assert distance==5.
    assert radial==pytest.approx(1.8)


@pytest.mark.parametrize('reflection',[False,True])
def test_two_moving_robots_radial_velocity_matches_range_derivative(reflection):
    spec=importlib.util.spec_from_file_location('phase',Path(__file__).resolve().parents[1]/'scripts/analyze_live_phase.py')
    phase=importlib.util.module_from_spec(spec);spec.loader.exec_module(phase)
    def state(position,velocity,time=0.):
        return {'pose':{'position':dict(zip('xyz',np.array(position)+time*np.array(velocity))),
            'orientation':{'x':0,'y':0,'z':0,'w':1}},
            'twist':{'linear':dict(zip('xyz',velocity)),'angular':dict.fromkeys('xyz',0.)}}
    tx=([0,0,-2],[1,2,-.5]);rx=([3,4,-3],[-2,1,.2]);dt=1e-5
    _,closing=phase.geometry(state(*tx),state(*rx),reflection)
    before=phase.geometry(state(*tx,-dt),state(*rx,-dt),reflection)[0]
    after=phase.geometry(state(*tx,dt),state(*rx,dt),reflection)[0]
    assert closing==pytest.approx(-(after-before)/(2*dt),abs=1e-8)
