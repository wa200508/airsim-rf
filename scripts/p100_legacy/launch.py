import os,sys
from pathlib import Path
libraries=Path('/usr/local/lib/python3.11/site-packages/nvidia')
env=dict(os.environ)
env['LD_LIBRARY_PATH']=':'.join(str(p) for p in libraries.glob('*/lib'))+':'+env.get('LD_LIBRARY_PATH','')
os.execvpe(sys.executable,[sys.executable,*sys.argv[1:]],env)
