"""Launch Python with the qualified wheel CUDA library paths (Linux)."""
import os
from pathlib import Path
import sys
import sysconfig


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Usage: airsim-rf-cuda <Python arguments>, e.g. -m airsim_rf.live --help')
    os.environ['PYTHONUTF8'] = '1'
    # A locally installed wheel can share its qualified dependencies through
    # venv --system-site-packages. Locate those wheel libraries on Python's
    # actual search path without importing CUDA or mixing separate installations.
    candidates=[Path(sysconfig.get_paths()['purelib'])/'nvidia']
    candidates.extend(Path(path)/'nvidia' for path in sys.path if path)
    root=next((path for path in candidates if (path/'cuda_runtime/lib').is_dir()),candidates[0])
    paths = [str(root/name/'lib') for name in ('cuda_runtime', 'cuda_nvrtc', 'cufft', 'cublas')
             if (root/name/'lib').is_dir()]
    if paths:
        os.environ['LD_LIBRARY_PATH'] = ':'.join(paths+[os.environ.get('LD_LIBRARY_PATH', '')])
    if (root/'cuda_runtime').is_dir():
        os.environ['CUDA_PATH'] = str(root/'cuda_runtime')
    for key, value in (('CUPY_CACHE_DIR','/tmp/cupy-kernel-cache'),('CUDA_CACHE_PATH','/tmp/cuda-kernel-cache')):
        os.environ.setdefault(key,value)
    os.execvpe(sys.executable,[sys.executable,*sys.argv[1:]],os.environ)


if __name__ == '__main__':
    main()
