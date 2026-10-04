"""Synchronized channel-to-ADC service latency and serial update throughput."""
import argparse
import json
import os
from pathlib import Path
import resource
from time import perf_counter


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tx', type=int, default=2)
    p.add_argument('--rx', type=int, choices=(1, 2), default=1)
    p.add_argument('--iterations', type=int, default=30)
    p.add_argument('--warmup', type=int, default=5)
    p.add_argument('--samples', type=int, default=4096)
    p.add_argument('--samples-per-link', type=int, default=1028)
    p.add_argument('--backend', choices=('cpu', 'cuda'), default='cpu')
    p.add_argument("--profile", action="store_true", help="Separate instrumented Dr.Jit event/NVTX run")
    p.add_argument("--threads", type=int, default=2)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if min(args.tx, args.iterations, args.samples) < 1 or args.warmup < 0 or args.samples_per_link < 2 or args.threads < 1:
        p.error('Positive counts, >=2 attempts/link and nonnegative warmup required')
    import numpy as np
    import drjit as dr
    import mitsuba as mi
    dr.set_thread_count(args.threads)
    if args.backend == 'cuda' and not dr.has_backend(dr.JitBackend.CUDA):
        p.error('CUDA unavailable; no implicit CPU fallback')
    mi.set_variant('cuda_ad_mono_polarized' if args.backend == 'cuda' else 'llvm_ad_mono_polarized')
    import sionna.rt as rt
    from airsim_rf.sdr import PlutoSDRProfile, RadioClock, SDREmitter, SDRNetworkReceiver
    from airsim_rf.runtime_metrics import receiver_gpu_workload, conditional_gpu_ray_times
    from airsim_rf.profiling import CaptureProfiler, summarize_kernel_history
    profiler = CaptureProfiler() if args.profile else None
    root = Path(__file__).resolve().parents[1]
    start = perf_counter()
    scene = rt.load_scene(str(root/'benchmarks/scenes/terrain.xml'))
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='hw_dipole', polarization='V')
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='hw_dipole', polarization='V')
    if args.tx == 2:
        tx_pos = np.array([[-60, -30, 12], [45, 45, 18]], dtype=float)
        tx_vel = np.array([[2, 0, 0], [-1, 0, 0]], dtype=float)
        frequencies, powers, clocks = [150e3, -200e3], [1e-3, 1e-6], [RadioClock(12, .2), RadioClock(-8, 1.1)]
    else:
        tx_pos = np.column_stack((np.zeros(args.tx), np.linspace(-25, 25, args.tx), np.full(args.tx, 10.)))
        tx_vel = np.tile([1., 0, 0], (args.tx, 1))
        frequencies, powers = np.linspace(-250e3, 250e3, args.tx), np.full(args.tx, 1e-6)
        clocks = [RadioClock(float(x), float(i*.1)) for i, x in enumerate(np.linspace(-20, 20, args.tx))]
    rx_pos = np.array([[-30, -10, 14], [30, -50, 20]], dtype=float)[:args.rx]
    rx_vel = np.array([[3, 0, 0], [0, 3, 0]], dtype=float)[:args.rx]
    devices, emitters = [], {}
    for i in range(args.tx):
        name = f'beacon_{i}'
        device = rt.Transmitter(name, position=tx_pos[i].tolist(), velocity=tx_vel[i].tolist())
        scene.add(device)
        devices.append(device)
        frequency = float(frequencies[i])
        emitters[name] = SDREmitter(lambda t, f=frequency: np.exp(2j*np.pi*f*t),
            transmit_power_w=float(powers[i]), clock=clocks[i], baseband_frequency_bounds_hz=(frequency, frequency))
    rx_clocks = {}
    for i in range(args.rx):
        name = f'listener_{i}'
        device = rt.Receiver(name, position=rx_pos[i].tolist(), velocity=rx_vel[i].tolist())
        scene.add(device)
        devices.append(device)
        rx_clocks[name] = [RadioClock(5, -.7), RadioClock(-10, .4)][i]
    receiver = SDRNetworkReceiver(scene, emitters, PlutoSDRProfile(), clocks=rx_clocks,
        samples_per_link=args.samples_per_link)
    preparation_ms = 1000*(perf_counter()-start)
    positions, velocities = np.vstack((tx_pos, rx_pos)), np.vstack((tx_vel, rx_vel))

    def run(index, phase):
        dr.sync_thread()
        if profiler is not None:
            dr.kernel_history_clear()
            profiler.take_host_ranges()
        start = perf_counter()
        epoch = index/200.
        for i, device in enumerate(devices):
            device.position = (positions[i]+velocities[i]*epoch).tolist()
        pose_ms = 1000*(perf_counter()-start)
        capture_start = perf_counter()
        if profiler is None:
            captures = receiver.capture(round(epoch*1e9), num_samples=args.samples)
        else:
            with dr.scoped_set_flag(dr.JitFlag.KernelHistory, True), profiler.activate():
                with profiler.range(f"capture.{phase}.{index}"):
                    captures = receiver.capture(round(epoch*1e9), num_samples=args.samples)
        finish = perf_counter()
        capture_ms = 1000*(finish-capture_start)
        row = dict(epoch_s=epoch, service_ms=1000*(finish-start), pose_ms=pose_ms,
            capture_ms=capture_ms, channel_ms=receiver.last_channel_ms,
            cpu_iq_receiver_ms=capture_ms-receiver.last_channel_ms,
            stage_timings=receiver.solver.stage_timings,
            retained_paths=sum(sum(cap.retained_paths.values()) for cap in captures.values()),
            clipping_fraction_max=max(cap.clipped_component_fraction for cap in captures.values()))
        if profiler is not None:
            dr.sync_thread()
            row["profile"] = summarize_kernel_history(dr.kernel_history())
            row["profile"]["host_ranges"] = profiler.take_host_ranges()
            row["profile"]["nvtx_available"] = profiler.nvtx is not None
            if args.backend == "cuda" and not row["profile"]["cuda_operation_count"]:
                raise RuntimeError("Instrumented CUDA capture recorded no CUDA operations")
        return row

    first = run(0, "first")
    for i in range(args.warmup):
        run(i+1, "warmup")
    start = perf_counter()
    rows = []
    for i in range(args.iterations):
        row = run(i+args.warmup+1, "timed")
        rows.append(row)
        if (i+1) % 5 == 0:
            print(f'{i+1}/{args.iterations}: {row["service_ms"]:.1f} ms', flush=True)
    serial_wall_s = perf_counter()-start

    def stats(values):
        return dict(p50_ms=float(np.median(values)), p95_ms=float(np.percentile(values, 95)),
                    mean_ms=float(np.mean(values)), max_ms=float(np.max(values)))
    times = np.array([r['service_ms'] for r in rows])
    workload = receiver_gpu_workload(transmitters=args.tx, receivers=10,
        attempts_per_link=args.samples_per_link, specular_planes=receiver.planes, pulse_hz=200)
    host = np.median([r['stage_timings']['host_numpy_sampling_ms'] for r in rows]) if args.rx == 1 else None
    result = dict(arguments={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        measurement_mode='instrumented_profile' if args.profile else 'unprofiled_benchmark',
        scope='915 MHz, 2 MS/s, 1 MHz filter, noisy independent-clock Pluto profile; moving mounts over 800-triangle DEM',
        timing_includes='Pose writes, synchronized channel/NumPy export, per-path IQ, per-link diagnostic filters, receive noise/filter and ADC conversion',
        timing_excludes=['AirSim RPC/physics', 'transport', 'queueing', 'storage', 'plots', 'RF skill processing'],
        initial_tx_positions_m=tx_pos.tolist(), initial_rx_positions_m=rx_pos.tolist(),
        capture_duration_ms=args.samples/2e6*1000, filter_warmup_samples=256,
        preparation_ms=preparation_ms, first_capture=first,
        first_capture_note='New process with existing on-disk JIT cache; imports excluded; not a cache-cleared cold-start benchmark',
        service=stats(times), channel=stats([r['channel_ms'] for r in rows]),
        cpu_iq_receiver=stats([r['cpu_iq_receiver_ms'] for r in rows]),
        serial_wall_s=serial_wall_s, sustained_updates_hz=args.iterations/serial_wall_s,
        receiver_blocks_per_second=args.iterations*args.rx/serial_wall_s,
        deadline_misses={str(hz):int((times>1000/hz).sum()) for hz in (120,200)},
        stage_timings={key:stats([r['stage_timings'][key] for r in rows]) for key in rows[0]['stage_timings']},
        retained_paths=dict(min=min(r['retained_paths'] for r in rows), max=max(r['retained_paths'] for r in rows)),
        host=dict(cpu_count=os.cpu_count(), cpu_quota=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
            memory_limit_bytes=Path('/sys/fs/cgroup/memory.max').read_text().strip(), drjit_threads=dr.thread_count(),
            peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
            cuda_available=dr.has_backend(dr.JitBackend.CUDA)),
        versions=dict(sionna_rt=rt.__version__, mitsuba=mi.__version__, drjit=dr.__version__, backend=mi.variant()),
        gpu_workload_per_receiver=workload,
        conditional_gpu_ray_stage=conditional_gpu_ray_times(workload,host_sampling_ms=None if host is None else float(host)),
        profile_note='Profiled serial throughput includes event/history instrumentation; use separate unprofiled runs for performance.',
        gpu_note='Ray-only hypothetical query throughput. IQ/receive chain and proposal draws remain CPU even with --backend cuda. No measured GPU latency or throughput.',
        samples=rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('service','channel','cpu_iq_receiver','sustained_updates_hz','retained_paths','host')},indent=2))


if __name__ == '__main__':
    main()
