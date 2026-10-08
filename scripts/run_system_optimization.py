"""Compare full RF pipeline optimizations on one idle GPU, serially."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--iterations', type=int, default=10)
a = p.parse_args()
if a.iterations < 2:
    p.error('At least two timed windows required')
a.output.mkdir(parents=True, exist_ok=False)
manifest = dict(scope='rf_pipeline_optimization_comparison', source_revision=subprocess.check_output(
    ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],text=True).strip(),
    started_utc=datetime.now(timezone.utc).isoformat(), iterations=a.iterations, tasks=[], complete=False)
def save():
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
def run(name, threads, optimized, fused=False):
    output = a.output/name
    command = [sys.executable, str(ROOT/'scripts/basis_launch.py'), str(ROOT/'benchmarks/benchmark_end_to_end.py'),
        '--renderer','basis-cuda','--propagation-backend','cuda','--pascal-compat','--tx','100','--rx','10','--iterations',str(a.iterations),
        '--warmup','3','--threads',str(threads),'--output',str(output)]
    if not optimized:
        command.append('--no-optimizations')
    if fused:
        command.append('--fused-projection')
    task = dict(name=name,threads=threads,optimized=optimized,fused=fused,command=command,status='running')
    manifest['tasks'].append(task);save();print(name,'starting',flush=True)
    tick=time.monotonic()
    with (a.output/(name+'.log')).open('w') as stream:
        code=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
    task.update(returncode=code,wall_s=time.monotonic()-tick,status='ok' if code==0 else 'failed')
    if code == 0:
        data=json.loads((output/'measurements.json').read_text())
        task['summary']=data['summary']
    save();print(name,task['status'],flush=True)
    if code:
        raise SystemExit(code)
    return task
save()
run('baseline_cuda',2,False)
run('persistent_cuda',2,True)
run('fused_cuda',2,True,True)
run('baseline_cuda_repeat',2,False)
manifest.update(complete=True,propagation_backend='Sionna RT CUDA/OptiX')
save()
