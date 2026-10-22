"""Host interpreter selection must honor virtual environments, not container Python."""
import json
import os
from pathlib import Path
import subprocess
import sys

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
