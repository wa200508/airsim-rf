"""Scenario selection, physical route/occlusion and source-independent radar DSP."""
import json
from pathlib import Path
import socket
import threading
import time
import numpy as np
import pytest
from airsim_rf.scenario_definition import catalog,load,snapshot
from airsim_rf.dashboard_scenario import flight_path,prepare
from airsim_rf.terrain import TerrainGrid
from radar_skill.processing import range_doppler
from radar_skill.app import RadarSkill
from airsim_rf.sample_stream import SampleStreamWriter


def test_packaged_catalog_and_self_contained_export(tmp_path):
    assert {'drone-orbit','mmwave-radar'}<={row['id'] for row in catalog()}
    c=snapshot('mmwave-radar',tmp_path/'radar')
    assert c['skill']['kind']=='radar' and not c['radios']['transmitters']
    assert c['skill']['mode_config']['waveform']['carrier_hz']==77e9


def route_geometry():
    c=load('mmwave-radar');e=c['environment'];grid=TerrainGrid(e['x_m'],e['y_m'],e['heights_m']);v,f=grid.mesh()
    d={'schema_version':1,'scene_id':'qualification','revision':'1','source':{'adapter':'scenario-heightfield','version':'1','asset':'environment.json','revision':'1','geometry_kind':'shared'},
       'materials':e['materials'],'objects':[{'id':'Terrain','material':e['material'],'vertices_local':(v*[1,-1,-1]).tolist(),'faces':f.tolist(),'local_to_ned_m':np.eye(4).tolist()}]}
    return c,grid,d


def test_racetrack_clears_terrain_and_ground_targets_have_masked_and_clear_passes():
    from airsim_rf.geometry_sync import nearest_intersections
    c,g,d=route_geometry();a=c['flight']['actors'][0]
    assert [actor['id'] for actor in c['flight']['actors']]==['RadarDrone']
    points=np.asarray(flight_path(a,1));np.testing.assert_allclose(points[0],points[-1])
    assert np.min(points[:,2]-g.elevation_at(points[:,0],points[:,1]))>20
    lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    t=np.arange(0,lengths[-1]/a['flight']['speed_m_s'],.02)
    positions=np.array([np.interp(t*a['flight']['speed_m_s'],lengths,points[:,i]) for i in range(3)]).T
    velocity=np.gradient(positions,.02,axis=0)
    for target in c['radios']['radar']['targets']:
        assert 'actor' not in target and target['altitude_reference']=='agl'
        tp=np.array(target['position_rf_m']);tp[2]+=g.elevation_at(*tp[:2])
        assert target['position_rf_m'][2]==target['visual']['size_m'][2]/2
        origin=points*[1,-1,-1];rays=(tp-points)*[1,-1,-1]
        hits=nearest_intersections(d,origin,rays,maximum_distance_m=1000)
        blocked=[hit is not None and hit['distance_m']<dist for hit,dist in zip(hits,np.linalg.norm(rays,axis=1))]
        assert any(blocked) and not all(blocked),target['id']
        rate=np.sum(-velocity*(tp-positions),axis=1)/np.linalg.norm(tp-positions,axis=1)
        assert rate.min() < -15 and rate.max() > 15
        assert max(abs(rate))<=20.01
    assert a['flight']['speed_m_s']**2/a['flight']['turn_radius_m']<=5


def test_fixed_targets_compile_to_shared_visual_and_rf_positions_without_flight_actors(tmp_path):
    from airsim_rf.dashboard_radar import target_states
    from airsim_rf.dashboard_view import ground_target_placements
    from airsim_rf.glb_geometry import triangle_glb
    prepare(tmp_path/'run',scenario_dir='mmwave-radar',duration_s=.004)
    runtime=json.loads((tmp_path/'run/runtime.json').read_text())
    scene=json.loads((tmp_path/'run/sim_config/scene.jsonc').read_text())
    assert [a['name'] for a in scene['actors']]==['RadarDrone']
    radar=runtime['radios']['radar'];states=target_states(radar,{})
    assert len(states)==3 and len({t.rcs_m2 for t in states})==3
    plan=ground_target_placements(radar['targets'])
    c,g,_=route_geometry()
    for source,state,obj in zip(c['radios']['radar']['targets'],states,plan['objects']):
        assert state.velocity_m_s==(0.,0.,0.) and obj['enable_physics'] is False
        assert state.position_m[2]==pytest.approx(g.elevation_at(*source['position_rf_m'][:2])+source['position_rf_m'][2])
        np.testing.assert_allclose(list(obj['pose']['translation'].values()),np.asarray(state.position_m)*[1,-1,-1])
        assert triangle_glb(**obj['mesh']).startswith(b'glTF')
    assert [t.position_m for t in target_states(radar,{})]==[t.position_m for t in states]
    # Moving actor targets remain supported for separately edited scenarios.
    actor={'pose':{'position':{'x':1.,'y':-2.,'z':-3.},'orientation':{'w':1.,'x':0.,'y':0.,'z':0.}},
           'twist':{'linear':{'x':4.,'y':-5.,'z':-6.},'angular':{'x':0.,'y':0.,'z':0.}}}
    moving=target_states({'targets':[{'actor':'Mover','rcs_m2':1.}]},{'Mover':actor})[0]
    assert moving.position_m==(1.,2.,3.) and moving.velocity_m_s==(4.,5.,6.)


def receiver_config(tmp_path,scenario='mmwave-radar'):
    pytest.importorskip('commentjson');prepare(tmp_path/'run',scenario_dir=scenario,duration_s=.004)
    path=tmp_path/'run/receiver-config.json';config=json.loads(path.read_text())
    assert set(config)=={'schema_version','sample_rate_hz','carrier_hz','sites','acquisition','voltage_reference'}
    assert not any(key in config['acquisition'] for key in ('targets','flight','rcs_m2','environment','radar'))
    return path,config


def synthetic_adc(config,range_m=125,range_rate=15):
    a=config['acquisition'];fs=config['sample_rate_hz'];fc=config['carrier_hz'];stride=round(a['pri_s']*fs);slope=a['bandwidth_hz']/a['chirp_duration_s']
    t=np.arange(a['num_samples'])/fs+a['adc_start_s'];slow=np.arange(100)*a['pri_s'];fd=2*range_rate*fc/299792458.
    values=np.zeros((100,stride),np.complex64);gate=round(a['adc_start_s']*fs)
    values[:,gate:gate+len(t)]=.05*np.exp(2j*np.pi*((2*range_m*slope/299792458.+fd)*t[None,:]+fd*slow[:,None]))
    return values.ravel()


def test_radar_processing_uses_only_adc_and_acquisition_config(tmp_path):
    path,c=receiver_config(tmp_path);rd=range_doppler(synthetic_adc(c),c['sample_rate_hz'],c['carrier_hz'],c['acquisition'])
    assert rd['detection']['detected']
    assert rd['detection']['range_m']==pytest.approx(125,abs=rd['range_resolution_m'])
    assert rd['detection']['range_rate_m_s']==pytest.approx(15,abs=rd['velocity_resolution_m_s'])
    noise=np.random.default_rng(3).normal(size=40000)+1j*np.random.default_rng(4).normal(size=40000)
    assert not range_doppler(noise,c['sample_rate_hz'],c['carrier_hz'],c['acquisition'])['detection']['detected']


def test_radar_tcp_commits_real_processing_before_ack(tmp_path):
    path,c=receiver_config(tmp_path);skill=RadarSkill(path,results_dir=tmp_path/'results')
    with socket.socket() as reserve:reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
    thread=threading.Thread(target=skill.serve_stream,args=(port,),daemon=True);thread.start()
    deadline=time.monotonic()+5
    while not skill.snapshot()['ingress_ready']:
        if time.monotonic()>deadline:pytest.fail('radar ingress did not start')
        time.sleep(.01)
    with socket.create_connection(('127.0.0.1',port),timeout=5) as connection:
        writer=SampleStreamWriter(connection,carrier_hz=c['carrier_hz'])
        for i in range(2):
            writer.send_samples('radar_rx0',synthetic_adc(c),timestamp_ns=i*4_000_000,sample_rate_hz=c['sample_rate_hz'])
            assert writer.commit_window()==i*4_000_000
            result=skill.snapshot(i*4_000_000);assert result['radar']['detection']['detected'] and result['complete_windows']==i+1
        assert writer.finish()=={'radar_rx0':80000}
    assert (tmp_path/'results/4000000.json').is_file()


def test_sionna_target_echo_and_mesh_occlusion_agree(tmp_path):
    pytest.importorskip('sionna.rt');pytest.importorskip('commentjson')
    import sionna.rt as rt
    from airsim_rf.fmcw import FMCWRadar,IWR1843Profile
    from airsim_rf.radar import PointTarget
    from dataclasses import replace
    prepare(tmp_path/'run',scenario_dir='mmwave-radar',duration_s=.004)
    scene=rt.load_scene(str(tmp_path/'run/bundle/scene.xml'),merge_shapes=False)
    c,g,d=route_geometry();fixed=json.loads((tmp_path/'run/runtime.json').read_text())['radios']['radar']['targets'][0]
    target=PointTarget('target',tuple(fixed['position_rf_m']),.01)
    radar=FMCWRadar(replace(IWR1843Profile(),noise_enabled=False),rf_scene=scene)
    powers=[]
    for pos in ([200,0,210],[-240,-150,210]):
        delta=np.asarray(target.position_m)-pos
        orientation=[np.arctan2(delta[1],delta[0]),-np.arctan2(delta[2],np.linalg.norm(delta[:2])),0]
        capture=radar.capture([target],position_m=pos,orientation_rad=orientation)
        powers.append(float(np.mean(abs(capture.if_volts)**2)))
        assert radar.last_path_diagnostics['target']['direct_paths']==(1 if pos[0]>0 else 0)
        assert radar.last_path_diagnostics['target']['reflected_paths']==0
    assert powers[0]>0


@pytest.mark.parametrize('terrain_clutter',[False,True])
def test_actual_sionna_radar_iq_to_detector_and_lossless_archive(tmp_path,terrain_clutter):
    """Real source acquisition -> exact recorded cf32 -> unchanged receiver DSP."""
    pytest.importorskip('sionna.rt')
    import sionna.rt as rt
    from airsim_rf.dashboard_radar import RadarWindowReceiver
    from airsim_rf.sample_recording import SampleRecordingWriter,iter_recorded_windows
    from airsim_rf.sample_stream import SampleBlock
    snapshot('mmwave-radar',tmp_path/'nondefault')
    mode_path=tmp_path/'nondefault/radar-mode.json';requested=json.loads(mode_path.read_text())
    requested['waveform'].update(bandwidth_hz=35e6,carrier_hz=78e9);mode_path.write_text(json.dumps(requested))
    radio_path=tmp_path/'nondefault/radios.json';hardware=json.loads(radio_path.read_text())
    hardware['carrier_hz']=78e9;radio_path.write_text(json.dumps(hardware))
    path,config=receiver_config(tmp_path,tmp_path/'nondefault');radio=json.loads((tmp_path/'run/runtime.json').read_text())['radios']
    radio['radar']['clutter']['enabled']=terrain_clutter;radio['radar']['profile']['noise_enabled']=False
    scene=rt.load_scene(str(tmp_path/'run/bundle/scene.xml'),merge_shapes=False) if terrain_clutter else rt.load_scene()
    receiver=RadarWindowReceiver(scene,radio,config)
    from airsim_rf.radar_control import serve_transceiver
    mode=load(tmp_path/'nondefault')['skill']['mode_config']
    skill=RadarSkill(path,results_dir=tmp_path/'actual-results')
    radio_server=serve_transceiver(receiver.control,('127.0.0.1',0))
    try:skill.start_transceiver(f'http://127.0.0.1:{radio_server.server_port}',mode,ready_timeout=2)
    finally:radio_server.shutdown();radio_server.server_close()
    assert receiver.control.snapshot()['transmit'] and receiver.control.snapshot()['receive']
    def kin(position,velocity):
        return {'pose':{'position':dict(zip(('x','y','z'),np.asarray(position)*[1,-1,-1])),
                        'orientation':{'w':1.,'x':0.,'y':0.,'z':0.}},
                'twist':{'linear':dict(zip(('x','y','z'),np.asarray(velocity)*[1,-1,-1])),
                         'angular':{'x':0.,'y':0.,'z':0.}}}
    receiver.update({'RadarDrone':kin([30,25,150],[-20,0,0])})
    assert len(receiver.targets)==3 and all(t.velocity_m_s==(0.,0.,0.) for t in receiver.targets)
    capture=receiver.capture(0,num_samples=40000)['radar_rx0']
    assert set(receiver.radar.last_path_diagnostics)=={t.name for t in receiver.targets}
    assert receiver.truth['target_names']==[t.name for t in receiver.targets]
    assert all(v['reflected_paths']==0 for v in receiver.radar.last_path_diagnostics.values())
    assert bool(capture.retained_paths['terrain_echoes'])==terrain_clutter
    assert receiver.radar.profile.bandwidth_hz==35e6
    assert receiver.radar.scene.frequency==78e9
    assert receiver.control.snapshot()['applied_configuration_id']==skill.snapshot()['transceiver']['configuration_id']
    original=SampleBlock('radar_rx0',capture.adc_iq_volts,0,0,config['sample_rate_hz'],config['carrier_hz'],capture.clipped_component_fraction)
    recording=SampleRecordingWriter(tmp_path/'iq',config);recording.write_window([original]);recording.close()
    restored=next(iter_recorded_windows(tmp_path/'iq'))[0]
    assert restored.samples.tobytes()==original.samples.tobytes()
    with socket.socket() as reserve:reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
    threading.Thread(target=skill.serve_stream,args=(port,),daemon=True).start()
    deadline=time.monotonic()+5
    while not skill.snapshot()['ingress_ready']:
        if time.monotonic()>deadline:pytest.fail('radar ingress did not start')
        time.sleep(.01)
    with socket.create_connection(('127.0.0.1',port),timeout=10) as connection:
        writer=SampleStreamWriter(connection,carrier_hz=restored.carrier_hz)
        writer.send_samples(restored.receiver,restored.samples,timestamp_ns=restored.timestamp_ns,sample_rate_hz=restored.sample_rate_hz)
        writer.commit_window();assert writer.finish()=={'radar_rx0':40000}
    measured=skill.snapshot()['radar'];truth=receiver.truth
    assert (tmp_path/'actual-results/0.json').is_file()
    assert measured['detection']['detected']
    assert measured['detection']['range_m']==pytest.approx(truth['target_ranges_m'][0],abs=measured['range_resolution_m'])
    assert measured['detection']['range_rate_m_s']==pytest.approx(truth['target_range_rates_m_s'][0],abs=measured['velocity_resolution_m_s']*2)
    cube=original.samples.reshape(100,400)
    assert np.all(cube[:,:30]==0) and np.all(cube[:,286:]==0)


@pytest.mark.parametrize('field,value',[('pri_s',35e-6),('carrier_hz',24e9),('sample_rate_hz',30e6),('if_high_hz',6e6),('adc_bits',1)])
def test_invalid_radar_acquisition_is_rejected_before_docker(tmp_path,field,value):
    snapshot('mmwave-radar',tmp_path/'edited')
    if field in ('pri_s','carrier_hz','sample_rate_hz'):
        path=tmp_path/'edited/radar-mode.json';c=json.loads(path.read_text())
        c['receiver' if field=='sample_rate_hz' else 'waveform'][field]=value
    else:
        path=tmp_path/'edited/radios.json';c=json.loads(path.read_text());c['radar']['profile'][field]=value
    path.write_text(json.dumps(c))
    with pytest.raises(ValueError):load(tmp_path/'edited')


@pytest.mark.parametrize('change', ['duplicate','mixed','outside-dem','negative-agl'])
def test_invalid_fixed_targets_fail_before_service_launch(tmp_path,change):
    snapshot('mmwave-radar',tmp_path/'edited')
    path=tmp_path/'edited/radios.json';radio=json.loads(path.read_text())
    targets=radio['radar']['targets']
    if change=='duplicate':targets[1]['id']=targets[0]['id']
    elif change=='mixed':targets[0]['actor']='RadarDrone'
    elif change=='outside-dem':targets[0]['position_rf_m'][0]=10000
    else:targets[0]['position_rf_m'][2]=-1
    path.write_text(json.dumps(radio))
    with pytest.raises(ValueError):load(tmp_path/'edited')


@pytest.mark.parametrize('field,value',[('sample_count',0),('seed',-1),('enabled','yes'),('materials',{'unknown':{'sigma0_db':-20.,'incidence_exponent':1.}})])
def test_invalid_clutter_is_rejected_before_launch(tmp_path,field,value):
    snapshot('mmwave-radar',tmp_path/'edited')
    path=tmp_path/'edited/radios.json';radio=json.loads(path.read_text());radio['radar']['clutter'][field]=value
    path.write_text(json.dumps(radio))
    with pytest.raises(ValueError):load(tmp_path/'edited')
