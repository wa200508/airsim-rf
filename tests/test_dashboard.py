"""Physical scenario, source continuity, and coherent skill ingress checks."""
from pathlib import Path
import importlib.util

import numpy as np
import pytest

from airsim_rf.dashboard_scenario import FS,orbit_pose,waveform_window
from airsim_rf.sample_stream import SampleBlock as StreamIQBlock


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
        assert np.linalg.norm(eye-position*[1,-1,-1])==pytest.approx(5.)
        target=np.mean(receivers,axis=0)*[1,-1,-1]
        np.testing.assert_allclose(rotation[:,0],(target-eye)/np.linalg.norm(target-eye))
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


def test_camera_labels_use_native_image_pose_and_hide_terrain_obstructed_anchors():
    from airsim_rf.dashboard_view import camera_frame,relative_camera_pose,camera_labels,project_radios
    from scipy.spatial.transform import Rotation
    receivers=[[0,-25,108],[0,25,115]];position=np.array([250.,0,220])
    eye,rotation=camera_frame(position,receivers)
    kinematics={'pose':{'position':dict(zip(('x','y','z'),position*[1,-1,-1])),
        'orientation':{'x':0,'y':0,'z':0,'w':1}}}
    mount=relative_camera_pose(eye,rotation,kinematics)
    # The drone and body attitude have changed since the mount was requested.
    body=Rotation.from_euler('ZYX',[.02,.01,-.01]);drone=position*[1,-1,-1]+[0,2,-1]
    actual_rotation=body.as_matrix()@rotation;actual_eye=drone+body.apply(list(mount['translation'].values()))
    q=Rotation.from_matrix(actual_rotation).as_quat()
    message={'width':960,'height':540,**dict(zip(('pos_x','pos_y','pos_z'),actual_eye)),
        **dict(zip(('rot_x','rot_y','rot_z','rot_w'),q))}
    document={'schema_version':1,'scene_id':'Labels','revision':'1',
        'source':{'adapter':'test','version':'1','asset':'wall','revision':'1','geometry_kind':'shared'},
        'materials':{'earth':{'relative_permittivity':5.,'conductivity_s_m':.01,'assumption':'Synthetic occluder'}},
        'objects':[{'id':'Terrain','material':'earth','vertices_local':[[125,5,-300],[125,20,-300],[125,20,0],[125,5,0]],
            'faces':[[0,1,2],[0,2,3]],'local_to_ned_m':np.eye(4).tolist()}]}
    labels=camera_labels(message,mount,receivers,document)
    assert {label['text'] for label in labels}=={'TX / DRONE','RX 1'}
    tx=next(label for label in labels if label['text']=='TX / DRONE')
    expected=project_radios(actual_eye,actual_rotation,[drone*[1,-1,-1]],960,540)[0]
    np.testing.assert_allclose([tx['x'],tx['y']],expected[:2],atol=1e-10)


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
    assert all(row['timestamp_ns']==0 for row in old['history']+old['waterfall'])
    assert old==original
    compact=skill.snapshot(0,compact=True)
    assert 'history' not in compact and 'waterfall' not in compact
    assert compact['psd']==original['psd'] and skill.snapshot(0)==original
    # Old waterfall rows must survive eviction from the live rolling waterfall.
    skill.state['waterfall']=[];skill.state['history']=[]
    assert skill.snapshot(0)==original
    assert skill.epoch_status(0)=={'timestamp_ns':0,'complete_windows':1}
    with pytest.raises(KeyError):skill.epoch_status(999)
    skill.state.update(status='failed',error='processing failed')
    with pytest.raises(RuntimeError,match='processing failed'):skill.epoch_status(0)


def test_skill_publishes_independent_receiver_spectra_and_waterfall_rows(tmp_path):
    pytest.importorskip('doa_py')
    import json
    from airsim_rf.skills.music import MusicSkill
    arrays={'schema_version':1,'sample_rate_hz':FS,'carrier_hz':915e6,'sites':[
        {'id':f'site{i}','channels':[f's{i}e{j}' for j in range(4)],'center_rf_m':[0,i*20,110],
         'yaw_rad':0,'element_offsets_m':(np.arange(4)*299792458./915e6/2).tolist(),
         'calibration_complex':[[1,0]]*4} for i in range(2)]}
    path=tmp_path/'arrays.json';path.write_text(json.dumps(arrays));skill=MusicSkill(path)
    rng=np.random.default_rng(77);t=np.arange(8192)/FS;blocks={}
    for site,frequency,amplitude in zip(arrays['sites'],[10000,-35000],[.001,.0002]):
        for name,offset in zip(site['channels'],site['element_offsets_m']):
            steering=np.exp(2j*np.pi*915e6/299792458.*offset*np.sin(np.deg2rad(80)))
            samples=amplitude*steering*np.exp(2j*np.pi*frequency*t)+1e-8*(rng.normal(size=len(t))+1j*rng.normal(size=len(t)))
            blocks[name]=StreamIQBlock(name,samples.astype(np.complex64),0,0,FS,915e6,0)
    skill.process(blocks);frame=skill.snapshot(0)
    for entry,site,expected in zip(frame['receiver_spectra'],arrays['sites'],[10,-35]):
        psd=entry['psd']
        assert entry['receiver']==site['channels'][0]
        assert abs(psd['frequency_khz'][np.argmax(psd['density_db_v2_hz'])]-expected)<.5
    assert frame['psd']==frame['receiver_spectra'][0]['psd']
    row=frame['waterfall'][0]
    assert row['site_psd_db']==[entry['psd']['density_db_v2_hz'] for entry in frame['receiver_spectra']]
    assert row['site_psd_db'][0]!=row['site_psd_db'][1]
    assert frame['angle_grid_deg'][0]==-180 and frame['angle_grid_deg'][-1]==180
    assert all(bearing['detected'] and abs(bearing['angle_deg']-80)<.2 for bearing in frame['bearings'])
    for curve in frame['music_db']:
        # A physical ULA has identical steering at 80° and 100°; a 360° search
        # must expose that ambiguity and remain continuous at the ±180° seam.
        assert curve[2600]==pytest.approx(curve[2800],abs=1e-5)
        assert curve[0]==pytest.approx(curve[-1],abs=1e-5)


def test_real_neutral_skill_ingress_and_stream_commit_release_flight_only_after_eight_channels(tmp_path):
    """Real source-neutral TCP -> MUSIC/PSD -> stream commit; only the flight step is stubbed."""
    pytest.importorskip('doa_py');pytest.importorskip('grpc')
    import asyncio,json,socket,subprocess,sys,time
    from types import SimpleNamespace
    from urllib.error import URLError
    from urllib.request import ProxyHandler,build_opener
    from airsim_rf.dashboard_sync import advance_after_commit
    from airsim_rf.sample_stream import SampleStreamWriter
    from airsim_rf.dashboard_recording import RecordingWriter,RecordingStore
    arrays={'schema_version':1,'sample_rate_hz':FS,'carrier_hz':915e6,'sites':[
        {'id':str(i),'channels':[f's{i}e{j}' for j in range(4)],'center_rf_m':[0,i*20,110],'yaw_rad':0,
         'element_offsets_m':(np.arange(4)*299792458./915e6/2).tolist(),'calibration_complex':[[1,0]]*4} for i in range(2)]}
    path=tmp_path/'arrays.json';path.write_text(json.dumps(arrays))
    reservations=[socket.socket() for _ in range(3)]
    for reservation in reservations:reservation.bind(('127.0.0.1',0))
    iq_port,http_port,control_port=[reservation.getsockname()[1] for reservation in reservations]
    for reservation in reservations:reservation.close()
    request=build_opener(ProxyHandler({})).open;steps=[]
    recorder=RecordingWriter(tmp_path/'replays','0123456789abcdef',{},.24,120000000,no_render=True)
    recorded=RecordingStore(tmp_path/'replays')
    class World:
        def continue_until_sim_time(self,epoch,wait_until_complete):
            assert recorded.snapshot('0123456789abcdef')['skill']['sim_time_ns']==epoch-120000000
            steps.append(epoch)
    with (tmp_path/'skill.log').open('w+') as log:
        process=subprocess.Popen([sys.executable,'-m','airsim_rf.skills.music','--arrays',str(path),
            '--iq-port',str(iq_port),'--http-port',str(http_port),'--results-dir',str(recorder.path/'results'),'--control-address',f'127.0.0.1:{control_port}'],stdout=log,stderr=log)
        try:
            deadline=time.monotonic()+30
            while True:
                try:
                    with request(f'http://127.0.0.1:{http_port}/health',timeout=.5) as response:
                        if json.load(response)['ingress_ready']:break
                except (OSError,URLError):pass
                if process.poll() is not None or time.monotonic()>deadline:
                    log.seek(0);pytest.fail('Skill startup failed: '+log.read())
                time.sleep(.05)
            with socket.create_connection(('127.0.0.1',iq_port),timeout=10) as connection:
                writer=SampleStreamWriter(connection,carrier_hz=915e6)
                names=[name for site in arrays['sites'] for name in site['channels']]
                rng=np.random.default_rng(42)
                samples=(.001*np.exp(2j*np.pi*10000*np.arange(240000)/FS)+
                    1e-6*(rng.normal(size=240000)+1j*rng.normal(size=240000))).astype(np.complex64)
                async def run_windows():
                    for index in range(2):
                        epoch=index*120000000
                        async def save_source():
                            recorder.source_frame({'sim_time_ns':epoch,'origin_ns':0,'sim_elapsed_s':index*.12,
                                'position_rf_m':[index,0,200]})
                        # Source uses no processing endpoint, estimator name or result.
                        # Commit is submitted only after all channel samples are written.
                        capture=SimpleNamespace(adc_iq_volts=samples,sim_time_ns=epoch,actual_sample_rate_hz=FS,clipped_component_fraction=0.)
                        for name in names[:-1]:writer.send_samples(name,capture.adc_iq_volts,timestamp_ns=epoch,sample_rate_hz=FS)
                        await asyncio.sleep(.15)
                        assert len(steps)==index
                        writer.send_samples(names[-1],capture.adc_iq_volts,timestamp_ns=epoch,sample_rate_hz=FS)
                        assert await advance_after_commit(World(),writer,epoch,120000000,lambda:False,on_committed=save_source)
                        with request(f'http://127.0.0.1:{http_port}/frames/{epoch}',timeout=2) as response:frame=json.load(response)
                        assert frame['timestamp_ns']==epoch and frame['complete_windows']==index+1
                        assert frame['payload_bytes']==(index+1)*8*240000*8
                        assert len(frame['bearings'])==2 and frame['psd']['frequency_khz']
                asyncio.run(run_windows())
                assert writer.finish()=={name:480000 for name in names}
            assert steps==[120000000,240000000]
        finally:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
