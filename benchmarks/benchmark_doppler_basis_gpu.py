"""Renderer-only CPU/CuPy comparison: private inputs, all paths, changing channels."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from airsim_rf.batched_rendering import BatchedPathRenderer, PathRenderJob
from airsim_rf.sampled_waveform import SampledWaveform
from airsim_rf.research.doppler_basis import DopplerBasisRenderer
from airsim_rf.research.doppler_basis_cuda import CudaDopplerBasisRenderer


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend', choices=('cpu', 'cuda'), required=True)
    p.add_argument('--tx', type=int, default=100)
    p.add_argument('--rx', type=int, default=1)
    p.add_argument('--paths', type=int, default=1028)
    p.add_argument('--samples', type=int, default=16667)
    p.add_argument('--sample-rate', type=float, default=2e6)
    p.add_argument('--max-delay-us', type=float, default=100.)
    p.add_argument('--max-doppler-hz', type=float, default=2500.)
    p.add_argument('--taps', type=int, default=32)
    p.add_argument('--block-samples', type=int, default=2048)
    p.add_argument('--batch-links', type=int, default=8)
    p.add_argument('--tolerance', type=float, default=1e-10)
    p.add_argument('--iterations', type=int, default=30)
    p.add_argument('--warmup', type=int, default=3)
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--profile-only', action='store_true', help='Instrumented timings never enter throughput table')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if min(args.tx,args.rx,args.paths,args.samples,args.block_samples,args.batch_links,args.iterations,args.threads) < 1 or args.warmup < 0:
        p.error('Positive counts and nonnegative warmup required')
    cfg = dict(sample_rate_hz=args.sample_rate, max_delay_s=args.max_delay_us*1e-6,
               max_doppler_hz=args.max_doppler_hz, block_samples=args.block_samples,
               temporal_tolerance=args.tolerance)
    engine = CudaDopplerBasisRenderer(**cfg, batch_links=args.batch_links) if args.backend == 'cuda' else DopplerBasisRenderer(**cfg, fft_workers=args.threads)
    rng = np.random.default_rng(20261004)
    tick = perf_counter()
    guard = args.taps+32
    history = int(np.ceil(args.max_delay_us*1e-6*args.sample_rate))+guard
    source_count = args.samples+history+guard
    jobs = []
    for receiver in range(args.rx):
        private = []
        for tx in range(args.tx):
            # Same transmitted data across receivers, but regenerate/copy into
            # private allocations. No input/transform reuse is credited.
            source_rng = np.random.default_rng(20261004+tx)
            spectrum = np.fft.fft(source_rng.normal(size=source_count)+1j*source_rng.normal(size=source_count))
            spectrum[abs(np.fft.fftfreq(source_count)) > .45] = 0
            source = SampledWaveform(np.fft.ifft(spectrum), args.sample_rate,
                                     -round(history/args.sample_rate*1e9), args.taps)
            gain = (rng.normal(size=args.paths)+1j*rng.normal(size=args.paths))/np.sqrt(2*args.paths)
            private.append(PathRenderJob(gain, rng.uniform(0,cfg['max_delay_s'],args.paths),
                rng.uniform(-args.max_doppler_hz,args.max_doppler_hz,args.paths), source,
                frequency_offset_hz=source_rng.uniform(-20000,20000), phase_offset_rad=source_rng.uniform(-np.pi,np.pi)))
        jobs.append(private)
    generation_ms = (perf_counter()-tick)*1000

    def evolving(epoch):
        # Synthetic channel epochs change ALL path arrays while remaining in
        # the declared ranges. These are not scene or pose-derived channels.
        return [[replace(job,
            coefficients=job.coefficients*np.exp(1j*.017*epoch),
            delays_s=np.remainder(job.delays_s+epoch*cfg['max_delay_s']*.001, cfg['max_delay_s'])
                if cfg['max_delay_s'] else job.delays_s,
            doppler_hz=np.clip(job.doppler_hz+args.max_doppler_hz*.0003*np.sin(epoch),
                               -args.max_doppler_hz,args.max_doppler_hz)) for job in private] for private in jobs]

    def capture(selected, profile=False):
        output, metrics = [], []
        for private in selected:
            if args.backend == 'cuda':
                signal = engine.render(private, num_samples=args.samples, sum_output=True, profile=profile)
            else:
                signal = engine.render(private, num_samples=args.samples).sum(axis=0)
            output.append(signal)
            metrics.append(dict(engine.last_metrics))
        return np.asarray(output), metrics

    tick = perf_counter()
    capture(evolving(0))
    first_ms = (perf_counter()-tick)*1000
    for i in range(args.warmup):
        capture(evolving(i+1))
    rows = []
    for i in range(args.iterations):
        selected = evolving(i+args.warmup+1)
        tick = perf_counter()
        actual, metrics = capture(selected, profile=args.profile_only)
        rows.append(dict(total_ms=(perf_counter()-tick)*1000, receiver_metrics=metrics,
                         channel_epoch_index=i+args.warmup+1))
    # Full all-job/all-sample comparison to the CPU basis oracle. Separate
    # finite direct checks validate the basis rather than merely itself.
    expected = np.asarray([DopplerBasisRenderer(**cfg, fft_workers=args.threads).render(private,
        num_samples=args.samples).sum(axis=0) for private in selected])
    rms = float(np.sqrt(np.mean(abs(actual-expected)**2)/max(np.mean(abs(expected)**2),1e-30)))
    direct = BatchedPathRenderer(backend='llvm', sample_tile=128)
    direct_checks = []
    for receiver, private in enumerate(selected):
        for start in dict.fromkeys([0, max(0,args.samples-128)]):
            n = min(128,args.samples-start)
            reference = direct.render(private, sample_rate_hz=args.sample_rate, num_samples=n,
                sim_time_ns=round(start/args.sample_rate*1e9), channel_epoch_ns=0, sum_output=True)
            error = actual[receiver,start:start+n]-reference
            normalized = float(np.sqrt(np.mean(abs(error)**2)/max(np.mean(abs(reference)**2),1e-30)))
            direct_checks.append(dict(receiver=receiver, start_sample=start, samples=n,
                paths_checked=args.tx*args.paths, normalized_rms_error=normalized,
                max_absolute_error=float(np.max(abs(error)))))
        for index in dict.fromkeys([0,len(private)-1]):
            job = private[index]
            oracle = direct.render([job], sample_rate_hz=args.sample_rate, num_samples=args.samples)[0]
            check = engine.render([job], num_samples=args.samples)[0]
            error = check-oracle
            direct_checks.append(dict(receiver=receiver, transmitter=index, samples=args.samples,
                paths_checked=args.paths, normalized_rms_error=float(np.linalg.norm(error)/max(np.linalg.norm(oracle),1e-30)),
                max_absolute_error=float(np.max(abs(error)))))
    passed = rms < max(1e-8,args.tolerance*100) and all(c['normalized_rms_error'] < max(1e-8,args.tolerance*100) for c in direct_checks)
    # Instrumented stage spans are collected independently from throughput.
    _, profile = capture(selected, profile=True) if args.backend == 'cuda' else (None, [])
    times = [r['total_ms'] for r in rows]
    mean = float(np.mean(times))
    deadline = 1000/120
    root = Path(__file__).resolve().parents[1]
    result = dict(scope='doppler_basis_receiver_rendering',
        measurement_mode='instrumented_basis_profile' if args.profile_only else 'unprofiled_basis_benchmark',
        utc=datetime.now(timezone.utc).isoformat(), arguments={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
        backend=args.backend, precision='complex128/float64', no_cpu_fallback=True,
        valid_paths=args.tx*args.rx*args.paths, private_source_bytes=sum(j.waveform.samples.nbytes for private in jobs for j in private),
        source_generation_ms=generation_ms, first_ms=first_ms, rows=rows,
        summary=dict(p50_ms=float(np.median(times)),p95_ms=float(np.percentile(times,95)),
                     p99_ms=float(np.percentile(times,99)),max_ms=max(times),mean_ms=mean),
        captures_per_second=1000/mean, output_samples_per_second_per_receiver=args.samples*1000/mean,
        deadline_ms=deadline, sample_window_ms=args.samples/args.sample_rate*1000,
        misses_120hz=sum(t>deadline for t in times), required_speedup_to_120hz=max(1.,mean/deadline),
        accuracy=dict(passed=passed, full_all_jobs_cpu_basis_normalized_rms=rms, direct_checks=direct_checks),
        profile_receivers=profile,
        includes=['private input copies/uploads','fresh delay map and GPU temporal construction','all paths and intra-block Doppler',
                  'private FFTs','coherent receiver sum','synchronized final receiver output export'],
        excludes=['source generation','scene propagation','sample-clock resampling','noise/filter/ADC','AirSim','transport/queues'],
        scope_note='Synthetic changing channels; equal clocks; entire-window synchronized renderer service, not a continuous receiver pipeline',
        cpu_quota=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
        source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
            ('src/airsim_rf/research/doppler_basis_cuda.py','src/airsim_rf/research/doppler_basis.py',
             'benchmarks/benchmark_doppler_basis_gpu.py','requirements-p100-cuda.txt')})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('backend','summary','captures_per_second','misses_120hz','accuracy')},indent=2))
    if not passed:
        raise SystemExit('Accuracy qualification failed; timings are not validated performance')


if __name__ == '__main__':
    main()
