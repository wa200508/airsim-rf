"""Expose pinned wheel CUDA libraries before starting the renderer collector."""
import os
from pathlib import Path
import sys
import sysconfig

os.environ['PYTHONUTF8'] = '1'
root = Path(sysconfig.get_paths()['purelib'])/'nvidia'
libraries = [root/name/'lib' for name in ('cuda_runtime', 'cuda_nvrtc', 'cufft')]
paths = [str(p) for p in libraries if p.is_dir()]
if paths:
    os.environ['LD_LIBRARY_PATH'] = ':'.join(paths+[os.environ.get('LD_LIBRARY_PATH', '')])
runtime = root/'cuda_runtime'
if runtime.is_dir():
    os.environ.setdefault('CUDA_PATH', str(runtime))
if len(sys.argv) < 2:
    raise SystemExit('Usage: python scripts/basis_launch.py <python-entrypoint> [args...]')
os.execvpe(sys.executable, [sys.executable, *sys.argv[1:]], os.environ)
