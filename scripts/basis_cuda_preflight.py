"""Verify actual CuPy FP64 projection/FFT execution, independent of OptiX."""
import argparse
import json
from pathlib import Path
import traceback

import numpy as np

from airsim_rf.batched_rendering import PathRenderJob
from airsim_rf.sampled_waveform import SampledWaveform
from airsim_rf.research.doppler_basis import DopplerBasisRenderer
from airsim_rf.research.doppler_basis_cuda import CudaDopplerBasisRenderer

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,required=True)
args=p.parse_args()
result=dict(status='blocked',scope='renderer_cuda_only',propagation='not tested; current Dr.Jit rejects P100')
try:
    rng=np.random.default_rng(42)
    wave=SampledWaveform(rng.normal(size=1024)+1j*rng.normal(size=1024),2e6,-200000)
    job=PathRenderJob(np.array([1.+.2j,-.3+.4j]),np.array([30e-6,80e-6]),np.array([1700.,-2500.]),wave)
    cfg=dict(sample_rate_hz=2e6,max_delay_s=100e-6,max_doppler_hz=2500)
    engine=CudaDopplerBasisRenderer(**cfg)
    actual=engine.render([job],num_samples=256,profile=True)
    expected=DopplerBasisRenderer(**cfg).render([job],num_samples=256)
    np.testing.assert_allclose(actual,expected,rtol=2e-9,atol=2e-9)
    cp=engine.cp
    props=cp.cuda.runtime.getDeviceProperties(cp.cuda.runtime.getDevice())
    name=props['name'].decode() if isinstance(props['name'],bytes) else props['name']
    if not any(e['name']=='basis.path_projection' and e['cuda_ms']>0 for e in engine.last_metrics['events']):
        raise RuntimeError('No timed CUDA projection execution')
    result.update(status='verified_cuda_cupy',gpu=name,compute_capability=f"{props['major']}.{props['minor']}",
        cupy_version=cp.__version__,cuda_runtime_version=cp.cuda.runtime.runtimeGetVersion(),
        cuda_driver_version=cp.cuda.runtime.driverGetVersion(),metrics=engine.last_metrics,
        max_absolute_error=float(np.max(abs(actual-expected))))
except Exception as exc:
    result.update(error=str(exc),traceback=traceback.format_exc())
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['status']=='verified_cuda_cupy' else 20)
