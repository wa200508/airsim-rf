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
    parser.add_argument("--tx", type=int, default=100)
    parser.add_argument("--rx", type=int, default=1)
    parser.add_argument("--samples-per-link", type=int, default=1028)
    parser.add_argument("--uniform-fraction", type=float, default=.1)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--pulse-hz", type=float, default=200)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.tx, args.rx, args.iterations, args.samples_per_link) < 1 or args.samples_per_link < 2 or min(args.warmup, args.threads) < 0 or args.pulse_hz <= 0:
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
    scene = rt.load_scene(str(Path(__file__).resolve().parent/"scenes/ground.xml"))
    scene.frequency = 24.125e9
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="tr38901", polarization="V")
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="tr38901", polarization="V")
    for i in range(args.tx):
        scene.add(rt.Transmitter(f"tx_{i}", position=[0, -25+50*i/max(args.tx-1, 1), 10],
                  orientation=[0, np.pi/2, 0], velocity=[1, 0, 0]))
    for i in range(args.rx):
        scene.add(rt.Receiver(f"rx_{i}", position=[10, -5+i, 15],
                  orientation=[0, np.pi/2, 0], velocity=[0, .5, 0]))
    solver = FirstOrderScatteringPathSolver(uniform_fraction=args.uniform_fraction)

    def run(index):
        start = time.perf_counter()
        epoch = index/args.pulse_hz
        for i, tx in enumerate(scene.transmitters.values()):
            tx.position = [epoch, -25+50*i/max(args.tx-1, 1), 10]
            tx.orientation = [0, float(np.pi/2+.05*np.sin(epoch+i)), 0]
        for i, rx in enumerate(scene.receivers.values()):
            rx.position = [10, -5+i+.5*epoch, 15]
            rx.orientation = [0, float(np.pi/2+.05*np.sin(epoch)), 0]
        pose_ms = (time.perf_counter()-start)*1000
        paths = solver(scene, samples_per_src=args.samples_per_link,
                       max_num_paths_per_src=args.rx*(args.samples_per_link+2), seed=42)
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
                "sampling": solver.sampling}

    cold = run(0)
    for i in range(args.warmup):
        run(i+1)
    samples = [run(i+args.warmup+1) for i in range(args.iterations)]
    times = np.asarray([sample['total_ms'] for sample in samples])
    result = {"scope": "Synthetic finite ground; independent moving TX/RX plus first-order diffuse and specular propagation",
              "model": {"carrier_hz": 24.125e9, "depth": 1, "refraction": False, "diffraction": False,
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
              "cold": cold, "p50_ms": float(np.median(times)), "p95_ms": float(np.percentile(times, 95)),
              "max_ms": float(times.max()), "pulse_budget_ms": 1000/args.pulse_hz,
              "deadline_misses": int((times > 1000/args.pulse_hz).sum()), "samples": samples,
              "notes": ["Attempts are not retained paths: misses, occlusion and zero response contribute zero",
                        "Incoherent sum of path powers is a normalization diagnostic, not coherent IQ power",
                        "Sample count does not establish clutter fidelity or convergence",
                        "Host RSS is not VRAM; no purchase minimum follows from CPU timing"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'samples'}, indent=2))


if __name__ == '__main__':
    main()
