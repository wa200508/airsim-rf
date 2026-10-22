"""Physical scenario, source continuity, and coherent skill ingress checks."""
from pathlib import Path
import importlib.util

import numpy as np
import pytest

from airsim_rf.dashboard_scenario import FS,orbit_pose,waveform_window
from airsim_rf.iq_stream import StreamIQBlock


def test_counter_source_preserves_identical_samples_across_windows():
    origin=1_790_000_000_000_000_000
    first,t0=waveform_window(origin,240000,origin)
    second,t1=waveform_window(origin+120_000_000,240000,origin)
    shift=round((t1-t0)*FS/1e9)
    np.testing.assert_allclose(first[shift:],second[:len(first)-shift],rtol=0,atol=1e-14)
    assert np.isfinite(first).all() and np.std(abs(first))>.1


def test_large_orbit_is_left_handed_and_closes():
    p0,v0=orbit_pose(0);p1,v1=orbit_pose(2*np.pi*250/25)
    assert p0[0]*v0[1]-p0[1]*v0[0]>0
    np.testing.assert_allclose(p0,p1,atol=1e-10)
    np.testing.assert_allclose(v0,v1,atol=1e-10)
    assert np.linalg.norm(p0[:2])==250 and np.linalg.norm(v0)==25


def test_skill_rejects_channels_with_different_simulation_epochs(tmp_path):
    pytest.importorskip('doa_py')
    import json
    from airsim_rf.dashboard_skill import Skill
    arrays={'schema_version':1,'sample_rate_hz':FS,'carrier_hz':915e6,'sites':[
        {'id':str(i),'channels':[f's{i}e{j}' for j in range(4)],'center_rf_m':[0,i*20,110],'yaw_rad':0,
         'element_offsets_m':(np.arange(4)*299792458./915e6/2).tolist(),'calibration_complex':[[1,0]]*4} for i in range(2)]}
    path=tmp_path/'arrays.json';path.write_text(json.dumps(arrays));skill=Skill(path)
    blocks={n:StreamIQBlock(n,np.ones(4096,dtype=np.complex64),0,0,FS,915e6,0) for site in arrays['sites'] for n in site['channels']}
    name='s1e3';blocks[name]=StreamIQBlock(name,np.ones(4096,dtype=np.complex64),0,120000000,FS,915e6,0)
    with pytest.raises(ValueError,match='epochs'):skill.process(blocks)
    assert skill.state['complete_windows']==0
