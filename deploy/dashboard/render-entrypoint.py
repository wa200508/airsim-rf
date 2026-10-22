"""One X server and one Unreal process; bounded display readiness."""
import os
from pathlib import Path
import subprocess
import time

server=subprocess.Popen(['Xvfb',':98','-ac','-screen','0','1280x720x24','-nolisten','tcp'],stdout=open('/tmp/xvfb.log','w'),stderr=subprocess.STDOUT)
for _ in range(100):
    if server.poll() is not None: raise SystemExit('Xvfb failed: '+Path('/tmp/xvfb.log').read_text())
    if Path('/tmp/.X11-unix/X98').exists():break
    time.sleep(.1)
else:raise SystemExit('Xvfb readiness timeout')
os.environ['DISPLAY']=':98'
os.environ.setdefault('VK_ICD_FILENAMES','/usr/share/vulkan/icd.d/lvp_icd.json')
executable=Path(os.environ.get('RF_BLOCKS_DIR','/blocks'))/'Blocks/Binaries/Linux/Blocks-Linux-Shipping'
os.execv(str(executable),['Blocks','Blocks','-RenderOffscreen','-vulkan','-sm5','-AllowCPUDevices','-nosound','-unattended','-stdout','-FullStdOutLogOutput','-userdir=/tmp/airsim-user'])
