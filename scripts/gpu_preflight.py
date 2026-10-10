"""Real terrain CUDA/OptiX smoke solve; never substitutes CPU for CUDA."""
import argparse
import json
from pathlib import Path
import traceback


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend', choices=('cuda', 'cpu'), default='cuda')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = {'backend_requested': args.backend, 'status': 'blocked'}
    try:
        import numpy as np
        import drjit as dr
        import mitsuba as mi
        dr.set_thread_count(2)
        result['cuda_available'] = dr.has_backend(dr.JitBackend.CUDA)
        if args.backend == 'cuda' and not result['cuda_available']:
            raise RuntimeError('Dr.Jit CUDA backend unavailable; no CPU fallback')
        mi.set_variant('cuda_ad_mono_polarized' if args.backend == 'cuda' else 'llvm_ad_mono_polarized')
        import sionna.rt as rt
        from airsim_rf.scattering import FirstOrderScatteringPathSolver
        from airsim_rf.profiling import summarize_kernel_history
        root = Path(__file__).resolve().parents[1]
        scene = rt.load_scene(str(root/'benchmarks/scenes/terrain_benchmark_v1.xml'))
        scene.frequency = 915e6
        scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='hw_dipole', polarization='V')
        scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='hw_dipole', polarization='V')
        scene.add(rt.Transmitter('tx', position=[-60,-30,12]))
        scene.add(rt.Receiver('rx', position=[-30,-10,14]))
        solver = FirstOrderScatteringPathSolver()
        planes = solver.specular_plane_count(scene)
        dr.sync_thread()
        dr.kernel_history_clear()
        with dr.scoped_set_flag(dr.JitFlag.KernelHistory, True):
            paths = solver(scene, samples_per_src=32, max_num_paths_per_src=planes+33, seed=42)
            a, tau = paths.cir(num_time_steps=1, normalize_delays=False, out_type='numpy')
            doppler = paths.doppler.numpy()
            dr.sync_thread()
        history = summarize_kernel_history(dr.kernel_history())
        if not np.isfinite(a).all() or not np.isfinite(doppler).all() or not (tau>=0).any():
            raise RuntimeError('Smoke solve returned nonfinite values or no retained paths')
        if args.backend == 'cuda' and (not history['cuda_operation_count'] or not history['optix_kernel_count']):
            raise RuntimeError('Terrain solve did not record both CUDA and OptiX execution')
        from airsim_rf.terrain import scene_provenance
        result.update(scene_provenance=scene_provenance(root/'benchmarks/scenes/terrain_benchmark_v1.xml'), status='ok', versions={'sionna_rt': rt.__version__, 'mitsuba': mi.__version__,
            'drjit': dr.__version__, 'backend': mi.variant()}, specular_planes=planes,
            retained_paths=int((tau>=0).sum()), profile=history)
    except Exception as exc:
        result.update(error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('profile','traceback')},indent=2))
    return 0 if result['status']=='ok' else 20


if __name__=='__main__':
    raise SystemExit(main())
