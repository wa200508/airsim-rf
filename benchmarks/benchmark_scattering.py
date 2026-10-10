"""Antenna-aware first-order ground scattering with an explicit per-link budget."""
import argparse
import json
import os
from pathlib import Path
import resource
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--scene", choices=("ground", "terrain"), default="ground")
    parser.add_argument("--tx", type=int, default=100)
    parser.add_argument("--rx", type=int, default=1)
    parser.add_argument("--samples-per-link", type=int, default=1028)
    parser.add_argument("--uniform-fraction", type=float, default=.1)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--pulse-hz", type=float, default=200)
    parser.add_argument("--deployment-receivers", type=int, default=10,
                        help="Fleet receiver/GPU count; benchmark --rx remains the local solve size")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.tx, args.rx, args.iterations, args.samples_per_link, args.deployment_receivers) < 1 or args.samples_per_link < 2 or min(args.warmup, args.threads) < 0 or args.pulse_hz <= 0:
        parser.error("Counts/rate must be positive, samples >= 2, warmup/threads nonnegative")
    import numpy as np
    import drjit as dr
    if args.threads:
        dr.set_thread_count(args.threads)
    if args.backend == "cuda" and not dr.has_backend(dr.JitBackend.CUDA):
        parser.error("CUDA unavailable; no CPU fallback")
    import mitsuba as mi
    mi.set_variant("cuda_ad_mono_polarized" if args.backend == "cuda" else "llvm_ad_mono_polarized")
    import sionna.rt as rt
    from sionna.rt.constants import InteractionType
    from airsim_rf.scattering import FirstOrderScatteringPathSolver
    from airsim_rf.runtime_metrics import receiver_gpu_workload, conditional_gpu_ray_times
    from scattering_scenario import load_fixture, update_platforms
    from airsim_rf.terrain import demo_terrain, scene_provenance, validate_flight_envelope
    scene = load_fixture(args.scene, args.tx, args.rx, historical=True)
    elevations = demo_terrain(historical=True).heights_m if args.scene == 'terrain' else np.zeros((2, 2))
    scene_name = 'terrain_benchmark_v1' if args.scene == 'terrain' else args.scene
    scene_path = Path(__file__).resolve().parent/'scenes'/f'{scene_name}.xml'
    contract = scene_provenance(scene_path)
    if args.scene == 'terrain':
        devices = list(scene.transmitters.values())+list(scene.receivers.values())
        contract['flight_envelope'] = validate_flight_envelope(demo_terrain(historical=True),
            np.asarray([np.asarray(d.position).ravel() for d in devices]),
            np.asarray([np.asarray(d.velocity).ravel() for d in devices]),
            (args.warmup+args.iterations)/args.pulse_hz)
    solver = FirstOrderScatteringPathSolver(uniform_fraction=args.uniform_fraction)
    prepare_start = time.perf_counter()
    planes = solver.specular_plane_count(scene)
    geometry_prepare_ms = 1000*(time.perf_counter()-prepare_start)

    def run(index):
        start = time.perf_counter()
        epoch = index/args.pulse_hz
        update_platforms(scene, epoch)
        pose_ms = (time.perf_counter()-start)*1000
        paths = solver(scene, samples_per_src=args.samples_per_link,
                       max_num_paths_per_src=args.rx*(args.samples_per_link+1+planes), seed=42)
        dr.eval(paths.a, paths.tau, paths.doppler)
        dr.sync_thread()
        solved = time.perf_counter()
        a, tau = paths.cir(num_time_steps=1, normalize_delays=False, out_type="numpy")
        doppler = paths.doppler.numpy()
        finish = time.perf_counter()
        if not np.isfinite(a).all() or not np.isfinite(doppler).all():
            raise RuntimeError("Nonfinite channel")
        # Classification and diagnostic reductions are excluded from the solve
        # timer, as the RF worker only needs the compact coefficients/delays/fd.
        diffuse = paths.interactions.numpy()[0] == int(InteractionType.DIFFUSE)
        per_link = diffuse.sum(axis=-1)
        power = np.abs(a[:, 0, :, 0, :, 0])**2
        return {"epoch_s": epoch, "total_ms": (finish-start)*1000, "pose_ms": pose_ms,
                "solve_ms": (solved-start)*1000-pose_ms, "cir_numpy_ms": (finish-solved)*1000,
                "valid_paths": int((tau >= 0).sum()), "diffuse_paths": int(diffuse.sum()),
                "diffuse_per_link_min": int(per_link.min()), "diffuse_per_link_median": float(np.median(per_link)),
                "diffuse_per_link_max": int(per_link.max()),
                "sum_diffuse_path_power": float(power[diffuse].sum()),
                "sampling": solver.sampling, "stage_timings": solver.stage_timings}

    cold = run(0)
    for i in range(args.warmup):
        run(i+1)
    samples = [run(i+args.warmup+1) for i in range(args.iterations)]
    times = np.asarray([sample['total_ms'] for sample in samples])
    stage_summary = {name: {"p50_ms": float(np.median([s['stage_timings'][name] for s in samples])),
                            "p95_ms": float(np.percentile([s['stage_timings'][name] for s in samples], 95))}
                     for name in samples[0]['stage_timings']}
    workload = receiver_gpu_workload(transmitters=args.tx, receivers=args.deployment_receivers,
                attempts_per_link=args.samples_per_link, specular_planes=planes, pulse_hz=args.pulse_hz)
    # A multi-RX batch cannot establish one-worker host cost by dividing by RX.
    host_ms = stage_summary['host_numpy_sampling_ms']['p50_ms'] if args.rx == 1 else None
    result = {"scope": f"Synthetic {args.scene}; independent moving TX/RX plus first-order diffuse and specular propagation",
              "scene_file": str(scene_path.relative_to(Path(__file__).resolve().parents[1])), "scene_provenance": contract, "specular_planes": planes,
              "geometry_prepare_ms": geometry_prepare_ms,
              "model": {"carrier_hz": 24.125e9, "depth": 1, "refraction": False, "diffraction": False,
                        "surface_geometry": "21x21 DEM, 800 planar triangles" if args.scene == 'terrain' else "Flat mesh, two triangles",
                        "elevation_range_m": [float(elevations.min()), float(elevations.max())],
                        "ground_extent_m": [-100, 100], "permittivity": 5, "conductivity_s_per_m": .01,
                        "thickness_m": .5, "scattering_coefficient": .3, "scattering_pattern": "Sionna default Lambertian",
                        "tx_pattern": "tr38901", "rx_pattern": "tr38901", "polarization": "V",
                        "calibrated_ground_roughness": False, "independent_random_scatterer_phases": False},
              "temporal_model": "Common random numbers per pulse; sampled hit points are not persistent world scatterers",
              "sampling": {"attempts_per_link": args.samples_per_link, "pattern_grid": [64, 128],
                           "strategy": "Half TX-pattern proposals, half RX-pattern proposals; mixture area-PDF correction",
                           "uniform_fraction": args.uniform_fraction, "proposal_generation": "NumPy host draws; Mitsuba traces and Sionna fields on selected backend"},
              "excludes": ["IQ synthesis", "AirSim", "moving mesh/BVH updates", "transport", "diagnostic classification"],
              "versions": {"sionna_rt": rt.__version__, "mitsuba": mi.__version__, "drjit": dr.__version__, "backend": mi.variant()},
              "arguments": {k: str(v) if isinstance(v, Path) else v for k,v in vars(args).items()},
              "host": {"cpu_count": os.cpu_count(), "cpu_quota": Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
                       "memory_limit": Path('/sys/fs/cgroup/memory.max').read_text().strip(),
                       "drjit_threads": dr.thread_count(), "peak_host_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024},
              "stage_timings": stage_summary,
              "gpu_deployment": {"workload": workload,
                    "gpu_channel_runtime_measured": args.backend == "cuda",
                    "gpu_iq_runtime_measured": False,
                    "cpu_to_gpu_speedup_applied": False,
                    "measured_host_sampling_ms_per_receiver_worker": host_ms,
                    "conditional_ray_stage_sensitivity": conditional_gpu_ray_times(workload, host_sampling_ms=host_ms),
                    "conditional_rates_source": "Hypothetical effective whole-scene query throughput, not vendor RT-core specifications",
                    "gpu_deadline_status": "unmeasured" if args.backend == "cpu" else "see local channel-only measured timings; IQ/AirSim/transport excluded",
                    "remaining_solve_cost": "mixed host/device; no pure GPU residual inferred",
                    "device_memory": "unmeasured; host RSS does not estimate VRAM"},
              "cold": cold, "p50_ms": float(np.median(times)), "p95_ms": float(np.percentile(times, 95)),
              "max_ms": float(times.max()), "pulse_budget_ms": 1000/args.pulse_hz,
              "deadline_misses": int((times > 1000/args.pulse_hz).sum()), "samples": samples,
              "notes": ["Geometry plane-cache preparation is timed separately from cold/epoch channel solves",
                        "Attempts are not retained paths: misses, occlusion and zero response contribute zero",
                        "Incoherent sum of path powers is a normalization diagnostic, not coherent IQ power",
                        "Sample count does not establish clutter fidelity or convergence",
                        "Host RSS is not VRAM; no purchase minimum follows from CPU timing"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'samples'}, indent=2))


if __name__ == '__main__':
    main()
