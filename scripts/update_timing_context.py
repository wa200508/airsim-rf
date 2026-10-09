#!/usr/bin/env python3
"""Normalize recorded wall costs by actual output signal duration, without rerunning benchmarks."""
import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = '<!-- BEGIN SIGNAL TIME CONTEXT -->'
END = '<!-- END SIGNAL TIME CONTEXT -->'


def measurements(path):
    try:
        d = json.loads(path.read_text())
    except (ValueError, OSError):
        return []
    if not isinstance(d, dict):
        return []
    args = d.get('arguments', {})
    scope = d.get('scope', '')
    mode = d.get('measurement_mode', 'historical')
    results = []
    if scope in ('rf_pipeline_end_to_end', 'live_airsim_rf_end_to_end'):
        rows = d['samples']
        results.append(('RF fleet update', mode, len(rows), sum(r['total_ms'] for r in rows),
                        sum(r['samples'] for r in rows) / d['sample_rate_hz'] * 1000))
    elif scope == 'doppler_basis_receiver_rendering' and isinstance(d.get('rows'), list) and d['rows']:
        rows = d['rows']
        results.append(('Renderer call', mode, len(rows), sum(r['total_ms'] for r in rows),
                        len(rows) * args['samples'] / args['sample_rate'] * 1000))
    elif scope == 'research_doppler_basis_fft':
        for name, rows in d['rows'].items():
            if rows:
                results.append((f'Renderer call ({name})', mode, len(rows), sum(r['total_ms'] for r in rows),
                                len(rows) * d['sample_duration_ms']))
    elif d.get('capture_duration_ms') and isinstance(d.get('samples'), list) and d['samples']:
        rows = d['samples']
        if all('service_ms' in r for r in rows):
            results.append(('Local RF service', mode, len(rows), sum(r['service_ms'] for r in rows),
                            len(rows) * d['capture_duration_ms']))
    return [(path, *r) for r in results]


def context(records, parent):
    lines = [BEGIN, '', '**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.', '',
             '| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for path, scope, mode, n, wall, signal in records:
        link = os.path.relpath(path, parent)
        label = os.path.relpath(path, ROOT)
        lines.append(f'| [{label}]({link}) — {scope} | {mode} | {n} | {signal/n:.6f} | {signal/1000:.6f} | {wall/1000:.6f} | {wall/signal:.3f} |')
    lines.extend(['', 'The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).', '', END])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    opts = parser.parse_args()
    records = []
    for directory in ('results', 'research_results', 'benchmarks/results'):
        for path in sorted((ROOT / directory).rglob('*.json')):
            records.extend(measurements(path))
    by_path = {}
    for r in records:
        by_path.setdefault(r[0], []).append(r)
    changed = []
    catalog = ROOT / 'SIGNAL_TIME_RESULTS.md'
    contents = '# Recorded wall time per simulated signal second\n\nThis index preserves historical configurations and failed qualification labels; a listed timing is not automatically a qualified result. For scope, qualification and hardware follow each raw case and its original report. [Definitions](TIMING_CONVENTIONS.md).\n\n' + context(records, ROOT) + '\n'
    targets = {catalog: contents}
    for path in sorted(ROOT.rglob('*.md')):
        if '.git' in path.parts or '.venv' in path.parts or path.name in ('SIGNAL_TIME_RESULTS.md', 'TIMING_AUDIT.md', 'TIMING_CONVENTIONS.md'):
            continue
        original = path.read_text()
        if '**Timing scope:**' not in original and not re.search(r'(?i)\b(?:timings?|latency|throughput|speedup|wall time|service time|median)\b', original):
            continue
        selected = set()
        for match in re.finditer(r'(?:\]\(|`)([^\s)`]+\.json)(?:\)|`)', original):
            name = match.group(1)
            for candidate in (path.parent/name, ROOT/name):
                candidate = candidate.resolve()
                if candidate in by_path:
                    selected.add(candidate)
        if path.name in ('REPORT.md', 'FINDINGS.md', 'README.md') and path.is_relative_to(ROOT/'results'):
            selected.update(p for p in by_path if p.is_relative_to(path.parent))
        selected.update(p for p in by_path if path.is_relative_to(ROOT/'research_results') and p.parent == path.parent)
        local = [r for r in records if r[0] in selected]
        # Every timing-bearing document states units/denominator, even if it only contains planning estimates.
        fallback = ('**Simulation-time reference:** use **wall seconds per simulated signal second**, not an unlabeled whole-run time. For fixed windows, divide mean service milliseconds by samples/sample-rate × 1,000. Stage costs use their parent window denominator. Geometry-only solves and analytic operation counts have no generated signal duration; a signal-time ratio is **not applicable**, unless an explicit update interval is assumed and labeled as a scheduling estimate. Unrecorded flight costs remain unknown. See [recorded normalized cases](' + os.path.relpath(catalog, path.parent) + ').')
        block = context(local, path.parent) if local else BEGIN+'\n\n'+fallback+'\n\n'+END
        if BEGIN in original:
            before, rest = original.split(BEGIN, 1)
            _, after = rest.split(END, 1)
            updated = before+block+after
        else:
            # Place denominator before detailed claims/tables, after title and scope note.
            updated = original.rstrip()+'\n\n'+block+'\n'
        targets[path] = updated
    for path, updated in targets.items():
        if not path.exists() or path.read_text() != updated:
            changed.append(str(path.relative_to(ROOT)))
            if not opts.check:
                path.write_text(updated)
    if opts.check and changed:
        raise SystemExit('Stale signal-time context: '+', '.join(changed))
    print(f'{len(records)} recorded cases; '+ ('contexts match.' if opts.check else f'{len(changed)} documents updated.'))


if __name__ == '__main__':
    main()
