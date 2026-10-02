"""Measure the materialized Sionna -> IF -> ADC path against a simulation tick."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--targets", type=int, default=2)
    parser.add_argument("--chirps", type=int, default=1)
    parser.add_argument("--update-hz", type=float, default=120)
    parser.add_argument("--rf-scene")
    parser.add_argument("--backend", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--fft", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("benchmark_rf.json"))
    args = parser.parse_args()
    if min(args.iterations, args.targets, args.chirps) < 1 or args.warmup < 0 or args.update_hz <= 0:
        parser.error("counts/rate must be positive and warmup nonnegative")
    import_start = time.perf_counter()
    import numpy as np
    import mitsuba as mi
    if args.backend != "auto":
        mi.set_variant("llvm_ad_mono_polarized" if args.backend == "cpu" else "cuda_ad_mono_polarized")
    import sionna.rt
    from airsim_rf.fmcw import FMCWRadar, range_fft
    from airsim_rf.radar import PointTarget
    import_ms = (time.perf_counter()-import_start)*1000
    setup_start = time.perf_counter()
    scene_file = args.rf_scene
    if scene_file and scene_file.startswith("builtin:"):
        scene_file = getattr(sionna.rt.scene, scene_file.split(":", 1)[1])
    radar = FMCWRadar(rf_scene=scene_file)
    setup_ms = (time.perf_counter()-setup_start)*1000
    targets = [PointTarget(f"target_{i}", (10+4*i/max(args.targets-1, 1), 0, 2), 0.1)
               for i in range(args.targets)]

    def update(index):
        timestamp = index/args.update_hz
        position = [0.3*timestamp, 0, 2]
        if args.chirps == 1:
            captures = [radar.capture(targets, position_m=position, velocity_m_s=[0.3, 0, 0],
                                      sim_time_ns=round(timestamp*1e9))]
        else:
            captures = radar.capture_frame(targets, position_m=position, velocity_m_s=[0.3, 0, 0],
                                           sim_time_ns=round(timestamp*1e9), num_chirps=args.chirps)
        # capture has converted paths to NumPy and materialized IF/ADC arrays.
        if args.fft:
            for capture in captures:
                range_fft(capture.adc_iq_volts, radar.profile)
        return captures[-1].adc_codes.size

    cold_start = time.perf_counter()
    update(0)
    cold_ms = (time.perf_counter()-cold_start)*1000
    for i in range(args.warmup):
        update(i+1)
    elapsed_ms = []
    for i in range(args.iterations):
        start = time.perf_counter()
        update(i+args.warmup+1)
        elapsed_ms.append((time.perf_counter()-start)*1000)
    budget_ms = 1000/args.update_hz
    result = {
        "scope": "Sionna direct paths + FMCW mixing + IF/noise + ADC; excludes AirSim RPC, physics, rendering, file I/O",
        "scene": args.rf_scene or "empty free-space scene",
        "scene_objects": len(radar.scene.objects),
        "backend": mi.variant(), "python": platform.python_version(),
        "sionna_rt": sionna.rt.__version__, "platform": platform.platform(),
        "cpu_count": os.cpu_count(), "cpu_model": next((line.split(':',1)[1].strip() for line in
             Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')), "unknown") if Path('/proc/cpuinfo').exists() else platform.processor(),
        "cgroup_cpu_max": Path('/sys/fs/cgroup/cpu.max').read_text().strip() if Path('/sys/fs/cgroup/cpu.max').exists() else None,
        "arguments": {key: str(value) if isinstance(value, Path) else value for key,value in vars(args).items()},
        "budget_ms": budget_ms, "import_ms": import_ms, "setup_ms": setup_ms, "cold_update_ms": cold_ms,
        "mean_ms": statistics.mean(elapsed_ms),
        "p50_ms": float(np.percentile(elapsed_ms, 50)), "p95_ms": float(np.percentile(elapsed_ms, 95)),
        "p99_ms": float(np.percentile(elapsed_ms, 99)), "max_ms": max(elapsed_ms),
        "deadline_misses": sum(value > budget_ms for value in elapsed_ms),
        "samples_ms": elapsed_ms,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ('samples_ms','arguments','platform')}, indent=2))


if __name__ == "__main__":
    main()
