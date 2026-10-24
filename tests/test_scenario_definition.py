"""Portable scenario input/compilation contracts, without Docker or a live world."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
import pytest
from airsim_rf.scenario_definition import load,default_directory,snapshot
from airsim_rf.dashboard_scenario import prepare,flight_path,WaveformSource,create_receiver


@pytest.fixture
def package(tmp_path):
    target=tmp_path/'editable inputs';shutil.copytree(default_directory(),target);return target


def change(package,file,edit):
    path=package/file;data=json.loads(path.read_text());edit(data);path.write_text(json.dumps(data));return data


def test_portable_package_validates_from_arbitrary_cwd_without_scientific_imports(package,tmp_path):
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'scripts/launch_dashboard.py'),'--scenario',str(package),
        '--check-scenario'],cwd=tmp_path,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['status']=='valid'
    path=tmp_path/'frozen';snapshot(package,path)
    change(package,'scenario.json',lambda d:d.update(title='Changed after snapshot'))
    assert load(path)['title']!=load(package)['title']


@pytest.mark.parametrize('field,value',[('rf_update_ns',120000001),('physics_step_ns',7000000)])
def test_invalid_clock_alignment_fails_before_services(package,field,value):
    change(package,'scenario.json',lambda d:d['mission'].update({field:value}))
    with pytest.raises(ValueError,match='align'):load(package)


def test_assets_stay_near_definition_and_mismatched_skill_is_rejected(package):
    change(package,'scenario.json',lambda d:d.update(radios='../outside.json'))
    with pytest.raises(ValueError,match='out-of-package'):load(package)
    change(package,'scenario.json',lambda d:d.update(radios='radios.json'))
    change(package,'radios.json',lambda d:d['sites'].pop())
    with pytest.raises(ValueError,match='two sites'):load(package)
    change(package,'scenario.json',lambda d:d['skill'].update(kind='custom',revision_policy='independent',image='research/energy:1'))
    assert len(load(package)['radios']['sites'])==1


def test_same_compiler_uses_edited_inputs_instead_of_dashboard_constants(package,tmp_path):
    pytest.importorskip('commentjson')
    change(package,'scenario.json',lambda d:(d['mission'].update(duration_s=.24),d['camera'].update(distance_m=9)))
    change(package,'flight.json',lambda d:(d['actors'][0].update(position_rf_m=[175,0,210]),
        d['actors'][0]['flight'].update(radius_m=175,speed_m_s=12,center_rf_m=[0,0,210])))
    def radio_edit(d):
        d.update(carrier_hz=433e6,sample_rate_hz=1e6)
        d['receiver_profile'].update(carrier_hz=433e6,sample_rate_hz=1e6,rf_bandwidth_hz=400000.)
        d['transmitters'][0].update(power_w=.03)
        d['sites'][1].update(yaw_rad=.4)
    change(package,'radios.json',radio_edit)
    change(package,'environment.json',lambda d:d['materials']['earth'].update(relative_permittivity=3.2))
    run=tmp_path/'run';arrays=prepare(run,scenario_dir=package)
    runtime=json.loads((run/'runtime.json').read_text());summary=json.loads((run/'scenario.json').read_text())
    assert arrays['carrier_hz']==433e6 and arrays['sample_rate_hz']==1e6
    assert summary['radius_m']==175 and summary['speed_m_s']==12
    assert runtime['radios']['transmitters'][0]['power_w']==.03 and runtime['camera']['distance_m']==9
    assert json.loads((run/'bundle/geometry.json').read_text())['materials']['earth']['relative_permittivity']==3.2
    assert (run/'scenario-input/quadrotor.jsonc').is_file()
    assert not any(key in arrays for key in ('flight','environment','transmitters','waveform','skill'))
    path=np.asarray(runtime['compiled_routes_rf_m'][runtime['flight']['actors'][0]['id']])
    radius=np.linalg.norm(path[:,:2],axis=1)
    assert radius.min()>=175*np.cos(np.deg2rad(1.5))-1e-8 and radius.max()<=175+1e-8
    scene=json.loads((run/'sim_config/scene.jsonc').read_text())
    np.testing.assert_allclose(list(map(float,scene['actors'][0]['origin']['xyz'].split())),[175,0,-210])


def test_waypoints_hold_and_multiple_movers_are_data(package,tmp_path):
    pytest.importorskip('commentjson')
    config=load(package);actor=deepcopy(config['flight']['actors'][0])
    actor['flight']={'type':'waypoints','points_rf_m':[[1,2,210],[10,2,210]],'speed_m_s':4,'lookahead_m':2,'adaptive_lookahead':0}
    assert flight_path(actor,1)==[[1,2,210],[10,2,210]]
    actor['flight']={'type':'hold'};assert flight_path(actor,1)==[]
    actor['id']='SecondDrone';actor['position_rf_m']=[20,20,210]
    change(package,'flight.json',lambda d:d['actors'].append(actor))
    tx=deepcopy(config['radios']['transmitters'][0]);tx.update(id='tx_second',actor='SecondDrone',power_w=.02)
    change(package,'radios.json',lambda d:d['transmitters'].append(tx))
    prepare(tmp_path/'run',scenario_dir=package)
    runtime=json.loads((tmp_path/'run/runtime.json').read_text())
    assert len(runtime['flight']['actors'])==len(runtime['radios']['transmitters'])==2
    assert {a['name'] for a in json.loads((tmp_path/'run/sim_config/scene.jsonc').read_text())['actors']}=={'OrbitDrone','SecondDrone'}


def test_arbitrary_sampled_waveform_requires_duration_coverage(package,tmp_path):
    pytest.importorskip('commentjson')
    change(package,'scenario.json',lambda d:d['mission'].update(duration_s=.12))
    change(package,'waveform.json',lambda d:(d.clear(),d.update(type='samples',file='measured.npy')))
    np.save(package/'measured.npy',np.ones(32,np.complex64))
    with pytest.raises(ValueError,match='cover'):prepare(tmp_path/'run',scenario_dir=package)
    values=np.exp(2j*np.pi*.01*np.arange(240032)).astype(np.complex64);np.save(package/'measured.npy',values)
    prepare(tmp_path/'run',scenario_dir=package)
    source=WaveformSource(tmp_path/'run/scenario-input','waveform.json',2e6)
    result,epoch,boundary=source.window(120000000,1024,0)
    np.testing.assert_array_equal(result,values);assert epoch==0 and boundary=='zero'


def test_configured_receiver_adapter_renders_real_iq_on_cpu(package,tmp_path):
    pytest.importorskip('commentjson');pytest.importorskip('sionna.rt')
    import sionna.rt as rt
    def edit(d):
        d['propagation'].update(renderer='numpy',max_depth=0,samples_per_link=64)
        d.update(carrier_hz=433e6,sample_rate_hz=1e6)
        d['receiver_profile'].pop('carrier_hz',None);d['receiver_profile'].pop('sample_rate_hz',None)
        d['receiver_profile']['rf_bandwidth_hz']=400000.
        d['sites'][1]['yaw_rad']=.4
    change(package,'radios.json',edit)
    prepare(tmp_path/'run',scenario_dir=package,duration_s=.12)
    config=load(tmp_path/'run/scenario-input');radio=config['radios']
    arrays=json.loads((tmp_path/'run/arrays.json').read_text())
    scene=rt.load_scene(str(tmp_path/'run/bundle/scene.xml'),merge_shapes=False)
    sources={tx['id']:WaveformSource(tmp_path/'run/scenario-input',tx['waveform'],radio['sample_rate_hz']) for tx in radio['transmitters']}
    receiver=create_receiver(scene,radio,arrays,sources,0,1024)
    assert receiver.samples_per_link==64
    scene.transmitters['tx0'].position=[250,0,200]
    captured=receiver.capture(0,num_samples=1024)
    assert len(captured)==8
    assert all(len(block.adc_iq_volts)==1024 and np.isfinite(block.adc_iq_volts).all() for block in captured.values())
    assert receiver.profile.carrier_hz==radio['carrier_hz']
    from airsim_rf.sample_stream import SampleBlock
    from airsim_rf.sample_recording import SampleRecordingWriter,iter_recorded_windows
    saved=SampleRecordingWriter(tmp_path/'propagated-iq',arrays)
    blocks=[SampleBlock(name,captured[name].adc_iq_volts,0,captured[name].sim_time_ns,
        captured[name].actual_sample_rate_hz,radio['carrier_hz'],captured[name].clipped_component_fraction)
        for site in arrays['sites'] for name in site['channels']]
    saved.write_window(blocks);saved.close()
    restored=next(iter_recorded_windows(tmp_path/'propagated-iq'))
    assert all(a.samples.tobytes()==b.samples.tobytes() for a,b in zip(blocks,restored))
    expected=np.asarray(arrays['sites'][1]['center_rf_m'])+arrays['sites'][1]['element_offsets_m'][0]*np.array([-np.sin(.4),np.cos(.4),0])
    np.testing.assert_allclose(scene.receivers['site1_e0'].position.numpy().reshape(3),expected,atol=1e-5)


def test_bulk_capture_space_is_checked_only_for_execution(package,tmp_path,monkeypatch):
    from types import SimpleNamespace
    pytest.importorskip('commentjson')
    monkeypatch.setattr('airsim_rf.dashboard_scenario.shutil.disk_usage',lambda path:SimpleNamespace(free=64*1024**2))
    with pytest.raises(ValueError,match='Insufficient output space for bulk I/Q'):
        prepare(tmp_path/'run',scenario_dir=package,check_iq_space=True)
    change(package,'scenario.json',lambda d:d['mission'].update(record_iq=False))
    prepare(tmp_path/'run-disabled',scenario_dir=package,check_iq_space=True)
    assert not json.loads((tmp_path/'run-disabled/runtime.json').read_text())['mission']['record_iq']
