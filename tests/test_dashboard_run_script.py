"""Host interpreter selection must honor virtual environments, not container Python."""
import json
import os
from pathlib import Path
import subprocess
import sys
import signal
import time

ROOT=Path(__file__).resolve().parents[1]


def fixture_tools(tmp_path):
    tools=tmp_path/'bin';tools.mkdir()
    docker=tools/'docker'
    docker.write_text(f'''#!{sys.executable}
import json,os,sys
with open(os.environ['CALLS'],'a') as stream: stream.write(json.dumps(['docker',*sys.argv[1:]])+'\\n')
if sys.argv[1]=='create': print('test-source-container')
''')
    docker.chmod(0o755)
    def python_at(path,label):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(f'''#!{sys.executable}
import json,os,sys
with open(os.environ['CALLS'],'a') as stream: stream.write(json.dumps([{label!r},*sys.argv[1:]])+'\\n')
''')
        path.chmod(0o755)
        return path
    python_at(tools/'python3','system-python')
    env=dict(os.environ,PATH=str(tools)+os.pathsep+os.environ['PATH'],CALLS=str(tmp_path/'calls.jsonl'),
             XDG_CACHE_HOME=str(tmp_path/'cache'))
    env.pop('VIRTUAL_ENV',None);env.pop('RF_DASHBOARD_PYTHON',None)
    return env,python_at


def run(env):
    return subprocess.run(['bash',str(ROOT/'scripts/run_dashboard.sh'),'--duration','12'],env=env,capture_output=True,text=True)


def calls(env):
    path=Path(env['CALLS'])
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_activated_environment_wins_over_system_python_including_spaces(tmp_path):
    env,python_at=fixture_tools(tmp_path)
    environment=tmp_path/'virtual environment'
    interpreter=python_at(environment/'bin/python','venv-python')
    env['VIRTUAL_ENV']=str(environment)
    result=run(env)
    assert result.returncode==0,result.stderr
    events=calls(env)
    assert events[0][0]=='venv-python' and events[0][1]=='-c'
    assert events[-1][0]=='venv-python' and '--duration' in events[-1]
    assert not any(e[0]=='system-python' for e in events)
    assert str(interpreter) in result.stdout


def test_explicit_interpreter_overrides_activated_environment(tmp_path):
    env,python_at=fixture_tools(tmp_path)
    env['VIRTUAL_ENV']=str(tmp_path/'missing environment')
    env['RF_DASHBOARD_PYTHON']=str(python_at(tmp_path/'chosen/bin/python','chosen-python'))
    assert run(env).returncode==0
    assert calls(env)[-1][0]=='chosen-python'


def test_without_venv_uses_python3_from_path(tmp_path):
    env,_=fixture_tools(tmp_path)
    assert run(env).returncode==0
    assert calls(env)[-1][0]=='system-python'


def test_broken_active_environment_fails_before_any_docker_operations(tmp_path):
    env,_=fixture_tools(tmp_path)
    env['VIRTUAL_ENV']=str(tmp_path/'missing environment')
    result=run(env)
    assert result.returncode!=0 and 'Active virtual environment' in result.stderr
    assert calls(env)==[]


def test_standalone_script_extracts_launcher_when_no_checkout_exists(tmp_path):
    env,_=fixture_tools(tmp_path)
    standalone=tmp_path/'downloaded/run_dashboard.sh';standalone.parent.mkdir()
    standalone.write_text((ROOT/'scripts/run_dashboard.sh').read_text())
    result=subprocess.run(['bash',str(standalone),'--duration','12'],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    events=calls(env)
    assert any(e[:3]==['docker','pull','ghcr.io/wa200508/airsim-rf:dashboard-gpu'] for e in events)
    assert any(e[:2]==['docker','cp'] for e in events)
    assert events[-1][0]=='system-python' and events[-1][1].endswith('/cache/airsim-rf-dashboard/dashboard.py')


def test_checkout_uses_current_launcher_instead_of_image_embedded_copy(tmp_path):
    env,_=fixture_tools(tmp_path)
    assert run(env).returncode==0
    events=calls(env)
    assert events[-1][1]==str(ROOT/'scripts/launch_dashboard.py')
    assert not any(e[0]=='docker' for e in events)


def test_cached_standalone_replay_does_not_pull_or_create_containers(tmp_path):
    env,_=fixture_tools(tmp_path)
    standalone=tmp_path/'downloaded/run_dashboard.sh';standalone.parent.mkdir()
    standalone.write_text((ROOT/'scripts/run_dashboard.sh').read_text())
    cache=Path(env['XDG_CACHE_HOME'])/'airsim-rf-dashboard';cache.mkdir(parents=True)
    for name in ('dashboard.py','dashboard_recording.py'):(cache/name).write_text('# cached launcher')
    result=subprocess.run(['bash',str(standalone),'--replay'],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    events=calls(env)
    assert not any(event[0]=='docker' for event in events)
    assert '--replay' in events[-1]


def test_standalone_interrupted_extraction_removes_source_container(tmp_path):
    env,_=fixture_tools(tmp_path)
    standalone=tmp_path/'downloaded/run_dashboard.sh';standalone.parent.mkdir()
    standalone.write_text((ROOT/'scripts/run_dashboard.sh').read_text())
    docker=tmp_path/'bin/docker'
    docker.write_text(f'''#!{sys.executable}
import json,os,sys,time
with open(os.environ['CALLS'],'a') as stream: stream.write(json.dumps(['docker',*sys.argv[1:]])+'\\n')
if sys.argv[1]=='cp':
    with open(os.environ['CALLS']+'.pid','w') as stream: stream.write(str(os.getpid()))
    time.sleep(60)
''')
    child=subprocess.Popen(['bash',str(standalone)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    marker=Path(env['CALLS']+'.pid')
    try:
        deadline=time.monotonic()+5
        while not marker.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.02)
        assert marker.exists()
        child.send_signal(signal.SIGTERM)
        child.communicate(timeout=5)
        assert child.returncode==143
        events=calls(env)
        create=next(e for e in events if e[:2]==['docker','create'])
        name=create[create.index('--name')+1]
        assert ['docker','rm','-f',name] in events
        import pytest
        with pytest.raises(ProcessLookupError):os.kill(int(marker.read_text()),0)
    finally:
        if child.poll() is None:child.kill();child.communicate()
