#!/usr/bin/env python3
"""Generate stage statistics from individual recorded captures, without rerunning them."""
import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path('results/profiling/p100-basis-optimized-full-20261004/profiles')
BEGIN = '<!-- BEGIN STAGE TIMING TABLES -->'
END = '<!-- END STAGE TIMING TABLES -->'


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def cases():
    result = []
    for tx in (100, 4, 1):
        for backend in ('cpu', 'cuda'):
            path = RUN / f'basis_{backend}_{tx}tx_1rx.json'
            data = json.loads((ROOT / path).read_text())
            assert data['measurement_mode'] == 'unprofiled_basis_benchmark'
            assert data['accuracy']['passed'] and len(data['rows']) == 30
            columns = [[] for _ in range(9)]
            for row in data['rows']:
                metrics = row['receiver_metrics'][0]
                columns[6].append(row['total_ms'])
                columns[8].append(row['total_ms'])
                if backend == 'cpu':
                    for index, key in ((2, 'preparation_ms'), (3, 'channel_construction_ms'), (4, 'fft_and_reconstruction_ms')):
                        columns[index].append(metrics[key])
                    columns[5].append(row['total_ms'] - sum(metrics[key] for key in ('preparation_ms', 'channel_construction_ms', 'fft_and_reconstruction_ms')))
            label = f"{'CPU basis' if backend == 'cpu' else 'P100 basis'}, {tx} → 1; 16,667 samples"
            result.append((label, path, columns, data))
    for file, label in (
        ('benchmarks/results/sdr_cpu_2tx_1rx.json', 'CPU direct SDR, 2 → 1'),
        ('benchmarks/results/sdr_cpu_2tx_2rx.json', 'CPU direct SDR, 2 → 2'),
        ('benchmarks/results/sdr_cpu_100tx_1rx.json', 'CPU direct SDR, 100 → 1'),
        ('research_results/batched_renderer_cpu/per_link_local.json', 'CPU LLVM per-link, 100 → 1'),
        ('research_results/batched_renderer_cpu/batched_32.json', 'CPU LLVM tile 32, 100 → 1'),
        ('research_results/batched_renderer_cpu/batched_128.json', 'CPU LLVM tile 128, 100 → 1'),
    ):
        path = Path(file)
        data = json.loads((ROOT / path).read_text())
        columns = [[] for _ in range(9)]
        for row in data['samples']:
            for index, key in ((0, 'pose_ms'), (1, 'channel_ms'), (8, 'service_ms')):
                columns[index].append(row[key])
            if 'render_ms' in row:
                columns[6].append(row['render_ms'])
                columns[7].append(row['cpu_iq_receiver_ms'] - row['render_ms'])
            else:
                columns[7].append(row['cpu_iq_receiver_ms'])
        result.append((label + '; 4,096 samples (historical)', path, columns, data))
    return result


def tables():
    records = cases()
    headings = ['Configuration / raw captures', 'n', 'Signal ms/call', 'Wall s / signal s (mean)', 'Pose update', 'Scene propagation', 'Render preparation', 'Basis/filter construction', 'FFT + reconstruction', 'Other rendering work', 'Signal rendering subtotal', 'Receiver processing', 'Measured call total']
    sections = []
    for title, p95 in (('Median ± sample standard deviation', False), ('95th percentile', True)):
        lines = ['### ' + title, '', '| ' + ' | '.join(headings) + ' |', '| --- | ---: | ---: | ---: | ' + ' | '.join(['---:'] * 9) + ' |']
        for label, path, columns, data in records:
            cells = []
            for values in columns:
                if not values:
                    cells.append('—')
                elif p95:
                    cells.append(f'{percentile(values, .95):.2f}')
                else:
                    cells.append(f'{statistics.median(values):.2f} ± {statistics.stdev(values):.2f}')
            lines.append('| ' + ' | '.join([f'[{label}]({path.as_posix()})', str(len(columns[8])), f"{data.get('capture_duration_ms', data.get('arguments',{}).get('samples',16667)/data.get('arguments',{}).get('sample_rate',2000000)*1000):.6f}", f"{statistics.mean(columns[8])/data.get('capture_duration_ms', data.get('arguments',{}).get('samples',16667)/data.get('arguments',{}).get('sample_rate',2000000)*1000):.3f}", *cells]) + ' |')
        sections.append('\n'.join(lines))
    lines = ['### GPU stage observations: one instrumented capture per configuration', '',
             'These are CUDA-event spans, in ms, from a separate capture. **n = 1; no standard deviation or p95 is available.** They include dispatch gaps and profiling overhead, and must not be added to the unprofiled median above.', '',
             '| Configuration | Pack + upload | Delay map | Temporal coefficients | Path → filter projection | Private FFT filters | Reconstruction + sum | Output export | Instrumented wall total |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    keys = ['basis.host_pack_and_upload', 'basis.delay_map', 'basis.temporal_coefficients', 'basis.path_projection', 'basis.private_fft_filters', 'basis.reconstruction_and_sum', 'basis.final_output_export']
    for label, path, columns, data in records:
        if 'P100 basis' not in label:
            continue
        profile = data['profile_receivers'][0]
        events = {}
        for event in profile['events']:
            events[event['name']] = events.get(event['name'], 0.) + event['cuda_ms']
        lines.append('| ' + ' | '.join([f'[{label}]({path.as_posix()})', *[f'{events[key]:.2f}' for key in keys], f'{profile["total_ms"]:.2f}']) + ' |')
    sections.append('\n'.join(lines))
    sections.extend(end_to_end_tables())
    return '\n\n'.join(sections)



def end_to_end_tables():
    from aggregate_end_to_end_profile import tables as complete_tables, validate, validate_collection
    records = []
    for path in sorted((ROOT/'results/end_to_end').rglob('measurements.json')):
        records.append((path, validate(json.loads(path.read_text()))))
    for path in sorted((ROOT/'results/profiling').rglob('manifest.json')):
        manifest=json.loads(path.read_text())
        if manifest.get('scope')!='rf_pipeline_end_to_end_collection':
            continue
        bundle_records=[(p,validate(json.loads(p.read_text()))) for p in sorted(path.parent.rglob('measurements.json'))]
        validate_collection(bundle_records,manifest)
        records.extend(bundle_records)
    return [complete_tables(records, link_root=ROOT)] if records else []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'docs/archive/runtime.md'
    current = path.read_text()
    assert current.count(BEGIN) == current.count(END) == 1
    before, rest = current.split(BEGIN)
    _, after = rest.split(END)
    updated = before + BEGIN + '\n\n' + tables().replace('](results/', '](../../results/').replace('](benchmarks/', '](../../benchmarks/').replace('](research_results/', '](../../research_results/') + '\n\n' + END + after
    if args.check and updated != current:
        raise SystemExit('Stage timing tables differ from raw captures.')
    if not args.check:
        path.write_text(updated)
    print('Stage timing tables match raw captures.' if args.check else 'Updated stage timing tables.')


if __name__ == '__main__':
    main()
