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


def test_visual_glb_has_stable_positions_and_an_orthogonal_tangent_frame():
    import json,struct
    from airsim_rf.glb_geometry import triangle_glb
    data=triangle_glb([[0,0,0],[1,0,0],[0,1,0]],[[0,1,2]],
                      base_color_rgba=[.3,.4,.2,1],emissive_rgb=[.07,.1,.04])
    size=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+size]);binary=20+size+8
    def read(index,width):
        view=doc['bufferViews'][doc['accessors'][index]['bufferView']]
        return np.frombuffer(data,dtype='<f4',count=3*width,offset=binary+view['byteOffset']).reshape(3,width)
    np.testing.assert_array_equal(read(0,3),[[0,0,0],[1,0,0],[0,0,1]])
    normal=read(1,3);tangent=read(4,4)
    np.testing.assert_allclose(np.linalg.norm(tangent[:,:3],axis=1),1)
    np.testing.assert_allclose(np.sum(normal*tangent[:,:3],axis=1),0,atol=1e-7)
    assert doc['materials'][0]['emissiveFactor']==[.07,.1,.04]


def test_skill_bind_failure_is_unhealthy(tmp_path):
    pytest.importorskip('doa_py')
    import json,socket
    from airsim_rf.dashboard_skill import Skill
    arrays={'schema_version':1,'sample_rate_hz':FS,'carrier_hz':915e6,'sites':[
        {'id':str(i),'channels':[f's{i}e{j}' for j in range(4)],'center_rf_m':[0,i*20,110],'yaw_rad':0,
         'element_offsets_m':(np.arange(4)*299792458./915e6/2).tolist(),'calibration_complex':[[1,0]]*4} for i in range(2)]}
    path=tmp_path/'arrays.json';path.write_text(json.dumps(arrays));skill=Skill(path)
    assert not skill.healthy()
    with socket.socket() as occupied:
        occupied.bind(('0.0.0.0',0));occupied.listen()
        skill.serve_stream(occupied.getsockname()[1])
    assert not skill.healthy()
    assert skill.snapshot()['status']=='failed'
    assert skill.snapshot()['error']


def test_launcher_rejects_port_collisions_before_starting_processes():
    import subprocess,sys
    result=subprocess.run([sys.executable,'scripts/launch_dashboard.py','--port','8812'],capture_output=True,text=True)
    assert result.returncode==2 and 'must be distinct' in result.stderr
