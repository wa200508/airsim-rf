"""Collect a sequential, reproducible CPU/CUDA profiling bundle and Markdown report."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data,indent=2)+'\n')


def probe(command):
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=30)
        return {'command':command,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    except (OSError,subprocess.TimeoutExpired) as exc:
        return {'command':command,'returncode':None,'error':str(exc)}


def read_optional(path):
    try: return Path(path).read_text().strip()
    except OSError: return None


def environment():
    revision=probe(['git','-C',str(ROOT),'rev-parse','HEAD'])
    status=probe(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=no'])
    files=[ROOT/'sources.json',ROOT/'requirements-lock.txt']
    for directory in ('src','scripts','benchmarks'):
        files.extend(p for p in (ROOT/directory).rglob('*.py') if '__pycache__' not in p.parts)
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    return dict(utc=datetime.now(timezone.utc).isoformat(), hostname=socket.gethostname(),
        platform=platform.platform(), python=sys.version, python_executable=sys.executable,
        source_revision=os.environ.get('RF_PROFILE_SOURCE_REV') or revision.get('stdout','').strip(),
        source_dirty=os.environ.get('RF_PROFILE_SOURCE_DIRTY') or bool(status.get('stdout','').strip()),
        source_file_sha256=hashes, sources=json.loads((ROOT/'sources.json').read_text()),
        cpu_count=os.cpu_count(), cpu_quota=read_optional('/sys/fs/cgroup/cpu.max'),
        memory_limit=read_optional('/sys/fs/cgroup/memory.max'),
        runtime_environment={k:os.environ.get(k) for k in ('CUDA_VISIBLE_DEVICES','NVIDIA_VISIBLE_DEVICES',
            'NVIDIA_DRIVER_CAPABILITIES','CUDA_LAUNCH_BLOCKING','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')},
        gpu=probe(['nvidia-smi','--query-gpu=index,uuid,name,driver_version,memory.total,compute_cap','--format=csv']),
        gpu_detail=probe(['nvidia-smi','-q']), cpu=probe(['lscpu','--json']),
        nsys=probe([os.environ.get('NSYS_BIN','nsys'),'--version']))


class Telemetry:
    def __init__(self, path):
        self.path=path
        self.stop=threading.Event()
        self.thread=None

    def start(self):
        if not shutil.which('nvidia-smi'): return
        self.thread=threading.Thread(target=self.collect,daemon=True)
        self.thread.start()

    def collect(self):
        fields='timestamp,index,uuid,memory.used,memory.total,utilization.gpu,power.draw,temperature.gpu,clocks.sm'
        with self.path.open('w') as output:
            output.write(fields+'\n')
            while not self.stop.is_set():
                result=probe(['nvidia-smi',f'--query-gpu={fields}','--format=csv,noheader,nounits'])
                if result.get('returncode')==0:
                    output.write(result['stdout']);output.flush()
                else:
                    break
                self.stop.wait(1.)

    def finish(self):
        self.stop.set()
        if self.thread: self.thread.join(timeout=35)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-root',type=Path,default=ROOT/'results/profiling')
    p.add_argument('--run-id',default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+re.sub(r'[^\w.-]','_',socket.gethostname()))
    p.add_argument('--quick',action='store_true',help='Fewer epochs; default ray and sample budgets unchanged')
    p.add_argument('--cpu-only',action='store_true',help='Explicit non-GPU harness validation')
    p.add_argument('--tx',type=int,nargs='+',default=[2,100])
    p.add_argument('--samples',type=int,default=4096)
    p.add_argument('--samples-per-link',type=int,default=1028)
    p.add_argument('--threads',type=int,default=2)
    p.add_argument('--no-example',action='store_true')
    p.add_argument('--no-nsys',action='store_true')
    p.add_argument('--no-telemetry',action='store_true')
    args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}',args.run_id) or args.run_id in ('.','..'):
        p.error('run-id must be a short filename-safe identifier')
    if min(args.tx+ [args.samples,args.threads])<1 or args.samples_per_link<2:
        p.error('Positive counts and >=2 attempts/link required')
    output=(args.output_root/args.run_id).resolve()
    output.mkdir(parents=True,exist_ok=False)
    for sub in ('metrics','profiles','logs','raw'): (output/sub).mkdir()
    manifest=dict(schema_version=1,run_id=args.run_id,started_utc=datetime.now(timezone.utc).isoformat(),
        arguments={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
        tasks=[],gpu_status='not_requested' if args.cpu_only else 'pending',complete=False,
        telemetry_enabled=not args.no_telemetry)
    dump(output/'environment.json',environment())
    packages=probe([sys.executable,'-m','pip','list','--format=json'])
    dump(output/'installed_packages.json',json.loads(packages['stdout']) if packages.get('returncode')==0 else packages)
    telemetry=Telemetry(output/'raw/gpu_telemetry.csv')
    if not args.no_telemetry: telemetry.start()
    required_failure=False
    benchmark=ROOT/'benchmarks/benchmark_sdr_runtime.py'

    def run_task(name,command,artifact=None,required=True):
        print(f'[{name}] starting',flush=True)
        log=output/'logs'/f'{name}.log'
        start=time.monotonic()
        task=dict(name=name,command=[str(x) for x in command],artifact=str(artifact.relative_to(output)) if artifact else None,
            log=str(log.relative_to(output)),required=required,status='running')
        manifest['tasks'].append(task)
        dump(output/'manifest.json',manifest)
        try:
            with log.open('w') as stream:
                child=subprocess.Popen([str(x) for x in command],stdout=stream,stderr=subprocess.STDOUT,cwd=ROOT)
                next_update=start+15
                try:
                    while child.poll() is None:
                        if time.monotonic()>=next_update:
                            print(f'[{name}] still running, {time.monotonic()-start:.0f}s; log: {log.name}',flush=True)
                            next_update=time.monotonic()+15
                        time.sleep(.2)
                except BaseException:
                    child.terminate()
                    try: child.wait(timeout=10)
                    except subprocess.TimeoutExpired: child.kill();child.wait()
                    raise
                task['returncode']=child.returncode
            task['status']='ok' if child.returncode==0 and (artifact is None or artifact.exists()) else 'failed'
        except OSError as exc:
            task.update(status='failed',error=str(exc),returncode=None)
            log.write_text(str(exc)+'\n')
        task['wall_seconds']=time.monotonic()-start
        dump(output/'manifest.json',manifest)
        print(f'[{name}] {task["status"]} ({task["wall_seconds"]:.1f}s)',flush=True)
        return task['status']=='ok'

    try:
        if os.environ.get('CUDA_LAUNCH_BLOCKING','0') not in ('','0'):
            raise RuntimeError('CUDA_LAUNCH_BLOCKING is set: disable it before performance collection')
        available=False
        if not args.cpu_only:
            artifact=output/'profiles/cuda_preflight.json'
            available=run_task('cuda_preflight',[sys.executable,ROOT/'scripts/gpu_preflight.py','--output',artifact],artifact)
            manifest['gpu_status']='verified_cuda_optix' if available else 'blocked'
            required_failure |= not available
        # CUDA blocked: retain same-host CPU evidence and a failure report.
        for tx in dict.fromkeys(args.tx):
            warmup=1 if args.quick else (20 if tx==2 else 5)
            iterations=(3 if tx==2 else 2) if args.quick else (200 if tx==2 else 30)
            common=['--tx',str(tx),'--rx','1','--samples',str(args.samples),
                '--samples-per-link',str(args.samples_per_link),'--threads',str(args.threads)]
            for backend in (['cpu','cuda'] if available else ['cpu']):
                name=f'{backend}_{tx}tx_1rx'
                artifact=output/'metrics'/f'{name}.json'
                required_failure |= not run_task(name,[sys.executable,benchmark,'--backend',backend,*common,
                    '--warmup',str(warmup),'--iterations',str(iterations),'--output',artifact],artifact)
            if available or args.cpu_only:
                backend='cuda' if available else 'cpu'
                name=f'{backend}_{tx}tx_1rx_events'
                artifact=output/'profiles'/f'{name}.json'
                required_failure |= not run_task(name,[sys.executable,benchmark,'--backend',backend,*common,'--profile',
                    '--warmup','1' if args.quick else '3','--iterations','2' if args.quick else '5','--output',artifact],artifact)
                nsys=os.environ.get('NSYS_BIN') or shutil.which('nsys')
                if available and not args.no_nsys and nsys:
                    stem=output/'raw'/f'nsys_{tx}tx_1rx'
                    artifact=output/'profiles'/f'nsys_{tx}tx_1rx.json'
                    success=run_task(f'nsys_{tx}tx_1rx',[nsys,'profile','--trace=cuda,nvtx,osrt',
                        '--sample=none','--cpuctxsw=none','--force-overwrite=true',f'--output={stem}',
                        sys.executable,benchmark,'--backend','cuda',*common,'--profile',
                        '--warmup','1' if args.quick else '3','--iterations','2' if args.quick else '5',
                        '--output',artifact],artifact,required=False)
                    if success:
                        run_task(f'nsys_{tx}tx_1rx_stats',[nsys,'stats','--report',
                            'cuda_gpu_kern_sum,cuda_api_sum,nvtx_sum',str(stem)+'.nsys-rep'],required=False)
                elif available and not args.no_nsys:
                    manifest['tasks'].append(dict(name=f'nsys_{tx}tx_1rx',status='unavailable',required=False,
                        reason='Nsight Systems not installed; CUDA-event profiling still collected'))
        if available and not args.no_example:
            required_failure |= not run_task('pluto_example',[sys.executable,ROOT/'examples/pluto_esm_drones.py',
                '--backend','cuda','--epochs','2' if args.quick else '12',
                '--samples',str(args.samples),'--samples-per-link',str(args.samples_per_link),
                '--output-dir',output/'raw/example'])
        manifest['complete']=True
    except (Exception,KeyboardInterrupt) as exc:
        required_failure=True
        manifest['error']=f'{type(exc).__name__}: {exc}'
        print(manifest['error'],flush=True)
    finally:
        telemetry.finish()
        manifest.update(finished_utc=datetime.now(timezone.utc).isoformat(),
            required_tasks_passed=not required_failure)
        dump(output/'manifest.json',manifest)
        aggregate=probe([sys.executable,ROOT/'scripts/aggregate_gpu_profile.py',output])
        if aggregate.get('returncode')!=0:
            print('Aggregation failed:',aggregate,flush=True)
            required_failure=True
        else:
            print(aggregate.get('stdout','').strip(),flush=True)
        print(f'Bundle: {output}',flush=True)
    return 20 if required_failure else 0


if __name__=='__main__':
    raise SystemExit(main())
