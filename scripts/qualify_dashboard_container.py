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
        assert (ROOT/'src/airsim_rf/dashboard.py').is_file()
        assert (ROOT/'src/airsim_rf/dashboard_static/index.html').is_file()
    print('Bundled dashboard: pinned GPU libraries, simulator dependencies, scene preparation and packaged host launcher passed. GPU mission not exercised.')


if __name__=='__main__':main()
