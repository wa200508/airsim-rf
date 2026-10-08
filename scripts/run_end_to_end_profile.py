"""Collect validated complete RF-pipeline CPU/P100 rows and repeated CUDA stages."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from time import monotonic

from aggregate_end_to_end_profile import aggregate
from run_gpu_profile import environment

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Exact new output directory')
    parser.add_argument('--output-root', type=Path, default=ROOT/'results/profiling')
    parser.add_argument('--run-id', default='p100-end-to-end-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    parser.add_argument('--backend', choices=('cpu','cuda','both'), default='both')
    parser.add_argument('--cpu-only', action='store_true', help='Equivalent to --backend cpu')
    parser.add_argument('--iterations', type=int, default=30)
    parser.add_argument('--propagation-backend', choices=('llvm','cuda'), default='llvm')
    parser.add_argument('--pascal-compat', action='store_true')
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--warmup', type=int, default=3)
    parser.add_argument('--scenarios', nargs='+', default=['2x2','10x4','100x10'], help='TXxRX counts; budgets/cadence unchanged')
    args = parser.parse_args()
    if args.iterations < 2 or args.warmup < 0 or args.threads < 1:
        parser.error('At least two timed captures for SD and nonnegative warmup required')
    if args.cpu_only:
        args.backend='cpu'
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}',args.run_id):
        parser.error('Use a filename-safe run-id')
    scenarios=[]
    for value in args.scenarios:
        match=re.fullmatch(r'([1-9][0-9]*)x([1-9][0-9]*)',value)
        if not match:
            parser.error('Scenarios must be TXxRX counts, e.g. 100x10')
        scenarios.append(tuple(map(int,match.groups())))
    if len(set(scenarios))!=len(scenarios):
        parser.error('Duplicate scenario')
    output=(args.output or args.output_root/args.run_id).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output/'logs').mkdir()
    (output/'profiles').mkdir()
    backends = ['cpu','cuda'] if args.backend == 'both' else [args.backend]
    manifest=dict(run_id=output.name,scope='rf_pipeline_end_to_end_collection',complete=False,
                  iterations=args.iterations,warmup=args.warmup,threads=args.threads,propagation_backend=args.propagation_backend,pascal_compat=args.pascal_compat,scenarios=scenarios,backends=backends,tasks=[])
    def save():
        (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    save()
    (output/'environment.json').write_text(json.dumps(environment(),indent=2)+'\n')
    launcher = [sys.executable, str(ROOT/'scripts/basis_launch.py')]

    def execute(name, command, artifact=None):
        task=dict(name=name,command=command,status='running',artifact=artifact)
        manifest['tasks'].append(task);save()
        print(f'{name}: starting', flush=True)
        started = monotonic()
        try:
            with (output/'logs'/(name+'.log')).open('w') as stream:
                with subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT) as child:
                    try:
                        while True:
                            try:
                                code = child.wait(timeout=15)
                                break
                            except subprocess.TimeoutExpired:
                                print(f'{name}: running for {monotonic()-started:.0f}s', flush=True)
                    except BaseException:
                        child.terminate()
                        try:
                            child.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            child.kill()
                        raise
            task.update(returncode=code,status='ok' if code==0 and (artifact is None or (output/artifact).is_file()) else 'failed')
        except BaseException:
            task['status']='failed';save();raise
        task['wall_seconds']=monotonic()-started;save()
        if task['status']!='ok':
            raise SystemExit(f'{name} failed; see {output/"logs"/(name+".log")}')
        print(f'{name}: passed', flush=True)

    if 'cuda' in backends:
        execute('cuda_preflight', launcher+[str(ROOT/'scripts/basis_cuda_preflight.py'),
                '--output',str(output/'profiles/cuda_preflight.json')], 'profiles/cuda_preflight.json')
    test_paths = ['tests/test_end_to_end.py','tests/test_sdr.py',
                  'tests/test_end_to_end_profiling.py','tests/test_p100_compat.py']
    prelude = "import mitsuba as mi; mi.set_variant(%r); " % (args.propagation_backend+'_ad_mono_polarized')
    if args.pascal_compat:
        prelude += 'from airsim_rf.p100_compat import enable_pascal_compat; enable_pascal_compat(); '
    prelude += "import pytest; raise SystemExit(pytest.main(%r))" % (test_paths+['-q','-o','cache_dir=/tmp/pytest-cache'])
    execute('integration_tests',launcher+['-c',prelude])
    # Worker fixtures select LLVM and must not switch Mitsuba variants inside
    # a process whose Sionna symbols were initialized for CUDA.
    worker_prelude = "import mitsuba as mi; import drjit as dr; mi.set_variant('llvm_ad_mono_polarized'); "
    if args.pascal_compat:
        worker_prelude += "setattr(dr.JitBackend,'Metal',None) if not hasattr(dr.JitBackend,'Metal') else None; "
    worker_prelude += "import pytest; raise SystemExit(pytest.main(['tests/test_distributed.py','-q','-o','cache_dir=/tmp/pytest-cache']))"
    execute('worker_protocol_tests',launcher+['-c',worker_prelude])
    for backend in backends:
        for tx, rx in scenarios:
            modes = ('unprofiled','instrumented') if backend=='cuda' else ('unprofiled',)
            for mode in modes:
                name = f'{backend}-{tx}tx-{rx}rx-{mode}'
                relative=f'profiles/{name}/measurements.json'
                command=launcher+[str(ROOT/'benchmarks/benchmark_end_to_end.py'),
                    '--renderer',f'basis-{backend}','--tx',str(tx),'--rx',str(rx),
                    '--iterations',str(args.iterations),'--warmup',str(args.warmup),'--threads',str(args.threads),'--propagation-backend',args.propagation_backend,
                    '--output',str(output/'profiles'/name)]
                if args.pascal_compat:
                    command.append('--pascal-compat')
                if mode=='instrumented':
                    command.append('--profile-rendering')
                execute(name,command,relative)
    manifest['complete']=True;save()
    try:
        aggregate(output)
    except BaseException:
        manifest['complete']=False;save();raise
    print(f'Completed and validated collection: {output/"REPORT.md"}', flush=True)
    if output.parent == ROOT/'results/profiling':
        print(f'Publish: python scripts/publish_gpu_results.py {output} --push', flush=True)
    else:
        print('To publish, copy this bundle into the checkout at results/profiling/<run-id>.', flush=True)


if __name__ == '__main__':
    main()
