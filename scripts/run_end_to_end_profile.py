"""Run the complete RF integration suite and CPU/P100 scene-to-consumer scenarios."""
import argparse
from pathlib import Path
import subprocess
import sys
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--backend', choices=('cpu','cuda','both'), default='both')
    parser.add_argument('--iterations', type=int, default=30)
    parser.add_argument('--warmup', type=int, default=3)
    args = parser.parse_args()
    if args.iterations < 1 or args.warmup < 0:
        parser.error('Positive iteration count and nonnegative warmup required')
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    launcher = [sys.executable, str(ROOT/'scripts/basis_launch.py')]

    def execute(name, command):
        print(f'{name}: starting', flush=True)
        started = monotonic()
        with (args.output/(name+'.log')).open('w') as stream:
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
        if code:
            raise SystemExit(f'{name} failed (exit {code}); see {args.output/(name+".log")}')
        print(f'{name}: passed', flush=True)

    if args.backend in ('cuda','both'):
        # Import/runtime failures are fatal: no CPU fallback or skipped GPU claim.
        execute('cuda_preflight', launcher+['-c',
            'import cupy as cp; assert cp.cuda.runtime.getDeviceCount()>0; cp.arange(8).sum().get()'])
    execute('integration_tests', launcher+['-m','pytest','tests/test_end_to_end.py',
        'tests/test_sdr.py','tests/test_distributed.py','-q'])
    backends = ('cpu','cuda') if args.backend == 'both' else (args.backend,)
    for backend in backends:
        for tx, rx in ((2,2),(10,4),(100,10)):
            name = f'{backend}-{tx}tx-{rx}rx'
            execute(name, launcher+[str(ROOT/'benchmarks/benchmark_end_to_end.py'),
                '--renderer',f'basis-{backend}','--tx',str(tx),'--rx',str(rx),
                '--iterations',str(args.iterations),'--warmup',str(args.warmup),
                '--output',str(args.output/name)])
    print(f'Completed end-to-end collection: {args.output}', flush=True)


if __name__ == '__main__':
    main()
