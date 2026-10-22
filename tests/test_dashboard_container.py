"""Fresh-install launch contract and task-owned process lifecycle."""
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('dashboard_stdlib',ROOT/'src/airsim_rf/dashboard.py')
dashboard=importlib.util.module_from_spec(spec);spec.loader.exec_module(dashboard)


def args(tmp_path):
    return SimpleNamespace(repo=tmp_path,run_dir=tmp_path/'run',blocks=tmp_path/'blocks',
        container_runtime=True,port=8765,iq_port=8811,skill_port=8812,control_port=8813,
        duration=12,pascal_compat=True,no_render=False)


def test_bundled_scene_preparation_never_calls_docker(tmp_path,monkeypatch):
    instance=dashboard.Dashboard(args(tmp_path));calls=[]
    monkeypatch.setattr(instance,'command',lambda value:calls.append(value))
    instance.prepare()
    assert calls[0][0]==sys.executable and 'docker' not in calls[0]
    assert str(tmp_path/'run') in calls[0]
    assert str(tmp_path/'.deps/ProjectAirSim') in calls[0]


def test_bundled_launch_starts_real_children_in_order_with_pascal(tmp_path,monkeypatch):
    instance=dashboard.Dashboard(args(tmp_path))
    executable=instance.args.blocks/'Blocks/Binaries/Linux/Blocks-Linux-Shipping'
    executable.parent.mkdir(parents=True);executable.touch()
    monkeypatch.setattr(instance,'prepare',lambda:None)
    monkeypatch.setattr(instance,'wait_port',lambda *a,**k:None)
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setattr(dashboard,'urlopen',lambda *a,**k:Response())
    calls=[]
    monkeypatch.setattr(instance,'launch',lambda part,command,**kw:calls.append((part,command,kw)))
    instance.start()
    assert [part for part,_,_ in calls]==['sim','skill','rf']
    assert all('docker' not in command for _,command,_ in calls)
    assert calls[0][2]['env']['RF_BLOCKS_DIR']==str(instance.args.blocks.resolve())
    assert 'airsim_rf.dashboard_skill' in calls[1][1]
    assert '--pascal-compat' in calls[2][1] and 'airsim_rf.cuda_launch' in calls[2][1]


def test_bundled_stop_terminates_only_owned_process_groups(tmp_path,monkeypatch):
    instance=dashboard.Dashboard(args(tmp_path))
    instance.processes={name:SimpleNamespace(pid=pid,wait=lambda **kw:None) for name,pid in [('rf',401),('skill',402),('sim',403)]}
    killed=[]
    monkeypatch.setattr(dashboard.os,'killpg',lambda pid,sig:killed.append((pid,sig)))
    monkeypatch.setattr(instance,'command',lambda *a,**k:pytest.fail('Docker must not be used'))
    instance.stop()
    assert killed==[(401,signal.SIGTERM),(402,signal.SIGTERM),(403,signal.SIGTERM)]


def test_fresh_checkout_defaults_pull_published_images(monkeypatch,tmp_path):
    monkeypatch.delenv('RF_DASHBOARD_CONTAINER',raising=False)
    monkeypatch.setattr(sys,'argv',['dashboard','--repo',str(tmp_path),'--run-dir',str(tmp_path/'run')])
    calls=[]
    monkeypatch.setattr(dashboard.subprocess,'run',lambda command,**kw:calls.append(command))
    class Bound(Exception):pass
    monkeypatch.setattr(dashboard,'ThreadingHTTPServer',lambda *a:(_ for _ in ()).throw(Bound()))
    with pytest.raises(Bound):dashboard.main()
    assert calls and all(c[:2]==['docker','pull'] for c in calls)
    assert all(c[2].startswith('ghcr.io/wa200508/airsim-rf:dashboard-') for c in calls)


def test_container_defaults_bind_ui_and_keep_compatibility_when_cmd_overridden(monkeypatch,tmp_path):
    monkeypatch.setenv('RF_DASHBOARD_CONTAINER','1')
    monkeypatch.setattr(sys,'argv',['dashboard','--run-dir',str(tmp_path/'run'),'--duration','12'])
    captured=[]
    class Bound(Exception):pass
    def capture(arguments):
        captured.append(arguments)
        raise Bound()
    monkeypatch.setattr(dashboard,'Dashboard',capture)
    monkeypatch.setattr(dashboard.subprocess,'run',lambda *a,**k:pytest.fail('No Docker or build on startup'))
    with pytest.raises(Bound):dashboard.main()
    arguments=captured[0]
    assert arguments.bind=='0.0.0.0' and arguments.repo==Path('/opt/airsim-rf')
    assert arguments.container_runtime and arguments.pascal_compat
