"""Matched GPU projection subgroup and FFT-length controls."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--iterations',type=int,default=30)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);(args.output/'logs').mkdir()
    cases=[('adaptive_before',[]),('auto',['--projection-lanes','0']),
           ('auto_radix23',['--projection-lanes','0','--fft-policy','radix23']),
           ('auto_trim_radix23',['--projection-lanes','0','--trim-delay-support','--fft-policy','radix23']),
           ('auto_trim_power2',['--projection-lanes','0','--trim-delay-support','--fft-policy','power2']),
           ('adaptive_after',[])]
    manifest=dict(scope='rf_pipeline_kernel_sweep',complete=False,iterations=args.iterations,warmup=3,tasks=[],note='All cases adaptive; identical GPU propagation/versions, epochs and private traffic. Separate sequential processes with shared disk JIT cache; controls bracket trials.')
    for name,options in cases:
        command=[sys.executable,str(ROOT/'scripts/basis_launch.py'),str(ROOT/'benchmarks/benchmark_end_to_end.py'),
            '--renderer','basis-cuda','--propagation-backend','cuda','--pascal-compat','--adaptive-temporal',
            '--tx','100','--rx','10','--iterations',str(args.iterations),'--warmup','3',
            '--output',str(args.output/name),*options]
        print('Starting '+name,flush=True);start=perf_counter()
        with (args.output/'logs'/f'{name}.log').open('w') as stream:
            result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
        manifest['tasks'].append(dict(name=name,command=command,returncode=result.returncode,wall_seconds=perf_counter()-start))
        (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        if result.returncode:raise SystemExit(name+' failed')
        d=json.loads((args.output/name/'measurements.json').read_text())
        print(f'{name}: {d["wall_time_per_simulated_time"]:.3f} wall s/simulated signal s; renderer {d["summary"]["rendering_ms"]["mean_ms"]:.3f} ms/update',flush=True)
    manifest['complete']=True;(args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':main()
