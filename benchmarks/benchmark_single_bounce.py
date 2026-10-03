"""Interleaved native/exhaustive single-reflection comparison on moving links.

Both solvers see identical poses. Timings include synchronized solving, one CIR
export and pose updates, but exclude the separate path-by-path comparison.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import resource
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--tx", type=int, default=100)
    parser.add_argument("--rx", type=int, default=1)
    parser.add_argument("--rays", type=int, default=10000)
    parser.add_argument("--path-cap", type=int, default=1000)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--threads", type=int, default=0, help="0 keeps Dr.Jit's default CPU thread count")
    parser.add_argument("--pulse-hz", type=float, default=200)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.tx, args.rx, args.rays, args.path_cap, args.iterations) < 1 or min(args.warmup, args.threads) < 0 or args.pulse_hz <= 0:
        parser.error("Counts/rate must be positive and warmup nonnegative")
    import numpy as np
    import drjit as dr
    if args.threads:
        dr.set_thread_count(args.threads)
    if args.backend == "cuda" and not dr.has_backend(dr.JitBackend.CUDA):
        parser.error("CUDA unavailable; no CPU fallback")
    import mitsuba as mi
    mi.set_variant("cuda_ad_mono_polarized" if args.backend == "cuda" else "llvm_ad_mono_polarized")
    import sionna.rt as rt
    from airsim_rf.single_bounce import SingleBouncePathSolver
    scene = rt.load_scene(rt.scene.simple_street_canyon)
    scene.frequency = 24.125e9
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    for i in range(args.tx):
        scene.add(rt.Transmitter(f"tx_{i}", position=[0, -25+50*i/max(args.tx-1, 1), 2], velocity=[1, 0, 0]))
    for i in range(args.rx):
        scene.add(rt.Receiver(f"rx_{i}", position=[2, -5+i, 2], velocity=[0, .5, 0]))
    solvers = {"native": rt.PathSolver(deterministic=True), "single-bounce": SingleBouncePathSolver()}
    options = dict(max_depth=1, samples_per_src=args.rays, max_num_paths_per_src=args.path_cap,
                   refraction=False, diffuse_reflection=False, diffraction=False, seed=42)

    def run(name, epoch):
        start = time.perf_counter()
        for i, tx in enumerate(scene.transmitters.values()):
            tx.position = [epoch, -25+50*i/max(args.tx-1, 1), 2]
        for i, rx in enumerate(scene.receivers.values()):
            rx.position = [2, -5+i+.5*epoch, 2]
        pose_ms = (time.perf_counter()-start)*1000
        paths = solvers[name](scene, **options)
        dr.eval(paths.a, paths.tau, paths.doppler)
        dr.sync_thread()
        after_solve = time.perf_counter()
        a, tau = paths.cir(num_time_steps=1, normalize_delays=False, out_type="numpy")
        fd = paths.doppler.numpy()
        finish = time.perf_counter()
        sample = {"total_ms": (finish-start)*1000, "pose_ms": pose_ms,
                  "solve_ms": (after_solve-start)*1000-pose_ms,
                  "cir_numpy_ms": (finish-after_solve)*1000,
                  "valid_paths": int((tau >= 0).sum())}
        return sample, (a, tau, fd)

    cold = {name: run(name, 0)[0] for name in solvers}
    for i in range(args.warmup):
        for name in solvers:
            run(name, (i+1)/args.pulse_hz)
    samples = []
    comparison = {"links_checked": 0, "max_delay_error_s": 0.,
                  "max_relative_magnitude_error": 0., "max_phase_error_rad": 0.,
                  "max_doppler_error_hz": 0.}
    for i in range(args.iterations):
        epoch = (i+args.warmup+1)/args.pulse_hz
        order = list(solvers) if i % 2 == 0 else list(reversed(solvers))
        pair, outputs = {}, {}
        for name in order:
            pair[name], outputs[name] = run(name, epoch)
        samples.append({"epoch_s": epoch, "order": order, **pair})
        # Sort each RX/TX's physical paths by delay before comparing. Padding
        # and native candidate order need not agree. This scene has no delay ties.
        na, nt, nf = outputs["native"]
        oa, ot, of = outputs["single-bounce"]
        for r in range(args.rx):
            for t in range(args.tx):
                ni = np.flatnonzero(nt[r, t] >= 0); ni = ni[np.argsort(nt[r, t, ni])]
                oi = np.flatnonzero(ot[r, t] >= 0); oi = oi[np.argsort(ot[r, t, oi])]
                if len(ni) != len(oi):
                    raise RuntimeError(f"Path-count mismatch at epoch {epoch}, RX {r}, TX {t}; native rays may not converge")
                comparison["links_checked"] += 1
                if not len(ni):
                    continue
                n, o = na[r, 0, t, 0, ni, 0], oa[r, 0, t, 0, oi, 0]
                delay_error = float(np.max(np.abs(nt[r, t, ni]-ot[r, t, oi])))
                # Paths with zero antenna gain have no meaningful phase.
                nonzero = np.abs(n) > 1e-20
                magnitude_error = float(np.max(np.abs(np.abs(n)-np.abs(o))/np.maximum(np.abs(n), 1e-20)))
                phase_error = float(np.max(np.abs(np.angle(o[nonzero]/n[nonzero])))) if nonzero.any() else 0.
                doppler_error = float(np.max(np.abs(nf[r, t, ni]-of[r, t, oi])))
                for key, value in zip(list(comparison)[1:], (delay_error, magnitude_error, phase_error, doppler_error)):
                    comparison[key] = max(comparison[key], value)
    # Physical regression guard for this fixed canyon fixture, allowing
    # float32 image construction and carrier-phase arithmetic differences.
    limits = {"max_delay_error_s": 3e-12, "max_relative_magnitude_error": 1e-3,
              "max_phase_error_rad": .02, "max_doppler_error_hz": .01}
    for key, limit in limits.items():
        if not np.isfinite(comparison[key]) or comparison[key] > limit:
            raise RuntimeError(f"Channel mismatch: {key}={comparison[key]} exceeds {limit}")
    summaries = {}
    for name in solvers:
        times = np.asarray([s[name]["total_ms"] for s in samples])
        summaries[name] = {"p50_ms": float(np.median(times)), "p95_ms": float(np.percentile(times, 95)),
                           "max_ms": float(times.max()), "deadline_misses_5ms": int((times > 5).sum()),
                           "deadline_misses_120hz": int((times > 1000/120).sum()),
                           "deadline_misses_pulse_budget": int((times > 1000/args.pulse_hz).sum()),
                           "valid_paths_min": min(s[name]["valid_paths"] for s in samples),
                           "valid_paths_max": max(s[name]["valid_paths"] for s in samples)}
    result = {"scope": "Specular-only one-way moving TX/RX; synchronized propagation plus one-epoch CIR/Doppler export",
              "ground_clutter_coverage": False,
              "excludes": ["IQ synthesis", "AirSim", "transport", "moving mesh/BVH updates"],
              "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
              "versions": {"sionna_rt": rt.__version__, "mitsuba": mi.__version__, "drjit": dr.__version__,
                           "backend": mi.variant(), "python": platform.python_version()},
              "host": {"cpu_count": os.cpu_count(), "cpu_quota": Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
                       "drjit_threads": dr.thread_count(),
                       "memory_limit": Path('/sys/fs/cgroup/memory.max').read_text().strip(),
                       "cpu_model": next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')), 'unknown'),
                       "peak_host_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024},
              "scene_triangles": sum(len(obj.mi_mesh.faces_buffer())//3 for obj in scene.objects.values()),
              "reflection_planes": solvers['single-bounce'].plane_count,
              "cold": cold, "summary": summaries, "channel_comparison": comparison,
              "median_speedup": summaries['native']['p50_ms']/summaries['single-bounce']['p50_ms'],
              "samples": samples,
              "notes": ["Alternating paired order reduces run-to-run bias", "RSS includes both solvers, not optimized-only memory or VRAM",
                        "Native and exhaustive discovery may differ in richer scenes; ray convergence remains scene dependent"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'samples'}, indent=2))


if __name__ == '__main__':
    main()
