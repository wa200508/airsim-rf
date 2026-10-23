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


def test_racetrack_clears_terrain_has_occluded_and_clear_passes_and_20_mps_range_rate():
    from airsim_rf.geometry_sync import nearest_intersections
    c,g,d=route_geometry();a=c['flight']['actors'][0];target=c['flight']['actors'][1]
    points=np.asarray(flight_path(a,1));np.testing.assert_allclose(points[0],points[-1])
    assert np.min(points[:,2]-g.elevation_at(points[:,0],points[:,1]))>20
    origin=points*[1,-1,-1];rays=np.asarray(target['position_rf_m'])*[1,-1,-1]-origin
    hits=nearest_intersections(d,origin,rays,maximum_distance_m=1000)
    blocked=[hit is not None and hit['distance_m']<dist for hit,dist in zip(hits,np.linalg.norm(rays,axis=1))]
    assert any(blocked) and not all(blocked)
    lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    t=np.arange(0,lengths[-1]/a['flight']['speed_m_s'],.02)
    positions=np.array([np.interp(t*a['flight']['speed_m_s'],lengths,points[:,i]) for i in range(3)]).T
    velocity=np.gradient(positions,.02,axis=0);f=target['flight'];angle=t*f['speed_m_s']/f['radius_m']
    tp=np.asarray(f['center_rf_m'])+np.column_stack((2.5*np.cos(angle),2.5*np.sin(angle),np.zeros(len(t))))
    tv=np.column_stack((-2*np.sin(angle),2*np.cos(angle),np.zeros(len(t))))
    rate=np.sum((tv-velocity)*(tp-positions),axis=1)/np.linalg.norm(tp-positions,axis=1)
    assert 19<max(abs(rate))<22
    assert np.all(abs(tp[:,2]-g.elevation_at(tp[:,0],tp[:,1])-10)<1)
    assert f['speed_m_s']**2/f['radius_m']<2
    assert a['flight']['speed_m_s']**2/a['flight']['turn_radius_m']<=5


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
    c,g,d=route_geometry();target=PointTarget('target',tuple(c['flight']['actors'][1]['position_rf_m']),.01)
    radar=FMCWRadar(replace(IWR1843Profile(),noise_enabled=False),rf_scene=scene,max_depth=1)
    powers=[]
    for pos in ([200,0,210],[-240,-150,210]):
        delta=np.asarray(target.position_m)-pos
        orientation=[np.arctan2(delta[1],delta[0]),-np.arctan2(delta[2],np.linalg.norm(delta[:2])),0]
        capture=radar.capture([target],position_m=pos,orientation_rad=orientation)
        powers.append(float(np.mean(abs(capture.if_volts)**2)))
        assert radar.last_path_diagnostics['target']['direct_paths']==(1 if pos[0]>0 else 0)
    assert powers[0]>0


def test_actual_sionna_radar_iq_to_detector_and_lossless_archive(tmp_path):
    """Real source acquisition -> exact recorded cf32 -> unchanged receiver DSP."""
    pytest.importorskip('sionna.rt')
    import sionna.rt as rt
    from airsim_rf.dashboard_radar import RadarWindowReceiver
    from airsim_rf.sample_recording import SampleRecordingWriter,iter_recorded_windows
    from airsim_rf.sample_stream import SampleBlock
    snapshot('mmwave-radar',tmp_path/'nondefault')
    mode_path=tmp_path/'nondefault/radar-mode.json';requested=json.loads(mode_path.read_text())
    requested['waveform']['bandwidth_hz']=35e6;mode_path.write_text(json.dumps(requested))
    path,config=receiver_config(tmp_path,tmp_path/'nondefault');radio=load(tmp_path/'nondefault')['radios']
    radio['radar']['max_depth_per_leg']=0;radio['radar']['profile']['noise_enabled']=False
    receiver=RadarWindowReceiver(rt.load_scene(),radio,config)
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
    receiver.update({'RadarDrone':kin([30,25,150],[-20,0,0]),'TargetDrone':kin([0,25,110],[0,2,0])})
    capture=receiver.capture(0,num_samples=40000)['radar_rx0']
    assert receiver.radar.profile.bandwidth_hz==35e6
    assert receiver.control.snapshot()['applied_configuration_id']==skill.snapshot()['transceiver']['configuration_id']
    original=SampleBlock('radar_rx0',capture.adc_iq_volts,0,0,10e6,77e9,capture.clipped_component_fraction)
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
