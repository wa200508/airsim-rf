"""Measure independent moving TX/RX propagation, without the radar shortcut.

This is an isolated Sionna benchmark, not a general RF worker implementation.
It materializes one CIR epoch rather than expanding a paths-by-ADC-time cube.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--tx", type=int, default=100)
    parser.add_argument("--rx", type=int, default=1)
    parser.add_argument("--scene", default="builtin:simple_street_canyon")
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--rays", type=int, default=10000)
    parser.add_argument("--path-cap", type=int, default=1000)
    parser.add_argument("--tx-batch", type=int, default=0, help="0 means all TX in one solve")
    parser.add_argument("--diffuse", action="store_true")
    parser.add_argument("--scattering-coefficient", type=float, default=0.3,
                        help="Synthetic material coefficient used only with --diffuse")
    parser.add_argument("--diffraction", action="store_true")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--update-hz", type=float, default=120)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.tx, args.rx, args.rays, args.path_cap, args.iterations) < 1:
        parser.error("TX, RX, rays, path cap and iterations must be positive")
    if min(args.depth, args.tx_batch, args.warmup) < 0 or args.update_hz <= 0:
        parser.error("depth/batch/warmup must be nonnegative and rate positive")
    if args.path_cap < args.rx:
        parser.error("path cap must accommodate at least one path per receiver")
    if not 0 <= args.scattering_coefficient <= 1:
        parser.error("scattering coefficient must be in [0,1]")

    import numpy as np
    import drjit as dr
    if args.backend == "cuda" and not dr.has_backend(dr.JitBackend.CUDA):
        parser.error("CUDA is unavailable; CPU fallback is not allowed")
    import mitsuba as mi
    mi.set_variant("cuda_ad_mono_polarized" if args.backend == "cuda" else "llvm_ad_mono_polarized")
    import sionna.rt as rt
    scene_file = None if args.scene == "empty" else args.scene
    if scene_file and scene_file.startswith("builtin:"):
        scene_file = getattr(rt.scene, scene_file.split(":", 1)[1])
    setup_start = time.perf_counter()
    scene = rt.load_scene(scene_file)
    scene.frequency = 24.125e9
    if args.diffuse:
        # The built-in canyon's materials have zero scattering by default.
        # Enable actual diffuse energy rather than just toggling the solver.
        for material in scene.radio_materials.values():
            material.scattering_coefficient = args.scattering_coefficient
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    # A line of emitters along the canyon; this deliberately small geometry is
    # a repeatable scaling probe, not a representative operational scene.
    tx_positions = [(0., -25 + 50*i/max(args.tx-1, 1), 2.) for i in range(args.tx)]
    transmitters = [rt.Transmitter(f"tx_{i}", position=p, velocity=[1., 0., 0.])
                    for i, p in enumerate(tx_positions)]
    receivers = [rt.Receiver(f"rx_{i}", position=[2., -5.+i, 2.], velocity=[0., 0.5, 0.])
                 for i in range(args.rx)]
    for rx in receivers:
        scene.add(rx)
    batch_size = args.tx_batch or args.tx
    batches = [transmitters[i:i+batch_size] for i in range(0, args.tx, batch_size)]
    if len(batches) == 1:
        for tx in transmitters:
            scene.add(tx)
    solver = rt.PathSolver(deterministic=True)
    setup_ms = (time.perf_counter()-setup_start)*1000

    def update(index):
        started = time.perf_counter()
        epoch = index/args.update_hz
        for tx, pos in zip(transmitters, tx_positions):
            tx.position = [pos[0]+epoch, pos[1], pos[2]]
        for i, rx in enumerate(receivers):
            rx.position = [2., -5.+i+0.5*epoch, 2.]
        pose_ms = (time.perf_counter()-started)*1000
        solve_ms, cir_ms, valid_paths, padded_paths, cap_risk = 0., 0., 0, 0, False
        checksum = 0.
        for batch in batches:
            if len(batches) > 1:
                for tx in batch:
                    scene.add(tx)
            before = time.perf_counter()
            paths = solver(scene, max_depth=args.depth, samples_per_src=args.rays,
                           max_num_paths_per_src=args.path_cap,
                           diffuse_reflection=args.diffuse, diffraction=args.diffraction, seed=42)
            # Force completion on CPU or GPU before stopping the solve timer.
            dr.eval(paths.a, paths.tau, paths.doppler)
            dr.sync_thread()
            solve_ms += (time.perf_counter()-before)*1000
            before = time.perf_counter()
            a, tau = paths.cir(num_time_steps=1, normalize_delays=False, out_type="numpy")
            valid = np.isfinite(tau) & (tau >= 0)
            valid_paths += int(valid.sum())
            padded_paths += int(tau.size)
            # Reaching a cap is a warning, not proof of convergence below it:
            # candidates rejected later can also exhaust this capacity.
            cap_risk |= bool(np.any(valid.sum(axis=(0, 2)) >= args.path_cap))
            checksum += float(np.sum(np.abs(a)**2))
            cir_ms += (time.perf_counter()-before)*1000
            if len(batches) > 1:
                for tx in batch:
                    scene.remove(tx.name)
        return {"total_ms": (time.perf_counter()-started)*1000,
                "pose_ms": pose_ms, "solve_ms": solve_ms, "cir_numpy_ms": cir_ms,
                "valid_paths": valid_paths, "padded_paths": padded_paths,
                "possible_path_cap_hit": cap_risk, "channel_power_checksum": checksum}

    cold = update(0)
    for index in range(args.warmup):
        update(index+1)
    samples = [update(index+args.warmup+1) for index in range(args.iterations)]
    total = np.asarray([s["total_ms"] for s in samples])
    gpu_info = None
    if args.backend == "cuda":
        try:
            gpu_info = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,name,memory.total,driver_version",
                 "--format=csv,noheader"], capture_output=True, text=True,
                timeout=10, check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            gpu_info = "nvidia-smi query unavailable"
    result = {
        "scope": "Moving independent radios; Sionna propagation and one-epoch NumPy CIR only",
        "excludes": ["waveform synthesis", "RF filtering/ADC", "moving meshes/BVH update",
                     "AirSim physics/render/RPC", "worker transport", "file I/O"],
        "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "versions": {"python": platform.python_version(), "sionna_rt": rt.__version__,
                     "mitsuba": mi.__version__, "drjit": dr.__version__, "backend": mi.variant()},
        "host": {"platform": platform.platform(), "cpu_count": os.cpu_count(),
                 "cpu_model": next((line.split(":", 1)[1].strip() for line in
                       Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), "unknown"),
                 "cpu_quota": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
                 "memory_limit": Path("/sys/fs/cgroup/memory.max").read_text().strip(),
                 "peak_host_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                 "gpu_inventory": gpu_info,
                 "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")},
        "scene_objects": len(scene.objects), "scene_triangles": sum(
            len(obj.mi_mesh.faces_buffer())//3 for obj in scene.objects.values()),
        "setup_ms": setup_ms, "cold": cold,
        "p50_ms": float(np.percentile(total, 50)), "p95_ms": float(np.percentile(total, 95)),
        "p99_ms": float(np.percentile(total, 99)), "max_ms": float(total.max()),
        "budget_ms": 1000/args.update_hz,
        "deadline_misses": int(np.sum(total > 1000/args.update_hz)),
        "stage_p50_ms": {k: float(np.median([s[k] for s in samples])) for k in
                         ("pose_ms", "solve_ms", "cir_numpy_ms")},
        "valid_paths_min": min(s["valid_paths"] for s in samples),
        "valid_paths_max": max(s["valid_paths"] for s in samples),
        "samples": samples,
        "notes": ["Host RSS is not GPU VRAM", "Path cap and ray count require convergence studies",
                  "Batched scene add/remove overhead is included", "Cold includes JIT work"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k: v for k, v in result.items() if k != "samples"}, indent=2))


if __name__ == "__main__":
    main()
