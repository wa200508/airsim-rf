"""Rebuild the current documentation entry point from immutable raw measurements."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BEGIN='<!-- BEGIN PROFILING OVERVIEW -->'
END='<!-- END PROFILING OVERVIEW -->'


def tables():
    rows=[]
    for tx,rx in [(2,2),(10,4),(100,10)]:
        path=Path(f'results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-{tx}tx-{rx}rx-unprofiled/measurements.json')
        d=json.loads((ROOT/path).read_text());stats=d['summary']
        stages=[stats[k] for k in ('advance_ms','source_ms','channel_ms','rendering_ms','receiver_ms','other_rf_ms','delivery_storage_ms','total_ms')]
        cells=[{s:stage[key] for s,key in [('median','median_ms'),('sd','std_ms'),('p95','p95_ms')]} for stage in stages]
        signal=d['measured_simulated_duration_ms']/len(d['samples'])
        wall=sum(r['total_ms'] for r in d['samples'])/d['measured_simulated_duration_ms']
        rows.append((f'[P100 one-way {tx} TX / {rx} RX, 2026-10-08](../{path})',signal,len(d['samples']),cells,wall))
    for name in ['clear-targets','masked-targets','clear-clutter','masked-clutter','1024-valid-scatterers-targets']:
        path=Path(f'results/reviews/first-order-radar-20261023/{name}.json');d=json.loads((ROOT/path).read_text());stats=d['summary']
        cells=['in other','N/A',stats['visibility_ms'],stats['tone_ms'],'in other',stats['other_ms'],'—',stats['service_ms']]
        rows.append((f'[CPU radar {name}, 2026-10-23](../{path})',4.,len(d['samples']),cells,d['wall_seconds_per_signal_second']))
    lines=[]
    for title,stat in [('Median ± sample SD','median'),('95th percentile','p95')]:
        lines += [f'## {title}', '', 'Milliseconds per named operation. **—** = unmeasured; **in other** = included in the Other column; **N/A** = no separate stage in this model.', '',
            '| Configuration / raw data | Signal ms | n | Pose / truth | Private TX sources | Channel / visibility | I/Q / IF synthesis | RX filter / noise / ADC | Other | Delivery / storage | Total |'+(' Wall s / signal s |' if stat=='median' else ''),
            '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |'+(' ---: |' if stat=='median' else '')]
        for label,signal,n,cells,wall in rows:
            formatted=[]
            for cell in cells:
                if isinstance(cell,str):formatted.append(cell)
                else:formatted.append(f"{cell['median']:.3f} ± {cell['sd']:.3f}" if stat=='median' else f"{cell['p95']:.3f}")
            lines.append('| '+f'{label} | {signal:.3f} | {n} | '+' | '.join(formatted)+' |'+(f' {wall:.3f} |' if stat=='median' else ''))
        lines.append('')
    return '\n'.join(lines).rstrip()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');args=p.parse_args()
    path=ROOT/'docs/profiling.md';text=path.read_text();assert text.count(BEGIN)==text.count(END)==1
    before,rest=text.split(BEGIN);_,after=rest.split(END);updated=before+BEGIN+'\n\n'+tables()+'\n\n'+END+after
    if args.check and updated!=text:raise SystemExit('Profiling overview is stale: run python scripts/update_profiling_overview.py')
    if not args.check:path.write_text(updated)
    print('Profiling overview matches raw measurements.' if args.check else 'Updated profiling overview.')


if __name__=='__main__':main()
