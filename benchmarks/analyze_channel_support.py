"""Measured delay/Doppler support, not a real-time or GPU benchmark."""
import json
from pathlib import Path
import numpy as np
import drjit as dr
import mitsuba as mi
mi.set_variant('llvm_ad_mono_polarized')
dr.set_thread_count(2)
import sionna.rt as rt
from airsim_rf.sdr import PlutoSDRProfile, SDREmitter, SDRNetworkReceiver
from airsim_rf.rendering import ToneWaveform
import argparse
parser=argparse.ArgumentParser(description='Inspect delay/Doppler support of the existing 100-TX terrain channel; no I/Q rendering.')
parser.add_argument('--output-dir',type=Path,default=Path('research_results/affordable_realtime'))
args=parser.parse_args()
args.output_dir.mkdir(parents=True,exist_ok=True)
root=Path(__file__).resolve().parents[1]
scene=rt.load_scene(str(root/'benchmarks/scenes/terrain.xml'))
scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='hw_dipole',polarization='V')
scene.rx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='hw_dipole',polarization='V')
emitters={}
for i,y in enumerate(np.linspace(-25,25,100)):
 name=f'beacon_{i}'
 scene.add(rt.Transmitter(name,position=[0,float(y),10],velocity=[1,0,0]))
 emitters[name]=SDREmitter(ToneWaveform(0.))
scene.add(rt.Receiver('listener',position=[-30,-10,14],velocity=[3,0,0]))
receiver=SDRNetworkReceiver(scene,emitters,PlutoSDRProfile(),samples_per_link=1028)
paths=receiver.solver(scene,max_depth=1,seed=42,diffuse_reflection=True,refraction=False,
 samples_per_src=1028,max_num_paths_per_src=1+receiver.planes+1028)
a,tau=paths.cir(num_time_steps=1,normalize_delays=False,out_type='numpy')
tau=tau[0,0,:,0,:] if tau.ndim==5 else tau[0]
fd=paths.doppler.numpy().reshape(tau.shape)
valid=tau>=0
spans=[float(np.ptp(t[v])) for t,v in zip(tau,valid) if v.any()]
result=dict(scope='100 TX, 1 RX, first epoch of existing terrain benchmark, CPU channel export only',
 carrier_hz=915e6,sample_rate_hz=2e6,attempts_per_link=1028,retained_paths=int(valid.sum()),
 max_path_doppler_hz=float(np.max(abs(fd[valid]))),
 absolute_delay_us=dict(min=float(tau[valid].min()*1e6),max=float(tau[valid].max()*1e6)),
 link_delay_spread_us=dict(min=min(spans)*1e6,max=max(spans)*1e6,median=float(np.median(spans)*1e6)),
 max_delay_span_samples_2MSps=max(spans)*2e6,
 stage_timings_ms=receiver.solver.stage_timings,
 path_count_per_link=dict(min=int(valid.sum(axis=1).min()),max=int(valid.sum(axis=1).max())))
print(json.dumps(result,indent=2))
(args.output_dir/'channel_support.json').write_text(json.dumps(result,indent=2)+'\n')
np.savez(args.output_dir/'channel_support_paths.npz',a=a[0,0,:,0,:,0],tau=tau,fd=fd)
