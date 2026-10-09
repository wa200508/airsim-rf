"""Matched GPU RF fleet controls for actual-Doppler rank and path ordering."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=30)
    args=parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'logs').mkdir()
    cases=[('fixed_before',[]),('adaptive',['--adaptive-temporal']),
           ('adaptive_single',['--adaptive-temporal','--cuda-delay-map','single']),
           ('fixed_single',['--cuda-delay-map','single']),
           ('adaptive_fused',['--adaptive-temporal','--fused-projection']),('fixed_after',[])]
    manifest=dict(scope='rf_pipeline_temporal_sweep',iterations=args.iterations,warmup=3,
                  complete=False,tasks=[],note='Same GPU propagation/versions/scene/epochs; separate sequential processes, shared disk JIT cache; fixed controls bracket experiments.')
    for name, options in cases:
        command=[sys.executable,str(ROOT/'scripts/basis_launch.py'),str(ROOT/'benchmarks/benchmark_end_to_end.py'),
            '--renderer','basis-cuda','--propagation-backend','cuda','--pascal-compat','--tx','100','--rx','10',
            '--iterations',str(args.iterations),'--warmup','3','--output',str(args.output/name),*options]
        print(f'Starting {name}',flush=True)
        started=perf_counter()
        with (args.output/'logs'/f'{name}.log').open('w') as stream:
            result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
        manifest['tasks'].append(dict(name=name,command=command,options=options,returncode=result.returncode,wall_seconds=perf_counter()-started))
        (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        if result.returncode:raise SystemExit(f'{name} failed; see log')
        d=json.loads((args.output/name/'measurements.json').read_text())
        print(f'{name}: {d["wall_time_per_simulated_time"]:.3f} wall s/simulated signal s; rendering mean {d["summary"]["rendering_ms"]["mean_ms"]:.3f} ms/update',flush=True)
    manifest['complete']=True
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':main()
