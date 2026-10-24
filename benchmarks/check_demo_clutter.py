"""Held-out ADC check of low-terrain radar and DF demo settings.

Actual source I/Q and independent radar FFT; no scene truth is sent to a skill.
This is a CPU snapshot audit, not an end-to-end flight or GPU timing benchmark.
"""
from pathlib import Path
from copy import deepcopy
import json
import tempfile
import time
import numpy as np
import mitsuba as mi
mi.set_variant('llvm_ad_mono_polarized')
import drjit as dr
dr.set_thread_count(2)
import sionna.rt as rt
from airsim_rf.dashboard_scenario import prepare
from airsim_rf.dashboard_radar import RadarWindowReceiver
from radar_skill.processing import range_doppler
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import argparse
from hashlib import sha256
parser=argparse.ArgumentParser(description='Check noisy ADC clutter on planned low-terrain demo routes; CPU observer audit, not native flight timing.')
parser.add_argument('--output',type=Path,default=Path('demo-clutter-check'))
args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
kin=lambda p,v:{'pose':{'position':dict(zip(('x','y','z'),np.asarray(p)*[1,-1,-1])),'orientation':{'w':1.,'x':0.,'y':0.,'z':0.}},'twist':{'linear':dict(zip(('x','y','z'),np.asarray(v)*[1,-1,-1])),'angular':{'x':0.,'y':0.,'z':0.}}}
summary={'scope':'planned low-altitude route snapshots, actual source ADC I/Q and external FFT, CPU; no AirSim dynamics/camera or GPU timing claim','cases':[]}
with tempfile.TemporaryDirectory(prefix='low-demo-') as td:
 run=Path(td);prepare(run,scenario_dir='mmwave-radar',duration_s=.004)
 c=json.loads((run/'runtime.json').read_text());a=json.loads((run/'arrays.json').read_text());route=np.asarray(c['compiled_routes_rf_m']['RadarDrone'])
 scene=rt.load_scene(str(run/'bundle/scene.xml'),merge_shapes=False)
 for name,xy in [('start',[-200,0]),('east-pass',[150,0]),('west-turn',[-240,-150]),('return',[0,-160])]:
  i=np.linalg.norm(route[:,:2]-xy,axis=1).argmin();p=route[i];v=route[min(i+1,len(route)-1)]-p
  if np.linalg.norm(v)<1e-8:v=p-route[i-1]
  v=v/np.linalg.norm(v)*20;maps={}
  for offset in [0.,-15.,-25.]:
   modes=['full','clutter','noise'];cache={}
   for mode in modes:
    radio=deepcopy(c['radios']);radio['radar']['profile']['noise_power_offset_db']=offset
    radio['radar']['clutter']['enabled']=mode!='noise'
    r=RadarWindowReceiver(scene,radio,deepcopy(a));r.control.configure(c['skill']['mode_config']);r.control.set_state({'transmit':True,'receive':True});r.update({'RadarDrone':kin(p,v)})
    if mode!='full':r.targets=[]
    cap=r.capture(0,num_samples=40000)['radar_rx0'];rd=range_doppler(cap.adc_iq_volts,a['sample_rate_hz'],a['carrier_hz'],a['acquisition'])
    cache[mode]=(rd,cap,r)
   noise_floor=cache['noise'][0]['median_bin_power_dbv2'];clutter=cache['clutter'][0]
   values=np.asarray(clutter['power_db'])+clutter['median_bin_power_dbv2']-noise_floor
   full=np.asarray(cache['full'][0]['power_db'])+cache['full'][0]['median_bin_power_dbv2']-noise_floor
   maps[offset]=(values,full,clutter)
   record={'viewpoint':name,'position_rf_m':p.tolist(),'velocity_rf_m_s':v.tolist(),'noise_power_offset_db':offset,'strongest_clutter_plus_noise_bin_vs_noise_median_db':float(values.max()),'noise_only_median_bin_dbv2':noise_floor,'clutter_echoes':cache['clutter'][1].retained_paths['terrain_echoes'],'full_scene_clipped_fraction':cache['full'][1].clipped_component_fraction}
   summary['cases'].append(record);print(json.dumps(record),flush=True)
  fig,axes=plt.subplots(2,3,figsize=(15,8),sharex=True,sharey=True,layout='constrained')
  for col,offset in enumerate([0.,-15.,-25.]):
   values,full,rd=maps[offset]
   for row,data in enumerate([values,full]):
    ax=axes[row,col];im=ax.pcolormesh(rd['doppler_khz'],rd['range_m'],data,shading='nearest',vmin=-5,vmax=35,cmap='viridis',rasterized=True)
    ax.set(xlim=(-12.5,12.5),ylim=(0,400),xlabel='Doppler (kHz)',ylabel='Apparent range (m)',title=f'{"Clutter + noise" if row==0 else "Full scene + noise"}: {offset:g} dB noise offset')
    ax.tick_params(labelbottom=True,labelleft=True)
  fig.colorbar(im,ax=list(axes.flat),label='dB relative to matched noise-only ADC-map median')
  fig.suptitle(name+': low terrain route, actual ADC output, shared contrast scale');fig.savefig(out/(name+'.png'),dpi=130);plt.close(fig)
 summary['input_sha256']=c['input_sha256'];summary['profile']=c['radios']['radar']['profile']
# Exercise the second demo's eight receiver streams using the same compiled
# low route and physical source; direct NumPy is only an evaluation backend.
from airsim_rf.dashboard_scenario import create_receiver,WaveformSource
summary['direction_finding_cases']=[]
with tempfile.TemporaryDirectory(prefix='low-df-demo-') as td:
 run=Path(td);prepare(run,scenario_dir='drone-orbit',duration_s=.12)
 c=json.loads((run/'runtime.json').read_text());arrays=json.loads((run/'arrays.json').read_text());radio=deepcopy(c['radios'])
 radio['propagation']['renderer']='numpy';route=np.asarray(c['compiled_routes_rf_m']['OrbitDrone'])
 source={t['id']:WaveformSource(run/'scenario-input',t['waveform'],radio['sample_rate_hz']) for t in radio['transmitters']}
 for name,xy in [('east',[250,0]),('north',[0,250]),('west',[-250,0]),('south',[0,-250])]:
  i=np.linalg.norm(route[:,:2]-xy,axis=1).argmin();p=route[i];v=route[i+1]-p;v=v/np.linalg.norm(v)*25
  scene=rt.load_scene(str(run/'bundle/scene.xml'),merge_shapes=False);receiver=create_receiver(scene,radio,deepcopy(arrays),source,0,8192)
  scene.transmitters['tx0'].position=p.tolist();scene.transmitters['tx0'].velocity=v.tolist()
  capture=receiver.capture(0,num_samples=8192)
  assert len(capture)==8 and all(np.isfinite(cap.adc_iq_volts).all() for cap in capture.values())
  record={'viewpoint':name,'position_rf_m':p.tolist(),'noise_power_offset_db':radio['receiver_profile']['noise_power_offset_db'],
          'channels':len(capture),'samples_per_channel':8192,'path_diagnostics':receiver.last_path_diagnostics,
          'max_ADC_clipped_fraction':max(cap.clipped_component_fraction for cap in capture.values()),
          'thermal_noise_power_w_by_channel':{n:cap.thermal_noise_power_w for n,cap in capture.items()}}
  summary['direction_finding_cases'].append(record);print(json.dumps(record),flush=True)
 summary['direction_finding_input_sha256']=c['input_sha256']
summary['source_sha256']={n:sha256(Path(__import__(n,fromlist=['x']).__file__).read_bytes()).hexdigest() for n in ['airsim_rf.fmcw','airsim_rf.sdr','airsim_rf.dashboard_scenario','airsim_rf.terrain','radar_skill.processing']}
summary['software']={'sionna_rt':rt.__version__,'numpy':np.__version__,'mitsuba':mi.__version__}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
