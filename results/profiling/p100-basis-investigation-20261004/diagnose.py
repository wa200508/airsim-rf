"""Read-only diagnostic of unchanged renderer math and projection kernel spans."""
import json, math, runpy, sys
from pathlib import Path
from dataclasses import replace
import numpy as np
import cupy as cp
from airsim_rf.batched_rendering import PathRenderJob
from airsim_rf.sampled_waveform import SampledWaveform
import airsim_rf.research.doppler_basis_cuda as module
out=Path('/work/results')
epoch=1790000000000000000; dt=68500; fs=2e6
rng=np.random.default_rng(42)
wave=SampledWaveform(rng.normal(size=3000)+1j*rng.normal(size=3000),fs,epoch-200000)
job=PathRenderJob(np.array([1.,-1.]),np.array([30e-6,30e-6]),np.array([2500.,-2500.]),wave,frequency_offset_hz=12000.)
engine=module.CudaDopplerBasisRenderer(sample_rate_hz=fs,max_delay_s=100e-6,max_doppler_hz=2500)
full=engine.render([job],num_samples=1025,sim_time_ns=epoch,channel_epoch_ns=epoch)[0]
right=engine.render([job],num_samples=888,sim_time_ns=epoch+dt,channel_epoch_ns=epoch)[0]
base=(job.frequency_offset_hz*(epoch*1e-9))%1
split=(job.frequency_offset_hz*((epoch+dt)*1e-9))%1
expected_local=job.frequency_offset_hz*dt*1e-9
phase_error=2*math.pi*(split-base-expected_local)
def relative(actual,expected):return float(np.linalg.norm(actual-expected)/np.linalg.norm(expected))
zero=replace(job,frequency_offset_hz=0.)
zfull=engine.render([zero],num_samples=1025,sim_time_ns=epoch,channel_epoch_ns=epoch)[0]
zright=engine.render([zero],num_samples=888,sim_time_ns=epoch+dt,channel_epoch_ns=epoch)[0]
diagnosis={'phase_error_rad':phase_error,'predicted_relative_complex_error':abs(np.exp(1j*phase_error)-1),'observed_relative_rms':relative(right,full[137:]),'residual_after_predicted_phase_rotation':relative(right,full[137:]*np.exp(1j*phase_error)),'zero_oscillator_offset_relative_rms':relative(zright,zfull[137:]),'no_renderer_code_changes':True}
(out/'timestamp_diagnosis.json').write_text(json.dumps(diagnosis,indent=2)+'\n')
Original=module.CudaDopplerBasisRenderer
class Instrumented(Original):
    def __init__(self,**kw):
        super().__init__(**kw)
        self.measure=False;self.kernel_pairs=[]
        for name in ('project','reconstruct'):
            original=getattr(self,name)
            def wrapped(*args,_fn=original,_name=name,**kw):
                if not self.measure:return _fn(*args,**kw)
                begin,end=cp.cuda.Event(),cp.cuda.Event();begin.record()
                value=_fn(*args,**kw);end.record();self.kernel_pairs.append((_name,begin,end));return value
            setattr(self,name,wrapped)
    def render(self,*args,**kw):
        self.measure=kw.get('profile',False);self.kernel_pairs=[]
        result=super().render(*args,**kw)
        if self.measure:
            pairs=[{'kernel':name,'cuda_event_ms':float(cp.cuda.get_elapsed_time(a,b))} for name,a,b in self.kernel_pairs]
            stats={name:{'launches':sum(p['kernel']==name for p in pairs),'sum_event_ms':sum(p['cuda_event_ms'] for p in pairs if p['kernel']==name)} for name in ('project','reconstruct')}
            (out/'kernel_diagnosis.json').write_text(json.dumps({'kernels':stats,'events':pairs,'note':'Events immediately surround warmed raw-kernel calls; excludes array allocation and surrounding stage work. Small host dispatch gaps may remain. Separate instrumented capture, not throughput timing.','profile_wall_ms':self.last_metrics['total_ms']},indent=2)+'\n')
        return result
module.CudaDopplerBasisRenderer=Instrumented
sys.argv=['/opt/airsim-rf/benchmarks/benchmark_doppler_basis_gpu.py','--backend','cuda','--tx','100','--batch-links','8','--iterations','3','--warmup','3','--output','/work/results/kernel_capture.json']
runpy.run_path(sys.argv[0],run_name='__main__')
