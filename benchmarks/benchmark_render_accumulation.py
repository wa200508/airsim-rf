"""Compare equal-path contribution buffers with local atomic accumulation.

Standalone analytic tone/LFM kernel experiment, not arbitrary-I/Q or end-to-end
qualification. Each directed link has private inputs and output; no source
buffer reuse is credited. CUDA requests fail if no CUDA device is present.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
from time import perf_counter

import drjit as dr
import numpy as np

from airsim_rf.rendering import LFMChirpWaveform, ToneWaveform, render_paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('llvm', 'cuda'), default='llvm')
    parser.add_argument('--links', type=int, default=4)
    parser.add_argument('--paths', type=int, default=1028)
    parser.add_argument('--samples', type=int, default=16667)
    parser.add_argument('--sample-rate', type=float, default=2e6)
    parser.add_argument('--max-delay-us', type=float, default=100.)
    parser.add_argument('--max-doppler-hz', type=float, default=2500.)
    parser.add_argument('--path-tiles', type=int, nargs='+', default=[128, 1028])
    parser.add_argument('--sample-tile', type=int, default=32)
    parser.add_argument('--warmup', type=int, default=2)
    parser.add_argument('--iterations', type=int, default=10)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--seed', type=int, default=20261004)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if min(args.links, args.paths, args.samples, args.sample_tile, args.iterations,
           args.threads, *args.path_tiles) < 1 or args.warmup < 0:
        parser.error('Positive sizes and nonnegative warmup required')
    if not all(np.isfinite(v) and v > 0 for v in
               (args.sample_rate, args.max_delay_us, args.max_doppler_hz)):
        parser.error('Positive finite sample rate and channel ranges required')
    kind = dr.JitBackend.CUDA if args.backend == 'cuda' else dr.JitBackend.LLVM
    if not dr.has_backend(kind):
        parser.error(f'{args.backend} unavailable; no CPU fallback')
    dr.set_thread_count(args.threads)
    rng = np.random.default_rng(args.seed)
    # Separate allocations and random channels for every directed link. Keep
    # link-private data resident on the host; existing renderer uploads on each
    # call. This measures current transfer/launch costs as well as accumulation.
    links = []
    for _ in range(args.links):
        gain = (rng.normal(size=args.paths)+1j*rng.normal(size=args.paths))/np.sqrt(2*args.paths)
        delay = rng.uniform(0., args.max_delay_us*1e-6, args.paths)
        doppler = rng.uniform(-args.max_doppler_hz, args.max_doppler_hz, args.paths)
        waves = dict(tone=ToneWaveform(rng.uniform(-.2, .2)*args.sample_rate,
                                       rng.uniform(-np.pi, np.pi)),
                     lfm=LFMChirpWaveform(rng.uniform(.2, .8)*args.sample_rate,
                                          .6*args.samples/args.sample_rate,
                                          phase_rad=rng.uniform(-np.pi, np.pi)))
        links.append((gain, delay, doppler, waves))
    kw = dict(sample_rate_hz=args.sample_rate, num_samples=args.samples,
              sample_tile=args.sample_tile, sim_time_ns=100000,
              channel_epoch_ns=0)
    records = []
    validation_links = min(4, args.links)
    for family in ('tone', 'lfm'):
        references = [render_paths(g, delay, fd, waves[family], backend='numpy', **kw)
                      for g, delay, fd, waves in links[:validation_links]]
        for tile in args.path_tiles:
            for mode in ('partial', 'local'):
                def run():
                    dr.sync_thread()
                    start = perf_counter()
                    checksum = 0.
                    for gain, delay, fd, waves in links:
                        output = render_paths(gain, delay, fd, waves[family],
                                              backend=args.backend, path_tile=tile,
                                              accumulation=mode, **kw)
                        checksum += float(output[0].real+output[-1].imag)
                    dr.sync_thread()
                    return (perf_counter()-start)*1000, checksum

                first_ms, _ = run()
                for _ in range(args.warmup):
                    run()
                timings, checksums = zip(*(run() for _ in range(args.iterations)))
                errors = []
                for reference, (gain, delay, fd, waves) in zip(references, links):
                    output = render_paths(gain, delay, fd, waves[family],
                                          backend=args.backend, path_tile=tile,
                                          accumulation=mode, **kw)
                    difference = output-reference
                    scale = max(float(np.sqrt(np.mean(abs(reference)**2))), 1e-30)
                    rms_relative = float(np.sqrt(np.mean(abs(difference)**2)))/scale
                    max_absolute = float(np.max(abs(difference)))
                    # FP64 analytic check; absolute error also catches gated
                    # zeros. This threshold is not a receiver noise-floor spec.
                    if rms_relative > 1e-9 or max_absolute > 1e-8:
                        raise RuntimeError(f'{family}/{mode}: accuracy check failed')
                    errors.append(dict(rms_relative=rms_relative, max_absolute=max_absolute))
                record = dict(waveform=family, accumulation=mode, path_tile=tile,
                              first_run_ms=first_ms, timed_ms=list(timings),
                              p50_ms=float(np.median(timings)),
                              p95_ms=float(np.percentile(timings, 95)),
                              max_ms=max(timings), output_checksum_range=[min(checksums), max(checksums)],
                              reference_errors=errors,
                              explicit_contribution_buffer_peak_bytes=(
                                  16*min(tile, args.paths)*args.samples if mode == 'partial' else 0))
                records.append(record)
                print(f'{family:4s} {mode:7s} paths/tile={tile}: '
                      f'median {record["p50_ms"]:.2f} ms for {args.links} private links', flush=True)
    root = Path(__file__).resolve().parents[1]
    try:
        devices = subprocess.run(['nvidia-smi', '--query-gpu=name,uuid,driver_version,memory.total',
                                  '--format=csv,noheader'], capture_output=True, text=True)
        gpu_identity = devices.stdout.strip() if devices.returncode == 0 else 'nvidia-smi query failed'
    except FileNotFoundError:
        gpu_identity = 'nvidia-smi unavailable'
    result = dict(arguments={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                  scope='Standalone FP64 analytic tone/LFM direct renderer; independent directed-link jobs',
                  includes=['host phase preparation', 'per-link allocation/upload',
                            'synchronized execution/reduction', 'per-link output download'],
                  excludes=['arbitrary sampled inputs/interpolation', 'propagation', 'receiver frontend',
                            'AirSim/AMS', 'transport', 'queueing'],
                  no_transmitter_buffer_sharing=True, validation_links=validation_links,
                  contributions_per_capture=args.links*args.paths*args.samples,
                  deadline_ms=1000/120,
                  first_run_note='First call for this configuration in this process; existing disk JIT cache is retained',
                  host=dict(cpu_count=os.cpu_count(), drjit_threads=dr.thread_count(),
                            cpu_quota=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
                            peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024),
                  drjit_version=dr.__version__,
                  gpu_identity=gpu_identity,
                  source_sha256={name: hashlib.sha256((root/name).read_bytes()).hexdigest()
                                 for name in ('src/airsim_rf/rendering.py',
                                              'benchmarks/benchmark_render_accumulation.py')},
                  source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  source_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()),
                  cases=records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
