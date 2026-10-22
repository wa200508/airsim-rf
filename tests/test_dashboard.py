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
    result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/launch_dashboard.py'),'--port','8812'],capture_output=True,text=True)
    assert result.returncode==2 and 'must be distinct' in result.stderr


def test_gimballed_camera_frames_all_radios_across_complete_orbit():
    from airsim_rf.dashboard_view import camera_frame,project_radios,relative_camera_pose
    from scipy.spatial.transform import Rotation
    receivers=[[0,-25,108],[0,25,115]]
    for angle in np.linspace(0,2*np.pi,121):
        position=np.array([250*np.cos(angle),250*np.sin(angle),220.])
        eye,rotation=camera_frame(position,receivers)
        points=project_radios(eye,rotation,[position,*receivers],960,540)
        assert np.all(points[:,2]>0)
        assert np.all((points[:,0]>80)&(points[:,0]<880))
        assert np.all((points[:,1]>40)&(points[:,1]<500))
        body=Rotation.from_euler('ZYX',[angle+.5,.1,-.1])
        q=body.as_quat();ned=position*[1,-1,-1]
        kinematics={'pose':{'position':dict(zip(('x','y','z'),ned)),
                           'orientation':dict(zip(('x','y','z','w'),q))}}
        relative=relative_camera_pose(eye,rotation,kinematics)
        np.testing.assert_allclose(body.apply(list(relative['translation'].values()))+ned,eye,atol=1e-10)
        np.testing.assert_allclose(body.as_matrix()@Rotation.from_quat(list(relative['rotation'].values())).as_matrix(),rotation,atol=1e-10)


def test_chase_camera_queues_pose_while_simulation_is_paused():
    from airsim_rf.dashboard_view import queue_chase_camera_pose,relative_camera_pose
    position=np.array([250.,0.,200.]);receivers=[[0,-25,108],[0,25,115]]
    kinematics={'pose':{'position':{'x':250.,'y':0.,'z':-200.},
                        'orientation':{'x':0.,'y':0.,'z':0.,'w':1.}}}
    class PausedCamera:
        pending=None
        def set_camera_pose(self,name,pose,wait_for_pose_update=True):
            assert name=='Chase'
            self.pending=pose
            # The stepping owner cannot advance Unreal until this RPC returns.
            return not wait_for_pose_update
    drone=PausedCamera()
    eye,rotation=queue_chase_camera_pose(drone,position,receivers,kinematics)
    assert drone.pending==relative_camera_pose(eye,rotation,kinematics)
    assert np.isfinite(eye).all() and np.isfinite(rotation).all()


def test_rejected_camera_pose_is_not_mistaken_for_readiness():
    from types import SimpleNamespace
    from airsim_rf.dashboard_view import queue_chase_camera_pose
    kinematics={'pose':{'position':{'x':250.,'y':0.,'z':-200.},
                        'orientation':{'x':0.,'y':0.,'z':0.,'w':1.}}}
    drone=SimpleNamespace(set_camera_pose=lambda *a,**kw:False)
    with pytest.raises(RuntimeError,match='pose request was rejected'):
        queue_chase_camera_pose(drone,[250,0,200],[[0,-25,108],[0,25,115]],kinematics)


def test_prepared_scene_reuses_demo_terrain_and_explicit_camera_gimbal(tmp_path):
    pytest.importorskip('commentjson')
    import json
    from airsim_rf.dashboard_scenario import prepare,ALTITUDE
    from airsim_rf.terrain import demo_terrain,TerrainGrid
    from airsim_rf.geometry import read_bundle
    prepare(tmp_path,Path('.deps/ProjectAirSim-runtime'))
    document,_,_=read_bundle(tmp_path/'bundle')
    original=demo_terrain();expected=TerrainGrid(original.x_m*4,original.y_m*4,100+original.heights_m*3)
    vertices,faces=expected.mesh()
    assert len(document['objects'])==1
    np.testing.assert_allclose(document['objects'][0]['vertices_local'],vertices*[1,-1,-1])
    np.testing.assert_array_equal(document['objects'][0]['faces'],faces)
    robot=json.loads((tmp_path/'sim_config/orbit.jsonc').read_text())
    assert not any(robot['sensors'][0]['gimbal'].values())
    assert ALTITUDE>expected.heights_m.max()


def test_preparation_reuses_run_directory_and_recovers_partial_bundle(tmp_path):
    pytest.importorskip('commentjson')
    from airsim_rf.dashboard_scenario import prepare
    from airsim_rf.geometry import read_bundle
    source=Path('.deps/ProjectAirSim-runtime')
    prepare(tmp_path,source)
    _,first,_=read_bundle(tmp_path/'bundle')
    recording=tmp_path/'recorded.iq';recording.write_bytes(b'keep recorded data')
    prepare(tmp_path,source)
    _,second,_=read_bundle(tmp_path/'bundle')
    assert first['scene_sha256']==second['scene_sha256']
    # Simulate an interrupted old export, with its completion marker missing.
    (tmp_path/'bundle/manifest.json').unlink()
    prepare(tmp_path,source)
    _,third,_=read_bundle(tmp_path/'bundle')
    assert third['scene_sha256']==first['scene_sha256']
    assert recording.read_bytes()==b'keep recorded data'
    assert not list(tmp_path.glob('.prepare-*'))


def test_failed_geometry_export_preserves_previous_bundle(tmp_path,monkeypatch):
    pytest.importorskip('commentjson')
    from airsim_rf.dashboard_scenario import prepare
    from airsim_rf import geometry
    prepare(tmp_path,Path('.deps/ProjectAirSim-runtime'))
    previous=(tmp_path/'bundle/manifest.json').read_bytes()
    def fail(*args,**kwargs):raise OSError('Simulated interrupted export')
    monkeypatch.setattr(geometry,'export_sionna_geometry',fail)
    with pytest.raises(OSError,match='interrupted export'):
        prepare(tmp_path,Path('.deps/ProjectAirSim-runtime'))
    assert (tmp_path/'bundle/manifest.json').read_bytes()==previous


def test_skill_keeps_diagnostics_for_a_delayed_camera_epoch(tmp_path):
    pytest.importorskip('doa_py')
    import json
    from airsim_rf.dashboard_skill import Skill
    arrays={'schema_version':1,'sample_rate_hz':FS,'carrier_hz':915e6,'sites':[
        {'id':str(i),'channels':[f's{i}e{j}' for j in range(4)],'center_rf_m':[0,i*20,110],'yaw_rad':0,
         'element_offsets_m':(np.arange(4)*299792458./915e6/2).tolist(),'calibration_complex':[[1,0]]*4} for i in range(2)]}
    path=tmp_path/'arrays.json';path.write_text(json.dumps(arrays));skill=Skill(path)
    def blocks(epoch,frequency):
        rng=np.random.default_rng(42);t=np.arange(4096)/FS
        return {n:StreamIQBlock(n,(.001*np.exp(2j*np.pi*frequency*t)+1e-6*(rng.normal(size=len(t))+1j*rng.normal(size=len(t)))).astype(np.complex64),
            0,epoch,FS,915e6,0) for site in arrays['sites'] for n in site['channels']}
    skill.process(blocks(0,10000));original=skill.snapshot(0)
    skill.process(blocks(120000000,50000));old=skill.snapshot(0)
    assert skill.snapshot()['available_epochs']==[0,120000000]
    assert old['psd']==original['psd']
    assert old['psd']!=skill.snapshot()['psd']
    assert all(row['sim_time_ns']==0 for row in old['history']+old['waterfall'])
