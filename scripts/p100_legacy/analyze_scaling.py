"""Summarize completed and failed legacy scaling cases without inventing timings."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('bundle', type=Path)
args = parser.parse_args()
bundle = args.bundle
manifest = json.loads((bundle / 'manifest.json').read_text())
summary = []
for case in manifest['cases']:
    data = json.loads((bundle / 'metrics' / f"{case['tx']}tx.json").read_text())
    row = {key: case.get(key) for key in ('tx', 'status', 'stage', 'requested_rays', 'wall_s')}
    row.update(case.get('telemetry', {}))
    row['setup_s'] = data.get('setup_s', data.get('setup_elapsed_s'))
    row['created_transmitters'] = data.get('created_transmitters')
    row['error'] = data.get('error')
    row['stop_reason'] = case.get('stop_reason')
    state = json.loads(case['container_state']['stdout'])
    row['host_oom_killed'] = state.get('OOMKilled')
    if case['status'] == 'ok':
        epochs = data['epochs']
        row.update(data['statistics'])
        row['epochs'] = len(epochs)
        row['trace_p50_ms'] = statistics.median(e['trace_ms'] for e in epochs)
        row['fields_p50_ms'] = statistics.median(e['fields_and_fence_ms'] for e in epochs)
        row['retained_paths'] = sorted(set(e['retained_paths'] for e in epochs))
        row['tensorflow_peak_bytes'] = max(e['tensorflow_memory']['peak'] for e in epochs)
        events = data['profile']['device_events']
        row['cuda_events'] = sum(e.get('backend') == 'CUDA' for e in events)
        row['optix_events'] = sum(bool(e.get('uses_optix')) for e in events)
    summary.append(row)
(bundle / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
lines = [
    '# P100 legacy propagation-only scaling', '',
    '**Legacy Sionna 0.19.2 / Mitsuba 3.5.2 / Dr.Jit 0.4.6 / TensorFlow 2.15.1.**', '',
    'All transmitters in each case are instantiated simultaneously in one scene and one native solve; no transmitter batching. One RX, static TX positions, original terrain mesh, 915 MHz, synthetic single-element dipoles, depth 1, LoS/reflection/scattering. Native Fibonacci tracing launches 1,028 rays per TX; scattering keep probability 1, random scatter phases disabled. Material epsilon_r=5, conductivity=.01, scattering=.3; legacy material lacks thickness.', '',
    'Signal rendering, I/Q synthesis, receiver filtering/noise/ADC and full coefficient export are omitted. Timings include native trace, RF fields, host orchestration and synchronized scalar reductions. Scene setup and first solve are excluded from steady timings and retained separately. These are experimental legacy measurements, not the branch custom solver or numerically validated equivalents.', '',
    '| Simultaneous TX | Rays requested | Outcome | Timed median | Trace / fields medians | Sampled GPU memory max | Sampled GPU busy max |',
    '|---:|---:|---|---:|---:|---:|---:|',
]
for r in summary:
    timing = f"{r['p50_ms']/1000:.3f} s" if r['status'] == 'ok' else '—'
    stages = f"{r['trace_p50_ms']/1000:.3f} / {r['fields_p50_ms']/1000:.3f} s" if r['status'] == 'ok' else '—'
    memory = f"{r['max_sampled_memory_mib']/1024:.3f} GiB" if r.get('max_sampled_memory_mib') is not None else '—'
    lines.append(f"| {r['tx']:,} | {r['requested_rays']:,} | {r['status']} ({r['stage']}) | {timing} | {stages} | {memory} | {r.get('max_sampled_utilization_percent', '—')}% |")
lines += ['', '![Propagation latency and sampled GPU memory](scaling.png)', '', '## Capacity and failed attempts', '']
for r in summary:
    if r['status'] != 'ok':
        lines += [f"- **{r['tx']:,} TX:** {r['status']} during `{r['stage']}`, after {r['wall_s']:.1f} s; {r.get('created_transmitters')} TX objects created. Container host OOM kill: `{r['host_oom_killed']}`. See [checkpoint](metrics/{r['tx']}tx.json) and [log](logs/{r['tx']}tx.log)."]
        if r['error']:
            lines += ['', '```text', r['error'], '```', '']
        if r['stop_reason']:
            lines += ['', r['stop_reason'], '']
lines += ['', '## Interpretation and limits', '',
    'At successful scales, both Dr.Jit CUDA/OptiX events and TensorFlow GPU allocation are recorded. GPU busy samples reach 100%; earlier zero samples cannot establish that 99% of processing capacity was unused. Busy percentage measures activity over a sampling window, not theoretical compute throughput.', '',
    'The runner exposes all 16 GiB of P100 VRAM. Its 12 GiB container cap applies only to host RAM; host swap is disabled. Larger cases have bounded wall-clock budgets and fail independently. Memory-pressure warnings or timeouts do not establish an exact maximum supported TX count; intermediate sizes, ray budget, material/scattering, path representation, receiver count and implementation all affect capacity. No GPU reset or driver reconfiguration is performed.', '',
    'GPU telemetry samples every 100 ms and includes other processes (about 263 MiB baseline). Sampled maxima can miss transient peaks. TensorFlow allocator peaks omit Dr.Jit and other allocators. Dr.Jit histories omit TensorFlow CUDA kernels and are not end-to-end critical-path timing.', '',
    'Sample streams are retained as compressed CSV in `telemetry/`. Environment metadata identifies the measured base source commit; `harness_checksums.json` identifies the committed benchmark/launcher source. The 1M attempt was stopped at the user’s request once the 100k memory boundary was evident; it is not a measured 1M OOM failure.', '',
    '1k uses 3 warmups and 10 timed epochs; 10k uses 1 warmup and 3 timed epochs. Few-epoch p95 values are smoke statistics, not reliable latency tails. Static geometry and repeated seeds do not represent a dynamic million-device deployment. Scientific equivalence and signal quality have not been validated.', '',
    'The earlier full service collection measured approximately 96% host I/Q/receiver time at 100 TX. Removing that stage exposes propagation scaling, but does not make simultaneous propagation unlimited. These results support investigating signal rendering and propagation memory independently. No extrapolated latency is assigned to failed cases.', '',
    '[Manifest](manifest.json) · [Summary](summary.json) · [Environment](environment.json) · [Harness](../../../scripts/p100_legacy/README.md) · [Checksums](checksums.json)', '',
]
(bundle / 'REPORT.md').write_text('\n'.join(lines))
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8))
    good = [r for r in summary if r['status'] == 'ok']
    axes[0].plot([r['tx'] for r in good], [r['p50_ms']/1000 for r in good], 'o-')
    axes[0].set(xscale='log', xlabel='Simultaneous transmitters', ylabel='Median propagation (s)', title='Completed solves only')
    labels = [f"{r['tx']:,}\n{r['status'].replace('stopped_by_user', 'stopped')}" for r in summary]
    axes[1].bar(labels, [r['max_sampled_memory_mib']/1024 for r in summary],
                color=['tab:blue' if r['status'] == 'ok' else 'gray' for r in summary])
    axes[1].axhline(16, color='red', linestyle='--', label='Physical VRAM')
    axes[1].set(xlabel='Simultaneous transmitters / outcome', ylabel='Sampled whole-GPU memory (GiB)', title='Incomplete attempts are gray')
    axes[1].legend()
    axes[1].tick_params(axis='x', rotation=20)
    fig.suptitle('P100 — legacy Sionna, no signal rendering')
    fig.tight_layout()
    fig.savefig(bundle / 'scaling.png', dpi=180)
    plt.close(fig)
except ImportError:
    pass
checks = {str(p.relative_to(bundle)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(bundle.rglob('*')) if p.is_file()
          and 'raw' not in p.relative_to(bundle).parts and p.name != 'checksums.json'}
(bundle / 'checksums.json').write_text(json.dumps(checks, indent=2) + '\n')
print(bundle / 'REPORT.md')
