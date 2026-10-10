import json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'benchmarks')
import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
from airsim_rf.p100_compat import enable_pascal_compat
enable_pascal_compat()
from terrain_scan import TerrainScan,scan_scene
rows=[]
for name in ('ground','terrain'):
 scene,_=scan_scene(name)
 gpu=TerrainScan(scene,renderer='direct-cuda')
 for position,epoch in [([-75,-50,40],0.),([0,0,40],9.),([75,50,40],18.)]:
  actual,_,paths=gpu.capture(position,velocity=[8.32,5.55,0],epoch_s=epoch)
  reference=TerrainScan(scene,renderer='numpy')
  expected,_=reference.voltage_from_channel(*gpu.last_channel,epoch_s=epoch)
  error=float(np.linalg.norm(actual-expected)/max(np.linalg.norm(expected),1e-30))
  rows.append({'scene':name,'epoch_s':epoch,'paths':paths,'relative_l2_error':error,'max_absolute_error_v':float(np.max(np.abs(actual-expected)))})
  assert error<1e-5,rows[-1]
print(json.dumps({'scope':'same GPU-traced physical channel; CUDA vs NumPy rendering only','cases':rows,'passed':True},indent=2))
