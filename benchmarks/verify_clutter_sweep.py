"""Held-out checks: actual saved I/Q must reproduce maps; the ridge blocks far ground.

This is an offline observer audit, not receiver input or a simulator dependency
on a skill algorithm. Run after the complete default sampling sweep.
"""
from pathlib import Path
import json
import numpy as np
import argparse
parser=argparse.ArgumentParser(description='Verify all 30 saved clutter I/Q maps and the highest-budget mesh shadow.')
parser.add_argument('--input',type=Path,required=True)
parser.add_argument('--output',type=Path,help='Writable verification report directory (default: input directory)')
args=parser.parse_args();out=args.input;dest=args.output or out;dest.mkdir(parents=True,exist_ok=True)
s=json.loads((out/'summary.json').read_text());assert len(s['cases'])==30
assert {(r['geometry'],r['exponent']) for r in s['cases']}=={(g['name'],e) for g in s['geometries'] for e in range(10,20)}
results=[]
for r in s['cases']:
 with np.load(out/r['data_file']) as d:
  assert d['analog_iq_volts'].shape==d['adc_iq_volts'].shape==(25600,)
  assert d['analog_dbv2'].shape==d['adc_dbv2'].shape==(128,64)
  for k in d.files:assert np.isfinite(d[k]).all()
  assert np.all(np.diff(d['range_m'])>0) and np.all(np.diff(d['doppler_khz'])>0)
  assert r['clipped_components']==0 and 0<r['retained_first_chirp']<=r['proposed_samples']
  assert np.isclose(r['raw_RCS_sum_m2'],.01*r['surface_area_m2'],rtol=1e-12)
  # Recompute the external processor's FFT directly from saved sensor data.
  for kind in ['analog','adc']:
   gate=d[kind+'_iq_volts'].reshape(64,400)[:,30:286];gate=gate-gate.mean(axis=1,keepdims=True)
   ft=np.fft.fftshift(np.fft.fft2(gate*np.hanning(64)[:,None]*np.hanning(256)),axes=0)[:,:128]
   db=(10*np.log10(np.maximum(abs(ft)**2/(np.hanning(64).sum()*np.hanning(256).sum())**2,np.finfo(float).tiny))).T
   visible=db>s['plot_limits_dbv2'][0]-20
   np.testing.assert_allclose(db[visible],d[kind+'_dbv2'][visible],atol=2e-10)
  linear=10**(d['analog_dbv2']/10);f=d['doppler_khz']
  negative=float(linear[:,f<0].sum()/linear.sum());positive=float(linear[:,f>0].sum()/linear.sum())
  results.append({'geometry':r['geometry'],'proposed_samples':r['proposed_samples'],'negative_Doppler_power_fraction':negative,'positive_Doppler_power_fraction':positive})
for name in [g['name'] for g in s['geometries']]:
 for e in [10,19]:
  print(next(r for r in results if r['geometry']==name and r['proposed_samples']==2**e))
(dest/'validation.json').write_text(json.dumps({'status':'passed','cases_checked':30,'checks':['complete power-of-two sweep for three geometries','finite I/Q and maps','64 chirps with preserved 40 us PRI gates','range-major 128x64 matrices','increasing physical axes','zero ADC clipping','RCS per area invariant across budgets','both map types reproduce independent FFT from saved I/Q throughout display span plus 20 dB'],'power_by_Doppler_sign':results},indent=2)+'\n')

import mitsuba as mi
mi.set_variant('llvm_ad_mono_polarized')
import drjit as dr
dr.set_thread_count(2)
import sionna.rt as rt
from airsim_rf.geometry import export_sionna_geometry
from airsim_rf.fmcw import IWR1843Profile
from airsim_rf.radar_scattering import TerrainBackscatter,segment_visibility
s=json.loads((out/'summary.json').read_text());records=[]
with tempfile.TemporaryDirectory(prefix='verify-clutter-shadow-') as td:
 for spec in s['geometries']:
  bundle=Path(td)/spec['name'];export_sionna_geometry(spec['geometry'],bundle)
  scene=rt.load_scene(str(bundle/'scene.xml'),merge_shapes=False)
  c=TerrainBackscatter(scene,{'enabled':True,'seed':314159,'materials':{'earth':{'sigma0_db':-20.,'incidence_exponent':1.}},'shape_materials':{'obj_Terrain':'earth'}},samples_per_link=524288)
  points,rcs,weights=c.candidates(spec['position_m'],250.)
  delta=points-spec['position_m'];distance=np.linalg.norm(delta,axis=1)
  eligible=IWR1843Profile().antenna_power_gain(delta/distance[:,None],spec['orientation_rad'])>0
  points=points[eligible];visible=segment_visibility(scene,spec['position_m'],points)
  record={'geometry':spec['name'],'budget':524288,'front_face_in_range':len(delta),'antenna_eligible':len(points),'mesh_blocked':int((~visible).sum()),'retained':int(visible.sum())}
  expected=next(r for r in s['cases'] if r['geometry']==spec['name'] and r['exponent']==19)['retained_first_chirp']
  assert record['retained']==expected
  if spec['name']=='ridge-shadow':
   far=(points[:,0]>40)&(abs(points[:,2])<1e-6)
   record.update(far_flat_eligible=int(far.sum()),far_flat_visible=int((far&visible).sum()))
   assert far.sum()>0 and not (far&visible).any()
  records.append(record)
(dest/'visibility-verification.json').write_text(json.dumps({'status':'passed','scope':'first chirp, highest budget; independent direct segment checks on exact experimental mesh','cases':records},indent=2)+'\n')
print(json.dumps(records))
