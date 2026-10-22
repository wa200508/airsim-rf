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
    monkeypatch.setattr(obj,'command',lambda command:calls.append(command))
    obj.prepare()
    assert '--entrypoint' in calls[0]
    assert 'registry:gpu' in calls[0]
    assert not any('/work/repo' in item for item in calls[0])


def test_image_pull_inspection_pins_matching_revisions(tmp_path,monkeypatch):
    obj=instance(tmp_path);calls=[]
    monkeypatch.setattr(dashboard.subprocess,'run',lambda command,**kw:calls.append(command))
    monkeypatch.setattr(obj,'command',lambda command:SimpleNamespace(stdout=json.dumps([
        {'Id':'sha256:'+command[-1].split(':')[-1],'Config':{'Labels':{'org.opencontainers.image.revision':'abc'}}}])))
    obj.pull_images()
    assert len(calls)==3 and all(command[:2]==['docker','pull'] for command in calls)
    assert obj.args.rf_image=='sha256:gpu'


def test_mismatched_images_fail_before_ready(tmp_path,monkeypatch):
    obj=instance(tmp_path)
    monkeypatch.setattr(dashboard.subprocess,'run',lambda *a,**kw:None)
    monkeypatch.setattr(obj,'command',lambda command:SimpleNamespace(stdout=json.dumps([
        {'Id':'sha256:id','Config':{'Labels':{'org.opencontainers.image.revision':command[-1]}}}])))
    with pytest.raises(RuntimeError,match='revisions differ'):obj.pull_images()
    assert not obj.ready


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


def test_rootless_services_share_bridge_and_start_before_readiness_waits(tmp_path,monkeypatch):
    import io
    obj=instance(tmp_path);obj.args.iq_port=18811;obj.rootless=True
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
    obj.bootstrap()
    assert obj.ready and obj.network_created
    for part,command in commands.items():
        assert command[command.index('--network')+1]==obj.network
        assert 'host' not in command
        assert command[command.index('--user')+1]==('10001:10001' if part=='sim' else '0:0')
    rf=commands['rf']
    assert rf[rf.index('--address')+1]=='projectairsim'
    assert rf[rf.index('--skill-host')+1]=='rf-skill'
    assert rf[rf.index('--skill-port')+1]=='8811'
