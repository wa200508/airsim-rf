"""Exploratory time-varying FIR accuracy check against ideal periodic delay."""
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.signal import firwin

import argparse
parser=argparse.ArgumentParser(description='One-link arbitrary sampled-waveform accuracy experiment; no production renderer.')
parser.add_argument('--input-dir',type=Path,default=Path('research_results/affordable_realtime'))
parser.add_argument('--doppler-scale',type=float,default=1.)
parser.add_argument('--knot-ms',type=float,nargs='+',default=[.5,1.,2.])
parser.add_argument('--output-name',default='ltv_validation.json')
args=parser.parse_args()
if not np.isfinite(args.doppler_scale) or args.doppler_scale <= 0 or any(not np.isfinite(v) or v <= 0 for v in args.knot_ms):
 parser.error('Positive finite Doppler scale and knot spacings required')
root=args.input_dir
paths=np.load(root/'channel_support_paths.npz')
valid=paths['tau'][0]>=0
a=paths['a'][0][valid].astype(np.complex128)
d=paths['tau'][0][valid].astype(float)*2e6
fd=paths['fd'][0][valid].astype(float)*args.doppler_scale
fs=2e6;n=16667;t=np.arange(n)/fs
rng=np.random.default_rng(42)
# A full block of arbitrary complex samples, bandlimited in the DFT domain.
f=np.fft.fftfreq(n)
spectrum=rng.normal(size=n)+1j*rng.normal(size=n)
spectrum[np.abs(f)>.24]=0.
x=np.fft.ifft(spectrum);x/=np.sqrt(np.mean(abs(x)**2));spectrum=np.fft.fft(x)
start=perf_counter();reference=np.zeros(n,dtype=np.complex128)
for gain,delay,doppler in zip(a,d,fd):
 reference+=gain*np.fft.ifft(spectrum*np.exp(-2j*np.pi*f*delay))*np.exp(2j*np.pi*doppler*t)
reference_ms=1000*(perf_counter()-start)
rows=[]
for taps in (16,32,64):
 # Sample indices shared by all rays in this link; full delay spread retained.
 indices=np.arange(-taps//2+1,int(np.ceil(max(d)))+taps//2+1)
 dist=indices[:,None]-d[None,:]
 weights=np.sinc(dist)*np.where(abs(dist)<=taps/2,np.i0(8.6*np.sqrt(np.maximum(0,1-(dist/(taps/2))**2)))/np.i0(8.6),0.)
 weights/=weights.sum(axis=0,keepdims=True)
 for dt in [ms*1e-3 for ms in args.knot_ms]:
  knots=np.arange(0,t[-1]+dt,dt)
  start=perf_counter();h=(weights*a)@np.exp(2j*np.pi*fd[:,None]*knots[None,:])
  channel_ms=1000*(perf_counter()-start)
  start=perf_counter();hn=CubicSpline(knots,h,axis=1)(t)
  out=np.zeros(n,dtype=np.complex128)
  for k,row in zip(indices,hn):out+=row*np.roll(x,int(k))
  rendering_ms=1000*(perf_counter()-start)
  err=np.sum(abs(out-reference)**2)/np.sum(abs(reference)**2)
  rows.append(dict(interpolation_support=taps,filter_coefficients=len(indices),knot_spacing_ms=dt*1000,
   channel_construction_ms=channel_ms,rendering_ms=rendering_ms,nmse_db=float(10*np.log10(err)),
   rms_evm_percent=float(100*np.sqrt(err))))
result=dict(scope='One real 100-TX terrain link; 8.3335 ms continuous arbitrary periodic bandlimited complex samples; CPU mathematical experiment, not full pipeline benchmark',
 paths=len(a),sample_rate_hz=fs,num_samples=n,signal_frequency_band_hz=[-.24*fs,.24*fs],
 doppler_scale=args.doppler_scale,max_doppler_hz=float(max(abs(fd))),ideal_fractional_delay_fft_reference_ms=reference_ms,rows=rows,
 limitations=['One link only, not 1000 links','Periodic waveform permits exact FFT fractional-delay reference; production needs streaming overlap/history','Cubic interpolation tested only for the chosen fixed Dopplers and this delay/gain realization','FP64 NumPy, not a GPU implementation','Full sample-expanded h used for validation only, production must fuse coefficient reconstruction and convolution'])
(root/args.output_name).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
