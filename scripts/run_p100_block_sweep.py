"""Matched GPU-propagation/renderer block-size trials, with bracketing controls."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=30)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'logs').mkdir()
    manifest = dict(scope='rf_pipeline_block_sweep', iterations=args.iterations,
                    warmup=3, tx=100, rx=10, propagation_backend='cuda', complete=False,
                    note='Sequential independent processes; shared disk JIT cache; 2048 controls bracket sweep. No CPU-only performance run.', tasks=[])
    for label, block in [('control_before',2048),('block512',512),('block1024',1024),
                         ('block4096',4096),('block8192',8192),('control_after',2048)]:
        command = [sys.executable,str(ROOT/'scripts/basis_launch.py'),str(ROOT/'benchmarks/benchmark_end_to_end.py'),
                   '--renderer','basis-cuda','--propagation-backend','cuda','--pascal-compat',
                   '--tx','100','--rx','10','--iterations',str(args.iterations),'--warmup','3',
                   '--block-samples',str(block),'--output',str(args.output/label)]
        print(f'Starting {label}: block={block}', flush=True)
        started = perf_counter()
        with (args.output/'logs'/f'{label}.log').open('w') as stream:
            outcome = subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
        manifest['tasks'].append(dict(name=label,block_samples=block,command=command,
            returncode=outcome.returncode,wall_seconds=perf_counter()-started))
        (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        if outcome.returncode:
            raise SystemExit(f'{label} failed; see its log')
        d=json.loads((args.output/label/'measurements.json').read_text())
        print(f'{label}: {d["wall_time_per_simulated_time"]:.3f} wall seconds/signal second; '
              f'{d["summary"]["total_ms"]["median_ms"]:.3f} ms/update; '
              f'rendering={d["summary"]["rendering_ms"]["median_ms"]:.3f} ms/update',flush=True)
    manifest['complete']=True
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    main()
