"""GPU comparison of angular and fixed-surface incoherent path power."""
import argparse
import json
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--pascal-compat',action='store_true')
args=parser.parse_args()
import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
if args.pascal_compat:
 from airsim_rf.p100_compat import enable_pascal_compat
 enable_pascal_compat()
from airsim_rf.scattering import FirstOrderScatteringPathSolver
import numpy as np
import sionna.rt as rt
from sionna.rt.constants import InteractionType
root=Path(__file__).resolve().parents[1]
scene=rt.load_scene(str(root/'benchmarks/scenes/ground.xml'));scene.frequency=2.4e9
scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V')
scene.rx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V')
scene.add(rt.Transmitter('tx',position=[-5,0,10],orientation=[0,np.pi/2,0],velocity=[1,0,0]))
scene.add(rt.Receiver('rx',position=[5,0,10],orientation=[0,np.pi/2,0],velocity=[0,.5,0]))
rows=[]
for count in (4096,16384):
 for seed in (42,43,44):
  power=[]
  for surface in (False,True):
   paths=FirstOrderScatteringPathSolver(surface_sampling=surface)(scene,samples_per_src=count,max_num_paths_per_src=count+2,los=False,specular_reflection=False,seed=seed)
   a,_=paths.cir(normalize_delays=False,out_type='numpy');a=a[0,0,0,0,:,0]
   diffuse=paths.interactions.numpy()[0,0,0]==int(InteractionType.DIFFUSE)
   power.append(float(np.sum(abs(a[diffuse])**2)))
  rows.append({'samples_per_link':count,'seed':seed,'angular_power_gain':power[0],'surface_power_gain':power[1],'surface_over_angular':power[1]/power[0]})
args.output.write_text(json.dumps({'scope':'2.4 GHz ground fixture; incoherent power, not coherent summed power or hardware calibration','rows':rows},indent=2)+'\n')
print(rows)
