"""Check recorded beacon/receiver line segments against the actual RF mesh."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('cpu', 'cuda'), default='cuda')
    parser.add_argument('--data-dir', type=Path, default=Path('docs/figures'))
    args = parser.parse_args()
    import drjit as dr
    import mitsuba as mi
    dr.set_thread_count(2)
    if args.backend == 'cuda' and not dr.has_backend(dr.JitBackend.CUDA):
        parser.error('CUDA unavailable; no CPU fallback')
    mi.set_variant('cuda_ad_mono_polarized' if args.backend == 'cuda' else 'llvm_ad_mono_polarized')
    import sionna.rt as rt
    root = Path(__file__).resolve().parents[1]
    mesh = root/'benchmarks/scenes/terrain.ply'
    report_path = args.data_dir/'pluto_esm_report.json'
    report = json.loads(report_path.read_text())
    scene = rt.load_scene(str(root/'benchmarks/scenes/terrain.xml'))
    rows = []
    for record in report['records']:
        poses = np.asarray(record['positions_m'])
        links = []
        for tx in range(2):
            for rx in range(2, 4):
                delta = poses[rx]-poses[tx]
                length = np.linalg.norm(delta)
                ray = mi.Ray3f(mi.Point3f(*map(float, poses[tx])),
                              mi.Vector3f(*map(float, delta/length)))
                ray.maxt = float(length-1e-4)
                links.append({'tx': report['devices'][tx], 'rx': report['devices'][rx],
                              'terrain_blocks_direct': bool(scene.mi_scene.ray_test(ray)[0])})
        rows.append({'epoch_s': record['epoch_s'], 'links': links})
    result = {'scope': 'Segment visibility against actual mesh; not received power or multipath strength',
              'backend': mi.variant(), 'mesh_sha256': sha256(mesh.read_bytes()).hexdigest(),
              'report_sha256': sha256(report_path.read_bytes()).hexdigest(), 'records': rows}
    (args.data_dir/'sensing_visibility.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(rows[-1], indent=2))


if __name__ == '__main__':
    main()
