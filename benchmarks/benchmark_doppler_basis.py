"""Matched all-valid-path direct versus Doppler-basis FFT research comparison."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter

import drjit as dr
import numpy as np

from airsim_rf.batched_rendering import BatchedPathRenderer, PathRenderJob
from airsim_rf.sampled_waveform import SampledWaveform
from airsim_rf.research.doppler_basis import DopplerBasisRenderer


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--links', type=int, default=1)
    p.add_argument('--paths', type=int, default=1028)
    p.add_argument('--samples', type=int, default=16667)
    p.add_argument('--sample-rate', type=float, default=2e6)
    p.add_argument('--max-delay-us', type=float, default=100.)
    p.add_argument('--max-doppler-hz', type=float, default=2500.)
    p.add_argument('--taps', type=int, default=32)
    p.add_argument('--block-samples', type=int, default=2048)
    p.add_argument('--tolerance', type=float, default=1e-10)
    p.add_argument('--iterations', type=int, default=5)
    p.add_argument('--warmup', type=int, default=2)
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--skip-direct-timing', action='store_true', help='Still validates every first-link output against direct')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if min(args.links, args.paths, args.samples, args.block_samples, args.iterations, args.threads) < 1 or args.warmup < 0:
        p.error('Positive sizes and nonnegative warmup required')
    dr.set_thread_count(args.threads)
    basis = DopplerBasisRenderer(sample_rate_hz=args.sample_rate, max_delay_s=args.max_delay_us*1e-6,
                                max_doppler_hz=args.max_doppler_hz, block_samples=args.block_samples,
                                temporal_tolerance=args.tolerance, fft_workers=args.threads)
    direct = BatchedPathRenderer(backend='llvm', sample_tile=128)
    rng = np.random.default_rng(20261004)
    tick = perf_counter()
    guard = args.taps+32
    history = int(np.ceil(args.max_delay_us*1e-6*args.sample_rate))+guard
    source_count = args.samples+history+guard
    jobs = []
    for _ in range(args.links):
        spectrum = np.fft.fft(rng.normal(size=source_count)+1j*rng.normal(size=source_count))
        spectrum[abs(np.fft.fftfreq(source_count)) > .45] = 0
        source = np.fft.ifft(spectrum)
        wave = SampledWaveform(source, args.sample_rate, -round(history/args.sample_rate*1e9), args.taps)
        gain = (rng.normal(size=args.paths)+1j*rng.normal(size=args.paths))/np.sqrt(2*args.paths)
        delay = rng.uniform(0, args.max_delay_us*1e-6, args.paths)
        fd = rng.uniform(-args.max_doppler_hz, args.max_doppler_hz, args.paths)
        jobs.append(PathRenderJob(gain, delay, fd, wave,
                                  frequency_offset_hz=rng.uniform(-20000, 20000),
                                  phase_offset_rad=rng.uniform(-np.pi, np.pi)))
    generation_ms = (perf_counter()-tick)*1000
    kw = dict(num_samples=args.samples, sim_time_ns=0, channel_epoch_ns=-3_000_000)

    def run(kind, selected):
        if kind == 'basis':
            private = basis.render(selected, **kw)
        else:
            private = direct.render(selected, sample_rate_hz=args.sample_rate, **kw)
        return np.sum(private, axis=0)

    first, rows = {}, {'basis': [], 'direct': []}
    kinds = ['basis'] if args.skip_direct_timing else ['basis', 'direct']
    for kind in kinds:
        tick = perf_counter()
        run(kind, jobs)
        first[kind] = (perf_counter()-tick)*1000
        for _ in range(args.warmup):
            run(kind, jobs)
    for i in range(args.iterations):
        # Alternating measurement order reduces a simple first/second bias.
        for kind in kinds if i % 2 == 0 else kinds[::-1]:
            tick = perf_counter()
            run(kind, jobs)
            rows[kind].append(dict(total_ms=(perf_counter()-tick)*1000,
                                   metrics=dict(basis.last_metrics if kind == 'basis' else direct.last_metrics)))
    # Full output comparison on ALL paths, first private link. Separate from
    # timed execution. No prefix-only shortcut or scene attrition is used.
    reference = run('direct', jobs[:1])
    actual = run('basis', jobs[:1])
    error = actual-reference
    rms = float(np.sqrt(np.mean(abs(error)**2)/max(np.mean(abs(reference)**2), 1e-30)))
    max_error = float(np.max(abs(error)))
    if rms > max(1e-8, args.tolerance*100):
        raise RuntimeError(f'Full-output direct comparison failed: {rms}')
    root = Path(__file__).resolve().parents[1]
    summary = {kind:dict(p50_ms=float(np.median([r['total_ms'] for r in records])),
                        p95_ms=float(np.percentile([r['total_ms'] for r in records],95)))
               for kind, records in rows.items() if records}
    result = dict(scope='research_doppler_basis_fft', utc=datetime.now(timezone.utc).isoformat(),
        arguments={k:str(v) if isinstance(v, Path) else v for k,v in vars(args).items()},
        qualification='Equal sample clocks only; oscillator offsets enabled; not an integrated scene/receiver test',
        includes=['private source packing and FFT per link', 'all-path interpolation map rebuilt per capture',
                  'all-path temporal projection per block', 'overlap-save filtering and basis reconstruction',
                  'oscillator phase and coherent summation'],
        excludes=['scene propagation', 'clock resampling', 'noise/filter/ADC', 'AirSim', 'transport/queues', 'source generation'],
        no_source_sharing=True, valid_paths=args.links*args.paths,
        private_source_bytes=sum(j.waveform.samples.nbytes for j in jobs), source_generation_ms=generation_ms,
        sample_duration_ms=args.samples/args.sample_rate*1000, first_ms=first, rows=rows, summary=summary,
        speedup=(summary['direct']['p50_ms']/summary['basis']['p50_ms']) if 'direct' in summary else None,
        accuracy=dict(links_checked=1, paths_checked=args.paths, samples_checked=args.samples,
                      normalized_rms_error=rms, max_absolute_error=max_error,
                      temporal_only_absolute_error_bound=basis.last_metrics['temporal_only_absolute_error_bound'][0]),
        accuracy_scope='Agreement with finite Lanczos sampled reconstruction; ideal sinc and noise-floor qualification remain separate',
        cpu_quota=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
        source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
                      ('src/airsim_rf/research/doppler_basis.py','src/airsim_rf/batched_rendering.py',
                       'src/airsim_rf/sampled_waveform.py','benchmarks/benchmark_doppler_basis.py')})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('summary','speedup','accuracy')}, indent=2))


if __name__ == '__main__':
    main()
