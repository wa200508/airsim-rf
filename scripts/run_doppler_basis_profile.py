"""Collect CPU/CuPy Doppler-basis renderer timings and a publishable report."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from time import monotonic

from run_gpu_profile import ROOT, Telemetry, dump, environment, probe


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-root',type=Path,default=ROOT/'results/profiling')
    p.add_argument('--run-id',default='p100-basis-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    p.add_argument('--quick',action='store_true',help='Fewer captures; paths and sample budgets unchanged')
    p.add_argument('--cpu-only',action='store_true',help='Harness validation, no CUDA claim')
    p.add_argument('--tx',type=int,nargs='+',default=[1,4,100])
    p.add_argument('--rx',type=int,default=1,help='Receivers processed sequentially on the selected device')
    p.add_argument('--samples',type=int,default=16667)
    p.add_argument('--paths',type=int,default=1028)
    p.add_argument('--block-samples',type=int,default=2048)
    p.add_argument('--batch-links',type=int,default=8)
    p.add_argument('--projection',choices=('gather','warp','dense'),default='gather')
    p.add_argument('--delay-map', choices=('double','single'), default='double')
    p.add_argument('--fft-inplace', action='store_true')
    p.add_argument('--max-delay-us',type=float,default=100.)
    p.add_argument('--max-doppler-hz',type=float,default=2500.)
    p.add_argument('--tolerance',type=float,default=1e-10)
    p.add_argument('--taps',type=int,default=32)
    p.add_argument('--threads',type=int,default=2)
    p.add_argument('--iterations',type=int,default=30)
    p.add_argument('--warmup',type=int,default=3)
    p.add_argument('--no-nsys',action='store_true')
    p.add_argument('--no-telemetry',action='store_true')
    args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}',args.run_id):
        p.error('Use a filename-safe run-id')
    if min(args.tx+[args.rx,args.samples,args.paths,args.block_samples,args.batch_links,args.threads,args.iterations])<1 or args.warmup<0:
        p.error('Positive counts and nonnegative warmup required')
    output=(args.output_root/args.run_id).resolve()
    output.mkdir(parents=True,exist_ok=False)
    for directory in ('metrics','profiles','logs','raw'):(output/directory).mkdir()
    manifest=dict(run_id=args.run_id,scope='doppler_basis_renderer',started_utc=datetime.now(timezone.utc).isoformat(),
        arguments={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},tasks=[],complete=False,
        gpu_status='not_requested' if args.cpu_only else 'pending',
        propagation_status='excluded; current pinned Dr.Jit does not support P100; legacy results retained separately')
    dump(output/'environment.json',environment())
    packages=probe([sys.executable,'-m','pip','list','--format=json'])
    dump(output/'installed_packages.json',json.loads(packages['stdout']) if packages.get('returncode')==0 else packages)
    telemetry=Telemetry(output/'raw/gpu_telemetry.csv')
    if not args.no_telemetry:telemetry.start()
    failed=False

    def run(name,command,artifact=None,required=True):
        nonlocal failed
        print(f'[{name}] starting',flush=True)
        task=dict(name=name,command=[str(c) for c in command],required=required,status='running',
                  artifact=str(artifact.relative_to(output)) if artifact else None,log=f'logs/{name}.log')
        manifest['tasks'].append(task);dump(output/'manifest.json',manifest)
        started=monotonic()
        try:
            with (output/task['log']).open('w') as stream:
                child=subprocess.Popen(task['command'],stdout=stream,stderr=subprocess.STDOUT,cwd=ROOT)
                while True:
                    try:
                        code=child.wait(timeout=15);break
                    except subprocess.TimeoutExpired:
                        print(f'[{name}] running for {monotonic()-started:.0f}s',flush=True)
                    except BaseException:
                        child.terminate()
                        try:child.wait(timeout=10)
                        except subprocess.TimeoutExpired:child.kill();child.wait()
                        raise
                task['returncode']=code
                task['status']='ok' if code==0 and (artifact is None or artifact.is_file()) else 'failed'
        except OSError as exc:
            task.update(status='failed',error=str(exc))
        task['wall_seconds']=monotonic()-started
        failed |= required and task['status']!='ok'
        dump(output/'manifest.json',manifest)
        print(f'[{name}] {task["status"]}',flush=True)
        return task['status']=='ok'

    try:
        if os.environ.get('CUDA_LAUNCH_BLOCKING','0') not in ('','0'):
            raise RuntimeError('Disable CUDA_LAUNCH_BLOCKING for timing collection')
        available=False
        if not args.cpu_only:
            artifact=output/'profiles/basis_cuda_preflight.json'
            available=run('basis_cuda_preflight',[sys.executable,ROOT/'scripts/basis_cuda_preflight.py','--output',artifact],artifact)
            manifest['gpu_status']='verified_cuda_cupy' if available else 'blocked'
        if available:
            run('basis_cuda_correctness',[sys.executable,'-m','pytest',ROOT/'tests/test_doppler_basis_cuda.py','-q'])
        else:
            run('basis_cpu_correctness',[sys.executable,'-m','pytest',ROOT/'tests/test_doppler_basis.py',
                                        ROOT/'tests/test_doppler_basis_cuda.py','-q'])
        for tx in dict.fromkeys(args.tx):
            common=['--tx',str(tx),'--rx',str(args.rx),'--samples',str(args.samples),'--paths',str(args.paths),
                    '--block-samples',str(args.block_samples),'--batch-links',str(args.batch_links),'--projection',args.projection,
                    '--max-delay-us',str(args.max_delay_us),'--max-doppler-hz',str(args.max_doppler_hz),
                    '--tolerance',str(args.tolerance),'--taps',str(args.taps),'--threads',str(args.threads),'--delay-map',args.delay_map]
            if args.fft_inplace:
                common.append('--fft-inplace')
            for backend in (['cpu','cuda'] if available else ['cpu']):
                name=f'basis_{backend}_{tx}tx_{args.rx}rx'
                artifact=output/'profiles'/f'{name}.json'
                command=[sys.executable,ROOT/'benchmarks/benchmark_doppler_basis_gpu.py','--backend',backend,*common,
                         '--iterations','2' if args.quick else str(args.iterations),
                         '--warmup','1' if args.quick else str(args.warmup),'--output',artifact]
                run(name,command,artifact)
                if backend=='cuda' and tx==max(args.tx) and not args.no_nsys:
                    nsys=os.environ.get('NSYS_BIN') or shutil.which('nsys')
                    if nsys:
                        stem=output/'raw'/f'nsys_{name}'
                        trace=output/'profiles'/f'{name}_nsys.json'
                        prof=[sys.executable,ROOT/'benchmarks/benchmark_doppler_basis_gpu.py','--backend','cuda',*common,
                              '--profile-only','--iterations','2','--warmup','1','--output',trace]
                        captured=run(f'nsys_{name}',[nsys,'profile','--trace=cuda,nvtx,osrt','--sample=none','--cpuctxsw=none',
                            '--force-overwrite=true',f'--output={stem}',*prof],trace,required=False)
                        if captured:
                            run(f'nsys_{name}_stats',[nsys,'stats','--report','cuda_gpu_kern_sum,cuda_api_sum,nvtx_sum',
                                str(stem)+'.nsys-rep'],required=False)
                    else:
                        manifest['tasks'].append(dict(name=f'nsys_{name}',status='unavailable',required=False,
                                                      reason='Nsight absent; separate CUDA-event stage spans still collected'))
        manifest['complete']=True
    except (Exception,KeyboardInterrupt) as exc:
        failed=True;manifest['error']=f'{type(exc).__name__}: {exc}'
    finally:
        telemetry.finish()
        manifest.update(required_tasks_passed=not failed,finished_utc=datetime.now(timezone.utc).isoformat())
        dump(output/'manifest.json',manifest)
        aggregate=probe([sys.executable,ROOT/'scripts/aggregate_gpu_profile.py',output])
        if aggregate.get('returncode')!=0:
            failed=True;print(aggregate,flush=True)
        print(f'Bundle: {output}',flush=True)
    return 20 if failed else 0


if __name__=='__main__':raise SystemExit(main())
