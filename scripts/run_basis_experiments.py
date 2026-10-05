"""Serial GPU timing experiments; keep fixed signal budgets and retain qualification."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--stage', choices=('projections', 'filters', 'blocks'), required=True)
parser.add_argument('--projection', choices=('gather', 'warp', 'dense'), default='warp')
parser.add_argument('--batch-links', type=int, default=8)
parser.add_argument('--iterations', type=int, default=10)
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
if args.stage == 'projections':
    cases = [(f'{p}{b}', ['--projection', p, '--batch-links', str(b)])
             for p, b in [('gather', 8), ('warp', 8), ('dense', 8), ('warp', 32),
                          ('dense', 32), ('warp', 100), ('dense', 100)]]
    cases.append(('gather8_repeat', ['--projection', 'gather', '--batch-links', '8']))
elif args.stage == 'filters':
    cases = [(f'sort{sort}_inplace{int(inplace)}', ['--projection', args.projection,
              '--batch-links', str(args.batch_links), '--delay-map', sort]
              + (['--fft-inplace'] if inplace else []))
             for sort, inplace in [('double', False), ('single', False), ('double', True), ('single', True)]]
else:
    cases = [(f'block{block}', ['--projection', args.projection,
              '--batch-links', str(args.batch_links), '--delay-map', 'single', '--fft-inplace',
              '--block-samples', str(block)]) for block in [512, 1024, 2048, 4096, 8192]]
manifest = dict(stage=args.stage, started_utc=datetime.now(timezone.utc).isoformat(),
    source_revision=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
    workload='100 independent TX / 1 RX, 1028 paths/link, 16667 samples, FP64/complex128; no concurrent GPU throughput runs',
    tasks=[], complete=False)
def save():
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
save()
for name, options in cases:
    command = [sys.executable, str(ROOT/'benchmarks/benchmark_doppler_basis_gpu.py'),
               '--backend', 'cuda', '--tx', '100', '--iterations', str(args.iterations),
               '--warmup', '3', '--output', str(out/f'{name}.json'), *options]
    task = dict(name=name, command=command, status='running')
    manifest['tasks'].append(task); save(); print(name, 'starting', flush=True)
    started = time.monotonic()
    with (out/f'{name}.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    task.update(returncode=result.returncode, wall_s=time.monotonic()-started,
                status='ok' if result.returncode == 0 else 'failed')
    save(); print(name, task['status'], flush=True)
manifest['complete'] = True
manifest['required_tasks_passed'] = all(t['status'] == 'ok' for t in manifest['tasks'])
save()
raise SystemExit(0 if manifest['required_tasks_passed'] else 20)
