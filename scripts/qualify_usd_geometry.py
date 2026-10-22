"""Shared USD scene against Unreal CPU LiDAR and Sionna CUDA intersections.

Owns a dedicated Blocks world's scene and stepping. Does not manage the server.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import time

import numpy as np
from scipy.spatial.transform import Rotation

from airsim_rf.geometry import export_sionna_geometry, file_digest
from airsim_rf.geometry_sync import AirSimGeometryBinding, placement_plan, spawn_placements, nearest_intersections
from airsim_rf.usd_geometry import import_usd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--pascal-compat', action='store_true')
    parser.add_argument('--client-mesh', action='store_true', help='Qualify generated GLB with an asymmetric sloping roof')
    parser.add_argument('--screen', action='store_true', help='Include the shared moving-link screen (requires --client-mesh)')
    parser.add_argument('--turn-screen', action='store_true', help='Probe the combined turning/reflection obstruction asset')
    args = parser.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    if (args.screen or args.turn_screen) and not args.client_mesh:
        parser.error('--screen requires --client-mesh')
    asset = 'shared-mesh-turn-screen' if args.turn_screen else 'shared-mesh-screen' if args.screen else 'shared-mesh-world' if args.client_mesh else 'shared-world'
    profile = json.loads((repo/f'examples/geometry/{asset}.rf.json').read_text())
    # Separate controlled geometry from the packaged Blocks buildings below.
    profile['stage_meters_to_ned_m'][2][3] = -100
    (root/'profile.json').write_text(json.dumps(profile, indent=2)+'\n')
    geometry, provenance, bindings = import_usd(repo/f'examples/geometry/{asset}.usda', root/'profile.json')
    export_sionna_geometry(geometry, root/'bundle', provenance=provenance, bindings=bindings)
    plan = placement_plan(geometry, bindings)
    guard = AirSimGeometryBinding(geometry, bindings)
    probes = [('BuildingNorth', [0, 0, -101], [0, 0, 0]),
              ('BuildingEast', [5, -5, -101], [0, 0, 90]),
              ('GroundTop', [0, 0, -105], [0, -90, 0])]
    wall = next(o for o in plan['objects'] if o['id'] == 'Wall')
    center = np.array([wall['pose']['translation'][k] for k in ('x','y','z')])
    matrix = np.asarray(next(o for o in geometry['objects'] if o['id']=='Wall')['local_to_ned_m'])
    direction = matrix[:3, 0]/np.linalg.norm(matrix[:3, 0])
    probes.append(('RotatedWall', (center-4*direction).tolist(), [0, 0, float(np.degrees(np.arctan2(direction[1],direction[0])))]))
    if args.client_mesh:
        probes.append(('SlopingRoof', [5, 0, -106], [0, -90, 0]))
    if args.screen:
        probes.append(('ScreenFront', [-4, .7, -120], [0, 0, 0]))
    if args.turn_screen:
        probes.append(('ScreenFront', [-4, 2.2, -120], [0, 0, 0]))
    sim = root/'sim'; sim.mkdir()
    robot = {'physics-type':'non-physics','links':[{'name':'Frame','collision':{'enabled':False}}],
        'sensors':[{'id':'lidar','type':'lidar','lidar-type':'generic_cylindrical','enabled':True,
        'parent-link':'Frame','number-of-channels':1,'range':12,'points-per-second':10000,
        'horizontal-rotation-frequency':10,'horizontal-fov-start-deg':-3,'horizontal-fov-end-deg':3,
        'vertical-fov-upper-deg':0,'vertical-fov-lower-deg':0,'disable-self-hits':True,
        'draw-debug-points':False,'report-point-cloud':True,'report-no-return-points':False,
        'origin':{'xyz':'0 0 0','rpy-deg':'0 0 0'}}]}
    (sim/'robot.jsonc').write_text(json.dumps(robot))
    config = {'id':'SharedUsdQualification','scene-type':'UnrealNative',
        'actors':[{'type':'robot','name':name,'origin':{'xyz':' '.join(map(str,pos)),
                    'rpy-deg':' '.join(map(str,rpy))},'robot-config':'robot.jsonc'} for name,pos,rpy in probes],
        'clock':{'type':'steppable','step-ns':3_000_000,'real-time-update-rate':3_000_000,'pause-on-start':True},
        'home-geo-point':{'latitude':47.641468,'longitude':-122.140165,'altitude':122.}}
    (sim/'scene.jsonc').write_text(json.dumps(config))
    from projectairsim import ProjectAirSimClient, World, Drone
    client = ProjectAirSimClient(address='127.0.0.1'); client.connect()
    messages = {name:[] for name,_,_ in probes}
    observations = {}
    try:
        world = World(client, 'scene.jsonc', sim_config_path=str(sim.resolve())); world.pause()
        spawn_placements(world, plan)
        initial = guard.require_static_match(world, int(world.get_sim_time()))
        drones = {name:Drone(client,world,name) for name,_,_ in probes}
        for name, drone in drones.items():
            client.subscribe(drone.sensors['lidar']['lidar'], lambda _,msg,n=name:messages[n].append(msg))
        time.sleep(.3)
        for _ in range(15):
            world.continue_until_sim_time(int(world.get_sim_time())+30_000_000, wait_until_complete=True)
            time.sleep(.05)
        final = guard.require_static_match(world, int(world.get_sim_time()))
        for name, drone in drones.items():
            observations[name] = {'kinematics':drone.get_ground_truth_kinematics(), 'lidar':messages[name]}
        changed = deepcopy(wall['pose']); changed['translation']['y'] += 1
        world.set_object_pose(wall['object_name'], changed, True)
        rejected = False
        try:
            guard.require_static_match(world, int(world.get_sim_time()))
        except RuntimeError:
            rejected = True
        _, revised = guard.snapshot(world)
        revised['revision'] = geometry['revision']+'-wall-moved'
        export_sionna_geometry(revised,root/'revised-bundle',provenance=provenance,bindings=bindings)
        revised_guard=AirSimGeometryBinding(revised,bindings).require_static_match(world,int(world.get_sim_time()))
        world.set_object_pose(wall['object_name'], wall['pose'], True)
        guard.require_static_match(world, int(world.get_sim_time()))
    finally:
        client.disconnect()
    (root/'unreal.json').write_text(json.dumps(observations, indent=2)+'\n')
    import mitsuba as mi
    mi.set_variant('cuda_ad_mono_polarized')
    if args.pascal_compat:
        from airsim_rf.p100_compat import enable_pascal_compat
        enable_pascal_compat()
    import sionna.rt as rt
    scene = rt.load_scene(str(root/'bundle/scene.xml'), merge_shapes=False)
    comparisons = {}
    for name, observation in observations.items():
        chunks = [np.asarray(m['point_cloud']).reshape(-1,3) for m in observation['lidar'] if m['point_cloud']]
        if not chunks:
            raise ValueError(f'{name}: no independent LiDAR returns')
        points = np.concatenate(chunks)
        pose = observation['kinematics']['pose']
        q = pose['orientation']; rotation = Rotation.from_quat([q[k] for k in ('x','y','z','w')]).as_matrix()
        origin = np.array([pose['position'][k] for k in ('x','y','z')])
        vectors = points @ rotation.T
        lengths = np.linalg.norm(vectors,axis=1)
        directions = vectors/lengths[:,None]
        cpu = nearest_intersections(geometry, np.tile(origin,(len(points),1)), directions, maximum_distance_m=12)
        if any(hit is None for hit in cpu):
            raise ValueError(f'{name}: LiDAR ray missing from shared CPU mesh')
        cpu_error = float(np.max(abs(np.array([hit['distance_m'] for hit in cpu])-lengths)))
        rf_origin = origin*[1,-1,-1]; rf_directions = directions*[1,-1,-1]
        hit = scene.mi_scene.ray_intersect(mi.Ray3f(mi.Point3f(*map(float,rf_origin)),mi.Vector3f(rf_directions.T)))
        expected = (origin+vectors)*[1,-1,-1]
        error = float(np.max(np.linalg.norm(hit.p.numpy().T-expected,axis=1)))
        comparisons[name] = {'rays':len(points),'cpu_maximum_error_m':cpu_error,'gpu_maximum_error_m':error,
                             'cpu_object_ids':sorted(set(h['object_id'] for h in cpu))}
    from airsim_rf.single_bounce import SingleBouncePathSolver
    scene.tx_array = rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V')
    scene.rx_array = scene.tx_array
    scene.add(rt.Transmitter('tx',position=[0,-3,103])); scene.add(rt.Receiver('rx',position=[12,-3,103]))
    paths = SingleBouncePathSolver()(scene,max_depth=1)
    gains, delays = paths.cir(normalize_delays=False,out_type='numpy')
    path_count = int(np.sum(delays>=0))
    observed_delays = np.sort(np.asarray(delays)[np.asarray(delays)>=0])
    expected_delays = np.array([12., np.sqrt(12.**2+6.**2)])/299792458.
    delay_error = float(np.max(abs(observed_delays-expected_delays))) if path_count==2 else None
    scene.transmitters['tx'].position=[0,0,101]
    scene.receivers['rx'].position=[10,0,101]
    blocked=SingleBouncePathSolver()(scene,max_depth=0)
    _,blocked_delays=blocked.cir(normalize_delays=False,out_type='numpy')
    blocked_count=int(np.sum(blocked_delays>=0))
    # A revision is a new export and a fresh scene/solver, never a hot patch of
    # the receiver's cached geometry. Independently ray-check the moved wall.
    revised_scene=rt.load_scene(str(root/'revised-bundle/scene.xml'),merge_shapes=False)
    ray_origin=center-4*direction
    revised_cpu=nearest_intersections(revised,[ray_origin],[direction],maximum_distance_m=12)[0]
    original_cpu=nearest_intersections(geometry,[ray_origin],[direction],maximum_distance_m=12)[0]
    revised_hit=revised_scene.mi_scene.ray_intersect(mi.Ray3f(
        mi.Point3f(*map(float,ray_origin*[1,-1,-1])),mi.Vector3f(*map(float,direction*[1,-1,-1]))))
    revised_distance=float(revised_hit.t[0])
    revision_error=abs(revised_distance-revised_cpu['distance_m'])
    stale_difference=abs(original_cpu['distance_m']-revised_cpu['distance_m'])
    cache_solver=SingleBouncePathSolver()
    cache_solver.specular_plane_count(scene)
    cache_solver.specular_plane_count(revised_scene)
    revised_solver=SingleBouncePathSolver()
    revised_solver.specular_plane_count(revised_scene)
    checks = {'stable_object_ids':set(scene.objects)=={'obj_'+obj['id'] for obj in geometry['objects']},
              'all_lidar_comparisons_within_1mm':all(np.isfinite(v['gpu_maximum_error_m']) and v['gpu_maximum_error_m']<.001
                  and v['cpu_maximum_error_m']<.001 for v in comparisons.values()),
              'moved_static_object_rejected':rejected,
              'direct_and_specular_paths_present':path_count==2,
              'analytic_direct_and_ground_delay':delay_error is not None and delay_error<1e-12,
              'building_blocks_direct_path':blocked_count==0,
              'finite_path_gains':bool(np.isfinite(gains).all()),
              'revised_binding_accepts_new_snapshot':revised_guard['geometry_sha256']!=initial['geometry_sha256'],
              'fresh_scene_matches_revised_triangles':revision_error<.001,
              'old_scene_is_stale_after_wall_move':stale_difference>.1,
              'changed_scene_rebuilds_plane_cache':cache_solver.mesh_rebuilds==2,
              'fresh_revision_solver_builds_own_cache':revised_solver.mesh_rebuilds==1}
    report = {'status':'passed' if all(checks.values()) else 'failed','checks':checks,'probes':comparisons,
              'path_count':path_count,'blocked_direct_path_count':blocked_count,
              'path_delays_s':observed_delays.tolist(),'expected_path_delays_s':expected_delays.tolist(),
              'maximum_delay_error_s':delay_error,'initial_guard':initial,'final_guard':final,
              'revised_guard':revised_guard,'revised_ray_error_m':revision_error,'stale_ray_difference_m':stale_difference,
              'revision_cache_rebuilds':cache_solver.mesh_rebuilds,'fresh_solver_cache_rebuilds':revised_solver.mesh_rebuilds,
              'sionna_rt':rt.__version__,'mitsuba':mi.__version__,
              'script_sha256':file_digest(__file__),
              'adapter':'blocks-client-glb-v1' if args.client_mesh else 'packaged-cube',
              'scope':'Static shared USD geometry, independent Unreal CPU LiDAR, CPU triangles and GPU intersections; no existing-world extraction or moving obstacles'}
    (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    if report['status']!='passed':
        raise SystemExit(1)


if __name__=='__main__':
    main()
