"""Independent sampled-input rendering stress, without scene-dependent pruning."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

import drjit as dr
import numpy as np

from airsim_rf.batched_rendering import BatchedPathRenderer, PathRenderJob
from airsim_rf.sampled_waveform import SampledWaveform


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend', choices=('llvm', 'cuda'), default='llvm')
    p.add_argument('--links', type=int, default=4)
    p.add_argument('--paths', type=int, default=1028)
    p.add_argument('--samples', type=int, default=16667)
    p.add_argument('--sample-rate', type=float, default=2e6)
    p.add_argument('--max-delay-us', type=float, default=100.)
    p.add_argument('--max-doppler-hz', type=float, default=2500.)
    p.add_argument('--taps', type=int, default=32)
    p.add_argument('--sample-tile', type=int, default=32)
    p.add_argument('--max-lanes', type=int, default=1_000_000)
    p.add_argument('--warmup', type=int, default=2)
    p.add_argument('--iterations', type=int, default=10)
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--no-replay', action='store_true')
    p.add_argument('--reduction', choices=('auto','local','expand'), default='auto')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if min(args.links, args.paths, args.samples, args.sample_tile, args.max_lanes,
           args.iterations, args.threads) < 1 or args.warmup < 0:
        p.error('Positive sizes and nonnegative warmup required')
    if not all(np.isfinite(v) and v > 0 for v in (args.sample_rate, args.max_delay_us, args.max_doppler_hz)):
        p.error('Positive finite channel ranges and sample rate required')
    dr.set_thread_count(args.threads)
    engine = BatchedPathRenderer(backend=args.backend, sample_tile=args.sample_tile,
                                max_lanes=args.max_lanes, replay=not args.no_replay, reduction=args.reduction)
    rng = np.random.default_rng(20261004)
    start = perf_counter()
    guard = args.taps+32
    history = int(np.ceil(args.max_delay_us*1e-6*args.sample_rate))+guard
    source_count = args.samples+history+guard
    source_epoch_ns = -round(history/args.sample_rate*1e9)
    jobs = []
    for _ in range(args.links):
        # Independent full random modulation, occupying +/-0.45 fs. Each job
        # pays for separate generation/filtering; that cost is reported below.
        spectrum = np.fft.fft(rng.normal(size=source_count)+1j*rng.normal(size=source_count))
        spectrum[abs(np.fft.fftfreq(source_count)) > .45] = 0
        source = np.fft.ifft(spectrum)
        wave = SampledWaveform(source, args.sample_rate, source_epoch_ns, args.taps)
        gain = (rng.normal(size=args.paths)+1j*rng.normal(size=args.paths))/np.sqrt(2*args.paths)
        delay = rng.uniform(0, args.max_delay_us*1e-6, args.paths)
        doppler = rng.uniform(-args.max_doppler_hz, args.max_doppler_hz, args.paths)
        jobs.append(PathRenderJob(gain, delay, doppler, wave, time_scale=1+rng.uniform(-20, 20)*1e-6,
                                  frequency_offset_hz=rng.uniform(-20000, 20000), phase_offset_rad=rng.uniform(-np.pi, np.pi)))
    generation_ms = (perf_counter()-start)*1000
    kw = dict(sample_rate_hz=args.sample_rate, num_samples=args.samples, sum_output=True)
    dr.sync_thread()
    start = perf_counter()
    first = engine.render(jobs, **kw)
    first_ms = (perf_counter()-start)*1000
    first_metrics = engine.last_metrics
    for _ in range(args.warmup):
        engine.render(jobs, **kw)
    times, rows = [], []
    for _ in range(args.iterations):
        dr.sync_thread()
        start = perf_counter()
        output = engine.render(jobs, **kw)
        times.append((perf_counter()-start)*1000)
        rows.append(engine.last_metrics)
    # Numerical reference on all paths of one link, for a bounded prefix.
    # No path reduction in performance runs or this reference comparison.
    checked = min(args.samples, 128)
    job = jobs[0]
    t = np.arange(checked)/args.sample_rate
    reference = sum((g*job.waveform((t-delay)*job.time_scale)
                     * np.exp(1j*(2*np.pi*job.frequency_offset_hz*(t-delay)+job.phase_offset_rad))
                     * np.exp(2j*np.pi*fd*t)
                     for g, delay, fd in zip(job.coefficients, job.delays_s, job.doppler_hz)),
                    start=np.zeros(checked, complex))
    actual = engine.render([job], sample_rate_hz=args.sample_rate, num_samples=checked)[0]
    error = actual-reference
    normalized = float(np.sqrt(np.mean(abs(error)**2)/max(np.mean(abs(reference)**2), 1e-30)))
    if normalized > 1e-8:
        raise RuntimeError('Independent sampled-waveform equation comparison failed')
    # Separate instrumented execution after matching-shape warmup.
    dr.kernel_history_clear()
    with dr.scoped_set_flag(dr.JitFlag.KernelHistory, True):
        engine.render(jobs, **kw)
        dr.sync_thread()
    from airsim_rf.profiling import summarize_kernel_history
    profile = summarize_kernel_history(dr.kernel_history())
    root = Path(__file__).resolve().parents[1]
    result = dict(scope='standalone_sampled_renderer', utc=datetime.now(timezone.utc).isoformat(),
        arguments={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        includes=['private input/channel packing and transfers', 'finite fractional-delay interpolation',
                  'individual Doppler and clock evolution', 'coherent sum', 'synchronized final output export'],
        excludes=['scene tracing', 'frontend noise/filter/ADC', 'AirSim', 'transport', 'queueing'],
        source_generation_ms=generation_ms, private_source_bytes=sum(j.waveform.samples.nbytes for j in jobs),
        no_source_sharing=True, valid_paths=args.links*args.paths,
        contributions_per_capture=args.links*args.paths*args.samples,
        first_ms=first_ms, first_metrics=first_metrics, timed_ms=times, render_metrics=rows,
        p50_ms=float(np.median(times)), p95_ms=float(np.percentile(times, 95)),
        serial_captures_per_second=1000/float(np.mean(times)),
        sample_duration_ms=args.samples/args.sample_rate*1000,
        accuracy=dict(links_checked=1, samples_checked=checked, paths_checked=args.paths,
                      normalized_rms_error=normalized, max_absolute_error=float(np.max(abs(error)))),
        accuracy_scope='Checks equality to the same finite interpolation operator, not ideal sinc or noise-floor qualification',
        profile=profile, host=dict(cpu_count=os.cpu_count(), drjit_threads=dr.thread_count(),
                                  cpu_quota=Path('/sys/fs/cgroup/cpu.max').read_text().strip()),
        source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
                       ('src/airsim_rf/batched_rendering.py','src/airsim_rf/sampled_waveform.py',
                        'benchmarks/benchmark_batched_rendering.py')})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('p50_ms','p95_ms','valid_paths','contributions_per_capture','accuracy')},indent=2))


if __name__ == '__main__':
    main()
