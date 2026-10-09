#!/usr/bin/env python3
"""Regenerate comparable renderer timings from the published P100 JSON files."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path('results/profiling/p100-basis-optimized-full-20261004')
BEGIN = '<!-- BEGIN MEASURED RUNTIME TABLE -->'
END = '<!-- END MEASURED RUNTIME TABLE -->'


def table():
    lines = [
        '| Backend / TX → RX | Renderer-call wall median (n=30) | p95 | Wall seconds / signal second | Estimated wall time for 600 signal seconds |',
        '| --- | ---: | ---: | ---: | ---: |',
    ]
    for tx in (100, 4, 1):
        for backend in ('cpu', 'cuda'):
            path = RUN / 'profiles' / f'basis_{backend}_{tx}tx_1rx.json'
            data = json.loads((ROOT / path).read_text())
            args = data['arguments']
            assert data['accuracy']['passed']
            assert data['measurement_mode'] == 'unprofiled_basis_benchmark'
            assert (args['tx'], args['rx'], args['paths'], args['samples']) == (tx, 1, 1028, 16667)
            assert args['sample_rate'] == 2_000_000 and args['iterations'] == 30
            stats = data['summary']
            # Scheduling at 120 Hz: 72,000 renderer calls in ten minutes.
            # Mean cost, not a speedup ratio or a sum of instrumented stages.
            ratio = stats['mean_ms'] / (args['samples'] / args['sample_rate'] * 1000)
            minutes = 10 * ratio
            duration = f'{minutes / 60:.2f} h' if minutes >= 120 else f'{minutes:.2f} min'
            label = 'CPU' if backend == 'cpu' else 'P100 CUDA'
            lines.append(
                f'| [{label}, {tx} → 1]({path.as_posix()}) '
                f'| {stats["p50_ms"]:.2f} ms | {stats["p95_ms"]:.2f} ms '
                f'| {ratio:.2f}× | {duration} |'
            )
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if documentation differs from source JSON')
    args = parser.parse_args()
    stale = []
    for name in ('docs/archive/runtime.md',):
        path = ROOT / name
        current = path.read_text()
        assert current.count(BEGIN) == current.count(END) == 1
        before, rest = current.split(BEGIN)
        _, after = rest.split(END)
        updated = before + BEGIN + '\n\n' + table().replace('](results/', '](../../results/') + '\n\n' + END + after
        if updated != current:
            stale.append(name)
            if not args.check:
                path.write_text(updated)
    if args.check and stale:
        raise SystemExit('Stale runtime tables: ' + ', '.join(stale))
    print('Runtime tables match published JSON.' if args.check else 'Updated runtime tables from published JSON.')


if __name__ == '__main__':
    main()
