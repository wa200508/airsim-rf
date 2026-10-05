"""Validate and consolidate complete RF-pipeline wall timings and repeated CUDA events."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import statistics

PIPELINE = {
    'advance_ms': 'Truth advance', 'source_ms': 'Private sources', 'channel_ms': 'Scene propagation',
    'rendering_ms': 'Signal rendering', 'receiver_ms': 'Noise/filter/ADC',
    'other_rf_ms': 'Bridge + other RF work', 'delivery_storage_ms': 'Delivery + storage', 'total_ms': 'Complete update',
}
EVENTS = {
    'basis.host_pack_and_upload': 'Pack + upload', 'basis.delay_map': 'Delay map',
    'basis.temporal_coefficients': 'Temporal coefficients', 'basis.path_projection': 'Path → filter projection',
    'basis.private_fft_filters': 'Private FFT filters', 'basis.reconstruction_and_sum': 'Reconstruction + sum',
    'basis.final_output_export': 'Output export',
}
NORMAL = 'unprofiled_end_to_end_benchmark'
PROFILE = 'instrumented_end_to_end_profile'


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered)-1)*fraction
    low = int(position)
    high = min(low+1,len(ordered)-1)
    return ordered[low]+(ordered[high]-ordered[low])*(position-low)


def numeric(value, label):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
        raise ValueError(f'{label}: expected finite nonnegative timing')
    return value


def mode(data):
    # Preserve the earlier, explicitly uninstrumented cloud captures.
    value = data.get('measurement_mode', NORMAL)
    if value not in (NORMAL,PROFILE):
        raise ValueError(f'Unknown measurement mode: {value}')
    return value


def event_totals(row, receivers):
    metrics = row.get('receiver_render_metrics',[])
    if len(metrics)!=receivers:
        raise ValueError('Missing per-receiver renderer profiling')
    totals = dict.fromkeys(EVENTS,0.)
    for receiver in metrics:
        if receiver.get('profile') is not True or receiver.get('backend')!='cuda_cupy':
            raise ValueError('Instrumented row is missing verified CuPy event profiling')
        present = set()
        for event in receiver.get('events',[]):
            name = event['name']
            if name not in EVENTS:
                raise ValueError(f'Unexpected CUDA stage: {name}')
            totals[name] += numeric(event['cuda_ms'],name)
            present.add(name)
        if present != set(EVENTS):
            raise ValueError('Missing CUDA stages: '+', '.join(sorted(set(EVENTS)-present)))
    return totals


def validate(data):
    if data.get('scope') not in ('rf_pipeline_end_to_end','live_airsim_rf_end_to_end'):
        raise ValueError('Not a complete RF-pipeline capture')
    args = data['arguments']
    rows = data['samples']
    if len(rows)!=args['iterations'] or not rows:
        raise ValueError('Incomplete timed capture count')
    if data['sample_rate_hz']!=2_000_000 or data['update_hz']!=120 or args['samples_per_link']!=1028:
        raise ValueError('Required 2 MS/s, 120 Hz, 1028 attempts/link workload changed')
    for row in rows:
        for key in PIPELINE:
            numeric(row[key],key)
        if set(row['retained_paths']) != {f'rx{i}' for i in range(args['rx'])}:
            raise ValueError('Missing receiver capture')
        for paths in row['retained_paths'].values():
            if set(paths)!={f'tx{i}' for i in range(args['tx'])}:
                raise ValueError('Missing transmitter link')
        if row['samples'] != round((row['sequence']+1)*2_000_000/120)-round(row['sequence']*2_000_000/120):
            raise ValueError('Output sample budget changed')
        if mode(data)==NORMAL and any(m.get('profile') is True for m in row.get('receiver_render_metrics',[])):
            raise ValueError('Instrumented renderer cannot enter unprofiled throughput')
        if mode(data)==PROFILE:
            if data['rendering_backend']!='basis-cuda':
                raise ValueError('GPU events require basis-cuda')
            event_totals(row,args['rx'])
    for previous,current in zip(rows,rows[1:]):
        if current['sequence']!=previous['sequence']+1 or current['sim_time_ns']!=previous['sim_time_ns']+previous['samples']*500:
            raise ValueError('Non-contiguous output windows')
    return data


def tables(records, *, link_root):
    sections = []
    def label(path,data):
        args=data['arguments']; hardware=data.get('hardware',{})
        gpu=hardware.get('gpu') or {}
        device=gpu.get('name') or hardware.get('cpu')
        if not device:
            legacy=path.parent.parent/'environment.json'
            extra=json.loads(legacy.read_text()) if legacy.is_file() else {}
            device=extra.get('cpu') if isinstance(extra.get('cpu'),str) else None
        device=device or 'see hardware record'
        name=f"{args['tx']} → {args['rx']}, {data['rendering_backend']}; {device}"
        return f'[{name}]({path.relative_to(link_root).as_posix()})'

    def render(title, selected, keys, get_values):
        for p95 in (False,True):
            heading=title+': '+('p95' if p95 else 'median ± sample standard deviation')
            lines=['### '+heading,'','| Configuration / raw captures | n | '+' | '.join(keys.values())+' |',
                   '| --- | ---: | '+' | '.join(['---:']*len(keys))+' |']
            for path,data in selected:
                columns=get_values(data)
                cells=[]
                for key in keys:
                    values=columns[key]
                    if p95:
                        cells.append(f'{percentile(values,.95):.3f}')
                    elif len(values)>1:
                        cells.append(f'{statistics.median(values):.3f} ± {statistics.stdev(values):.3f}')
                    else:
                        cells.append(f'{values[0]:.3f} (n=1; SD unavailable)')
                lines.append('| '+' | '.join([label(path,data),str(len(data['samples'])),*cells])+' |')
            sections.append('\n'.join(lines))

    normal=[r for r in records if mode(r[1])==NORMAL]
    profiled=[r for r in records if mode(r[1])==PROFILE]
    if normal:
        render('End-to-end RF pipeline',normal,PIPELINE,
               lambda d:{key:[row[key] for row in d['samples']] for key in PIPELINE})
    if profiled:
        render('Instrumented end-to-end wall timings',profiled,PIPELINE,
               lambda d:{key:[row[key] for row in d['samples']] for key in PIPELINE})
        def event_columns(data):
            windows=[event_totals(row,data['arguments']['rx']) for row in data['samples']]
            return {key:[row[key] for row in windows] for key in EVENTS}
        render('Repeated CUDA rendering event spans',profiled,EVENTS,event_columns)
        sections.append('CUDA event spans sum each named stage across all blocks/batches and receivers **within each window**, then summarize those window totals. They include host dispatch gaps and are not pure kernel execution times. They come from separate instrumented full-pipeline runs; do not mix them into unprofiled throughput or add their medians to wall-time medians.')
    sections.append('All timings are ms per fleet update. Source generation, propagation, continuous receiver filtering/noise/ADC, loopback HTTP delivery and consumer file readback are included. Sionna propagation is LLVM CPU even with CuPy rendering. Receivers execute serially. The default truth source implements the AirSim contract; it does not run live AirSim physics/RPC or AMS-GRA distributed SDR workers. Startup/warmup are excluded from these tables, physical path counts and hardware/quota are in the linked JSON, and five-/ten-window historical runs do not qualify long-run tail latency.')
    return '\n\n'.join(sections)


def validate_collection(records, manifest):
    if not manifest.get('complete') or any(t['status']!='ok' for t in manifest['tasks']):
        raise ValueError('Collection is incomplete or has failed required tasks')
    expected={(b,tx,rx,m) for b in manifest['backends'] for tx,rx in manifest['scenarios']
              for m in ((NORMAL,PROFILE) if b=='cuda' else (NORMAL,))}
    actual=[(d['rendering_backend'].removeprefix('basis-'),d['arguments']['tx'],d['arguments']['rx'],mode(d)) for _,d in records]
    if len(actual)!=len(set(actual)) or set(actual)!=expected:
        raise ValueError('Missing or duplicated scenario/mode rows')
    if any(len(d['samples'])!=manifest['iterations'] for _,d in records):
        raise ValueError('Scenario capture count differs from collection request')
    if any(len(d['samples'])<2 for _,d in records):
        raise ValueError('At least two captures required for standard deviation')



def aggregate(bundle, *, check_complete=True):
    bundle=Path(bundle).resolve()
    records=[(p,validate(json.loads(p.read_text()))) for p in sorted(bundle.rglob('measurements.json'))]
    if not records:
        raise ValueError('No complete-pipeline measurement files')
    manifest_path=bundle/'manifest.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    if manifest and check_complete:
        validate_collection(records,manifest)
    report='# Complete RF end-to-end profiling collection\n\n'+tables(records,link_root=bundle)+'\n'
    (bundle/'REPORT.md').write_text(report)
    summaries=[]
    for path,data in records:
        summaries.append(dict(path=path.relative_to(bundle).as_posix(), measurement_mode=mode(data),
                              arguments=data['arguments'], summary=data['summary']))
    (bundle/'profile_summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    files=[p for p in bundle.rglob('*') if p.is_file() and p.suffix in ('.json','.md','.log') and p.name!='checksums.json']
    checksums={p.relative_to(bundle).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    (bundle/'checksums.json').write_text(json.dumps(checksums,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle',type=Path)
    args=parser.parse_args()
    try:
        aggregate(args.bundle)
    except (ValueError,KeyError) as exc:
        raise SystemExit(f'Incomplete end-to-end results: {exc}')
    print(f'Validated and wrote {args.bundle/"REPORT.md"}')


if __name__=='__main__':
    main()
