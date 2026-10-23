"""Separate-container readiness and image pinning contract."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('dashboard_stdlib',ROOT/'src/airsim_rf/dashboard.py')
dashboard=importlib.util.module_from_spec(spec);spec.loader.exec_module(dashboard)


def instance(tmp_path):
    return dashboard.Dashboard(SimpleNamespace(repo=tmp_path,run_dir=tmp_path/'run',port=8765,
        iq_port=8811,skill_port=8812,control_port=8813,duration=12,pascal_compat=True,
        no_render=False,ready_timeout=300,sim_image='registry:render',skill_image='registry:skill',rf_image='registry:gpu'))


def test_preparation_uses_packaged_rf_image_without_checkout_mount(tmp_path,monkeypatch):
    obj=instance(tmp_path);calls=[]
    monkeypatch.setattr(obj,'command',lambda command,**kw:calls.append(command))
    obj.prepare()
    assert '--entrypoint' in calls[0]
    assert 'registry:gpu' in calls[0]
    assert not any('/work/repo' in item for item in calls[0])


def test_image_pull_inspection_pins_matching_revisions(tmp_path,monkeypatch):
    obj=instance(tmp_path);obj.definition['skill']['revision_policy']='matching';calls=[]
    def command(arguments,**kw):
        calls.append(arguments)
        return SimpleNamespace(stdout=json.dumps([
            {'Id':'sha256:'+arguments[-1].split(':')[-1],'Config':{'Labels':{'org.opencontainers.image.revision':'abc'}}}]))
    monkeypatch.setattr(obj,'command',command)
    obj.pull_images()
    assert len([c for c in calls if c[:2]==['docker','pull']])==3
    assert obj.args.rf_image=='sha256:gpu'


def test_mismatched_images_fail_before_ready(tmp_path,monkeypatch):
    obj=instance(tmp_path)
    monkeypatch.setattr(dashboard.subprocess,'run',lambda *a,**kw:None)
    monkeypatch.setattr(obj,'command',lambda command,**kw:SimpleNamespace(stdout=json.dumps([
        {'Id':'sha256:id','Config':{'Labels':{'org.opencontainers.image.revision':command[-1]}}}])))
    with pytest.raises(RuntimeError,match='revisions differ'):obj.pull_images()
    assert not obj.ready


def test_independently_versioned_skill_does_not_relax_simulator_rf_pairing(tmp_path,monkeypatch):
    obj=instance(tmp_path);obj.definition['skill']['revision_policy']='independent'
    different_rf=False
    def command(arguments,**kwargs):
        image=arguments[-1]
        revision=None if image.endswith(':skill') else 'changed' if different_rf and image.endswith(':gpu') else 'abc'
        return SimpleNamespace(stdout=json.dumps([{'Id':'sha256:'+image.split(':')[-1],
            'Config':{'Labels':{'org.opencontainers.image.revision':revision}}}]))
    monkeypatch.setattr(obj,'command',command)
    obj.pull_images()
    assert obj.args.skill_image=='sha256:skill'
    different_rf=True
    with pytest.raises(RuntimeError,match='revisions differ'):obj.pull_images()


def test_mission_button_requires_ready_and_never_launches_containers(tmp_path,monkeypatch):
    obj=instance(tmp_path)
    monkeypatch.setattr(obj,'launch',lambda *a,**kw:pytest.fail('No containers at mission launch'))
    with pytest.raises(ValueError,match='Prepare healthy'):obj.start()
    obj.ready=True
    obj.processes={part:SimpleNamespace(poll=lambda:None) for part in ('sim','rf','skill')}
    obj.start()
    assert obj.mission_started and json.loads((obj.run/'command.json').read_text())['start']


def test_start_api_rejects_before_readiness(tmp_path):
    obj=instance(tmp_path)
    with pytest.raises(ValueError,match='Services must be ready'):obj.action('start')


def test_rootless_uid_maps_workspace_to_login_user(tmp_path,monkeypatch):
    obj=instance(tmp_path)
    monkeypatch.setattr(obj,'command',lambda command:SimpleNamespace(stdout='["name=rootless"]'))
    obj.configure_docker()
    assert obj.rootless and obj.uid()=='0:0'


def test_rootless_workspace_is_tested_both_directions(tmp_path,monkeypatch):
    obj=instance(tmp_path);obj.rootless=True;calls=[]
    def command(arguments,**kwargs):
        calls.append(arguments)
        marker=obj.run/'.dashboard-access-check'
        assert marker.read_text()=='host-wrote'
        marker.write_text('container-wrote')
        return SimpleNamespace(returncode=0,stderr='')
    monkeypatch.setattr(obj,'command',command)
    obj.check_workspace()
    assert calls[0][calls[0].index('--user')+1]=='0:0'
    assert not (obj.run/'.dashboard-access-check').exists()


def test_workspace_permission_failure_is_actionable_and_not_ready(tmp_path,monkeypatch):
    obj=instance(tmp_path);obj.rootless=True
    monkeypatch.setattr(obj,'command',lambda *a,**kw:SimpleNamespace(returncode=1,stderr='Permission denied'))
    with pytest.raises(RuntimeError,match='fresh --run-dir'):obj.check_workspace()
    assert not obj.ready


def test_rootless_gpu_prefers_cdi_and_falls_back_only_to_working_gpu_runtime(tmp_path,monkeypatch):
    obj=instance(tmp_path);obj.rootless=True;attempts=[]
    def command(arguments,**kwargs):
        attempts.append(arguments)
        return SimpleNamespace(returncode=1 if '--device' in arguments else 0,stderr='unresolvable CDI device',stdout='')
    monkeypatch.setattr(obj,'command',command)
    obj.check_gpu()
    assert '--device' in attempts[0] and '--gpus' in attempts[1]
    assert obj.gpu_options==['--gpus','device=0']
    assert all('--user' in command and command[command.index('--user')+1]=='0:0' for command in attempts)


def test_gpu_failure_never_turns_into_cpu_fallback(tmp_path,monkeypatch):
    obj=instance(tmp_path);obj.rootless=True
    monkeypatch.setattr(obj,'command',lambda *a,**kw:SimpleNamespace(returncode=1,stderr='Permission denied on GPU',stdout=''))
    with pytest.raises(RuntimeError,match='No CPU fallback'):obj.check_gpu()
    assert not obj.ready and obj.gpu_options==[]


@pytest.mark.parametrize('rootless',[True,False])
@pytest.mark.parametrize('custom',[False,True])
def test_services_share_bridge_and_start_before_readiness_waits(tmp_path,monkeypatch,rootless,custom):
    import io
    obj=instance(tmp_path);obj.args.iq_port=18811;obj.rootless=rootless
    if custom:
        import shutil
        source=tmp_path/'custom inputs';shutil.copytree(dashboard._definition.default_directory(),source)
        path=source/'scenario.json';config=json.loads(path.read_text())
        config['skill'].update(kind='custom',image='research/consumer:1',revision_policy='independent',
            ports={'iq':9911,'http':9912,'control':None},command=['--input','/config/arrays.json','--output','/results'])
        path.write_text(json.dumps(config));obj.scenario_path=source;obj.args.skill_image_override=False
    monkeypatch.setattr(dashboard.os,'getuid',lambda:0)
    owned=[]
    monkeypatch.setattr(dashboard.os,'chown',lambda path,uid,gid:owned.append((path,uid,gid)))
    obj.gpu_options=['--device','nvidia.com/gpu=0']
    for name in ('configure_docker','pull_images','check_workspace','check_gpu','prepare'):
        monkeypatch.setattr(obj,name,lambda:None)
    monkeypatch.setattr(obj,'command',lambda *a,**kw:SimpleNamespace(returncode=0,stdout='network',stderr=''))
    commands={}
    def launch(part,command):
        commands[part]=command;obj.processes[part]=SimpleNamespace(poll=lambda:None)
    monkeypatch.setattr(obj,'launch',launch)
    def wait(*a,**kw):assert len(commands)==3
    monkeypatch.setattr(obj,'wait_port',wait)
    monkeypatch.setattr(obj,'read',lambda name:{'status':'ready'})
    class Response(io.BytesIO):status=200
    monkeypatch.setattr(dashboard,'urlopen',lambda *a,**kw:Response(b'{"complete_windows":1}'))
    import socket
    original_socket=socket.socket
    class TestSocket(original_socket):
        def connect_ex(self,address):
            # These services are stubbed; an unrelated local simulator must not
            # affect this launch-command contract test.
            if address[1] in (8989,8990,obj.args.iq_port,obj.args.skill_port,obj.args.control_port):return 111
            return super().connect_ex(address)
    monkeypatch.setattr(dashboard.socket,'socket',TestSocket)
    # Preparing another mission must not reject the HTTP listener already
    # owned by this dashboard process.
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));listener.listen()
        obj.args.port=listener.getsockname()[1]
        obj.bootstrap()
    assert obj.ready and obj.network_created
    for part,command in commands.items():
        assert command[command.index('--network')+1]==obj.network
        assert 'host' not in command
        assert command[command.index('--user')+1]==('10001:10001' if part=='sim' or not rootless else '0:0')
    if rootless:assert not owned
    else:
        results=obj.run/'replays'/obj.recording_id/'results'
        assert (results,10001,10001) in owned
    rf=commands['rf']
    assert rf[rf.index('--workdir')+1]=='/run'
    assert rf[rf.index('--address')+1]=='projectairsim'
    assert rf[rf.index('--iq-host')+1]=='rf-skill'
    assert rf[rf.index('--iq-port')+1]==('9911' if custom else '8811')
    if custom:
        assert commands['skill'][-4:]==['--input','/config/arrays.json','--output','/results']
        assert '127.0.0.1:8812:9912' in commands['skill']
        assert obj.image_tags['skill_image']=='research/consumer:1'
        assert not any(item.startswith('127.0.0.1:8813:') for item in commands['skill'])
    assert '--skill-http-port' not in rf
    assert '--recording-id' in rf
    mounts=[command for command in commands['skill'] if ':/results' in command]
    assert len(mounts)==1 and '/replays/' in mounts[0]
    assert not any(item.endswith(':/run') for item in commands['skill'])


def test_display_matches_camera_time_to_older_iq_not_latest_transport(tmp_path,monkeypatch):
    import io
    obj=instance(tmp_path);key='0123456789abcdef-100'
    (obj.run/'camera').mkdir();(obj.run/'camera'/(key+'.jpg')).write_bytes(b'image at 100')
    records={'producer.json':{'status':'running','geometry_sha256':'g','history':[
        {'sim_time_ns':100,'position_rf_m':[1,0,200]},
        {'sim_time_ns':200,'position_rf_m':[2,0,200]}]},
        'camera.json':{'key':key,'sim_time_ns':100,'geometry_sha256':'g'},'scenario.json':{}}
    monkeypatch.setattr(obj,'read',lambda name:records.get(name,{}))
    def request(url,**kwargs):
        value=({'status':'processing','sim_time_ns':200,'available_epochs':[100,200],'payload_bytes':999}
            if url.endswith('/status') else {'sim_time_ns':100,'payload_bytes':123,'complete_windows':1,'psd':{'from_epoch':100}})
        return io.BytesIO(json.dumps(value).encode())
    monkeypatch.setattr(dashboard,'urlopen',request)
    state=obj.snapshot()
    assert state['producer']['position_rf_m']==[1,0,200]
    assert state['skill']['sim_time_ns']==100
    assert state['transport']['sim_time_ns']==100 and state['transport']['payload_bytes']==123
    assert state['synchronization']['latest_rf_sim_time_ns']==200
    assert state['camera']['url']=='/camera.jpg?frame='+key
    assert state['synchronization']['offset_ms']==0
    assert state['camera']['available']

    # New video can arrive before the skill has finished the next RF window.
    # Keep every measurement, counter and the image on the previous pair.
    newer='0123456789abcdef-120000200'
    (obj.run/'camera'/(newer+'.jpg')).write_bytes(b'newer image')
    records['camera.json']={'key':newer,'sim_time_ns':120000200,'geometry_sha256':'g'}
    records['producer.json']['windows']=999
    records['producer.json']['simulation_speed']=99
    held=obj.snapshot()
    assert held['camera']['url']==state['camera']['url']
    assert held['skill']==state['skill'] and held['transport']==state['transport']
    assert held['producer']==state['producer']


def test_buffered_camera_finds_completed_rf_despite_newer_video(tmp_path,monkeypatch):
    import io
    obj=instance(tmp_path);old='0123456789abcdef-120000000';new='0123456789abcdef-240000000'
    (obj.run/'camera').mkdir()
    for key in (old,new):(obj.run/'camera'/(key+'.jpg')).write_bytes(b'image')
    cameras=[{'key':key,'sim_time_ns':epoch,'geometry_sha256':'g'} for key,epoch in ((old,120000000),(new,240000000))]
    records={'producer.json':{'status':'running','geometry_sha256':'g','windows':3,'simulation_speed':30,'history':[
        {'sim_time_ns':120000000,'position_rf_m':[1,0,200],'windows':2,'simulation_speed':2},
        {'sim_time_ns':240000000,'position_rf_m':[2,0,200],'windows':3,'simulation_speed':30}]},
        'camera.json':{**cameras[-1],'history':cameras},'scenario.json':{}}
    monkeypatch.setattr(obj,'read',lambda name:records.get(name,{}))
    def request(url,**kwargs):
        value=({'status':'processing','sim_time_ns':120000000,'available_epochs':[120000000]}
            if url.endswith('/status') else {'sim_time_ns':120000000,'complete_windows':2})
        return io.BytesIO(json.dumps(value).encode())
    monkeypatch.setattr(dashboard,'urlopen',request)
    state=obj.snapshot()
    assert state['camera']['url'].endswith(old)
    assert state['producer']['windows']==state['skill']['complete_windows']==2
    assert state['producer']['simulation_speed']==2


def test_pair_selection_never_rewinds_and_prefers_closest_image():
    history=[{'sim_time_ns':120000000},{'sim_time_ns':240000000}]
    cameras=[{'sim_time_ns':125000000},{'sim_time_ns':270000000},{'sim_time_ns':239000000}]
    assert dashboard.select_display_pair(history,[120000000,240000000],cameras,60000000)==(history[1],cameras[2])
    assert dashboard.select_display_pair(history,[120000000],cameras,60000000,240000000) is None


def test_recorded_view_keeps_service_health_live_without_changing_saved_data(tmp_path,monkeypatch):
    obj=instance(tmp_path);obj.ready=True
    obj.processes={part:SimpleNamespace(poll=lambda:None,pid=1) for part in ('sim','rf','skill')}
    monkeypatch.setattr(obj,'read',lambda name:{'status':'ready'} if name=='producer.json' else {})
    writer=dashboard._recording.RecordingWriter(obj.run/'replays','0123456789abcdef',{},.12,120000000,no_render=True)
    writer.frame({'sim_time_ns':0,'origin_ns':0,'sim_elapsed_s':0.,'position_rf_m':[1,0,200]},
        {'sim_time_ns':0,'complete_windows':1})
    calls=[]
    def unavailable(url,**kwargs):calls.append(url);raise OSError('skill offline')
    monkeypatch.setattr(dashboard,'urlopen',unavailable)
    state=obj.recorded_snapshot('0123456789abcdef')
    assert state['skill']['complete_windows']==1 and state['producer']['position_rf_m']==[1,0,200]
    assert not state['ready'] and state['service_health']['skill_status']=='offline'
    assert len(calls)==1 and calls[0].endswith('/health')


def test_display_rejects_large_clock_offsets_and_missing_diagnostic_epochs():
    history=[{'sim_time_ns':0},{'sim_time_ns':120000000},{'sim_time_ns':240000000}]
    assert dashboard.select_display_frame(history,[0,120000000],120000000,120000000)==history[1]
    assert dashboard.select_display_frame(history,[240000000],0,120000000) is None
    assert dashboard.select_display_frame(history,[],0,120000000) is None
    assert dashboard.select_display_frame(history,[0],None,120000000) is None
    assert dashboard.select_display_frame(history,[0],120000000,60000000) is None
    assert dashboard.select_display_frame(history,[0,120000000],120000000,60000000)==history[1]


def test_default_direction_finding_skill_is_external_and_independent():
    config=dashboard._definition.load()
    assert config['skill']['kind']=='direction-finding'
    assert config['skill']['revision_policy']=='independent'
    assert config['skill']['image'].startswith('ghcr.io/wa200508/df-skill:sha-')
