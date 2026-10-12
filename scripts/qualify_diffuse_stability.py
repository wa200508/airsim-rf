"""Audit diffuse sampling under local motion from recorded real-flight kinematics.

This is GPU propagation replay, not a fresh live capture or throughput benchmark.
A fixed angular proposal is not a persistent physical surface-scatterer model.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree


def match_proposals(before, after, endpoints_before, endpoints_after):
    """Match antenna-relative launch directions; exported path order may change."""
    distances=[];indices=[]
    for old,new in zip(endpoints_before,endpoints_after):
        a=before-old;b=after-new
        a=a/np.linalg.norm(a,axis=1)[:,None];b=b/np.linalg.norm(b,axis=1)[:,None]
        distance,index=cKDTree(b).query(a)
        distances.append(distance);indices.append(index)
    side=np.argmin(distances,axis=0);rows=np.arange(len(before))
    chosen=np.asarray(indices)[side,rows];distance=np.asarray(distances)[side,rows]
    keep=distance<1e-5
    counts=np.bincount(chosen[keep],minlength=len(after))
    keep &= counts[chosen]==1
    return rows[keep],chosen[keep]


def run(args):
    import mitsuba as mi
    mi.set_variant('cuda_ad_mono_polarized')
    if args.pascal_compat:
        from airsim_rf.p100_compat import enable_pascal_compat
        enable_pascal_compat()
    import sionna.rt as rt
    from sionna.rt.constants import InteractionType
    from airsim_rf.bridge import mount_kinematics
    from airsim_rf.scattering import FirstOrderScatteringPathSolver
    from airsim_rf.terrain import scene_provenance
    root=Path(__file__).resolve().parents[1]
    trajectory=json.loads(args.trajectory.read_text())
    states=[mount_kinematics(r['kinematics']) for r in trajectory[:2]]
    scene=rt.load_scene(str(root/'benchmarks/scenes/ground.xml'));scene.frequency=915e6
    scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V')
    scene.rx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V')
    devices=[rt.Transmitter('tx',position=states[0][0]),rt.Receiver('rx',position=states[1][0])]
    for device in devices:scene.add(device)
    def pose(dt):
        for device,(p,v,o) in zip(devices,states):
            device.position=(p+v*dt).tolist();device.velocity=v.tolist();device.orientation=o.tolist()
    def solve(solver,n,seed):
        paths=solver(scene,samples_per_src=n,max_num_paths_per_src=n+2,seed=seed,
            los=False,specular_reflection=False)
        a,tau=paths.cir(normalize_delays=False,out_type='numpy')
        return (a[0,0,0,0,:,0],tau[0,0],paths.doppler.numpy()[0,0],
            paths.vertices.numpy()[0,0,0],paths.interactions.numpy()[0,0,0]==int(InteractionType.DIFFUSE))
    rows=[]
    for count in (128,512,2048):
        for seed in (42,43,44):
            solver=FirstOrderScatteringPathSolver(surface_sampling=args.surface_sampling);pose(0)
            a,tau,fd,vertices,diffuse=solve(solver,count,seed)
            repeated=solve(solver,count,seed)
            fresh=solve(FirstOrderScatteringPathSolver(cache_sampling=False,surface_sampling=args.surface_sampling),count,seed)
            base_valid=(tau>=0)&diffuse
            def equivalent(other):
                order=np.lexsort(vertices.T);other_order=np.lexsort(other[3].T)
                return all(np.allclose(x[order],y[other_order],rtol=1e-6,atol=1e-12)
                    for x,y in zip((a,tau,fd),other[:3]))
            reproducible=equivalent(repeated);cache_equal=equivalent(fresh)
            for dt in (.0001,.001,.012):
                pose(dt);b,delay,newfd,points,newdiffuse=solve(solver,count,seed)
                old_indices=np.flatnonzero(base_valid&(abs(a)>0))
                new_indices=np.flatnonzero((delay>=0)&newdiffuse&(abs(b)>0))
                if args.surface_sampling:
                    distance,right=cKDTree(points[new_indices]).query(vertices[old_indices])
                    left=np.flatnonzero(distance<1e-5);right=right[left]
                else:
                    left,right=match_proposals(vertices[old_indices],points[new_indices],
                        [s[0] for s in states],[s[0]+s[1]*dt for s in states])
                left=old_indices[left];right=new_indices[right]
                displacement=np.linalg.norm(points[right]-vertices[left],axis=1)
                residual=np.angle(b[right]/a[left]*np.exp(-2j*np.pi*fd[left]*dt))
                held=np.sum(a[base_valid]*np.exp(2j*np.pi*fd[base_valid]*dt))
                updated=np.sum(b[(delay>=0)&newdiffuse])
                rows.append({'samples_per_link':count,'seed':seed,'elapsed_signal_s':dt,
                    'stationary_repeat_equivalent':bool(reproducible),'sampling_cache_equivalent':bool(cache_equal),
                    'common_valid_slots':len(left),'valid_slots_before':int(base_valid.sum()),
                    'valid_slots_after':int(((delay>=0)&newdiffuse).sum()),
                    'median_vertex_displacement_m':float(np.median(displacement)),
                    'p95_vertex_displacement_m':float(np.quantile(displacement,.95)),
                    'median_absolute_phase_residual_rad':float(np.median(abs(residual))),
                    'p95_absolute_phase_residual_rad':float(np.quantile(abs(residual),.95)),
                    'complex_sum_change_over_incoherent_rms':float(abs(updated-held)/np.sqrt(np.sum(abs(a[base_valid])**2)))})
    checks={'stationary_repeat_equivalent':all(r['stationary_repeat_equivalent'] for r in rows),
        'cache_preserves_result':all(r['sampling_cache_equivalent'] for r in rows),
        'all_comparisons_have_diffuse_paths':all(r['common_valid_slots']>0 for r in rows)}
    report={'status':'passed' if all(checks.values()) else 'failed','checks':checks,
        'scope':'diffuse angular-sampling repeatability and local-motion diagnostics, not coherent diffuse qualification',
        'persistent_surface_scatterers_qualified':False,'surface_sampling':args.surface_sampling,'backend':mi.variant(),'sionna_rt':rt.__version__,
        'trajectory_sha256':sha256(args.trajectory.read_bytes()).hexdigest(),
        'rf_scene':scene_provenance(root/'benchmarks/scenes/ground.xml'),
        'motion':'constant measured endpoint velocities, fixed starting orientations; actual sampled surface positions may slide',
        'states_rf':[{'position_m':p.tolist(),'velocity_m_s':v.tolist(),'orientation_rad':o.tolist()} for p,v,o in states],
        'carrier_hz':915e6,'rows':rows}
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'stability.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trajectory',type=Path,default=Path('results/reviews/moving-receiver-20261011/direct-12/trajectory.json'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--pascal-compat',action='store_true')
    parser.add_argument('--surface-sampling',action='store_true')
    run(parser.parse_args())
