"""Offline installed-runtime smoke: bundled assets, preparation and dashboard HTTP.

This deliberately does not claim CUDA or a live rendered RF mission on CPU CI.
"""
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT=Path('/opt/airsim-rf')


def main():
    for name,version in (('cupy-cuda12x','13.6.0'),('mitsuba','3.8.0'),('drjit','1.3.1'),
                         ('sionna-rt','2.2.0'),('usd-core','26.8'),('doa-py','0.5.0')):
        assert importlib.metadata.version(name)==version,(name,importlib.metadata.version(name))
    executable=Path('/opt/blocks/Blocks/Binaries/Linux/Blocks-Linux-Shipping')
    assert executable.is_file() and os.access(executable,os.X_OK),'Bundled simulator missing'
    dependencies=subprocess.run(['ldd',str(executable)],capture_output=True,text=True,check=True)
    assert 'not found' not in dependencies.stdout,dependencies.stdout
    from airsim_rf.dashboard_scenario import prepare
    with tempfile.TemporaryDirectory() as temporary:
        output=Path(temporary)
        prepare(output,ROOT/'.deps/ProjectAirSim')
        arrays=json.loads((output/'arrays.json').read_text())
        assert len(arrays['sites'])==2
        assert sum(len(site['channels']) for site in arrays['sites'])==8
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        command=[sys.executable,str(ROOT/'scripts/launch_dashboard.py'),'--port',str(port),
                 '--run-dir',str(output),'--bind','127.0.0.1']
        http=build_opener(ProxyHandler({}))
        with (output/'dashboard.log').open('w') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            try:
                for _ in range(100):
                    if process.poll() is not None:raise RuntimeError((output/'dashboard.log').read_text())
                    try:
                        with http.open(f'http://127.0.0.1:{port}/api/status',timeout=1) as response:
                            state=json.load(response)
                        break
                    except (OSError,URLError):time.sleep(.1)
                else:raise RuntimeError('Dashboard HTTP did not become ready')
                assert state['processes']=={} and state['error'] is None
                with http.open(f'http://127.0.0.1:{port}/',timeout=2) as response:
                    assert b'Launch' in response.read()
            finally:
                process.terminate()
                process.wait(timeout=15)
    print('Bundled dashboard: pinned GPU libraries, simulator dependencies, scene preparation and HTTP passed. GPU mission not exercised.')


if __name__=='__main__':main()
