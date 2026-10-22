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
