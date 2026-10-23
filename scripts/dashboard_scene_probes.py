"""Independent Unreal CPU LiDAR probes for the dashboard's shared DEM."""
import json
import numpy as np
from scipy.spatial.transform import Rotation

from airsim_rf.geometry import read_bundle
from airsim_rf.geometry_sync import nearest_intersections,AirSimGeometryBinding,spawn_placements
from airsim_rf.dashboard_geometry import isolate_blocks_scene,require_rf_mesh_match
from airsim_rf.dashboard_view import TERRAIN_BASE_COLOR_RGBA,TERRAIN_EMISSIVE_RGB


def add_probes(output):
    document,_,_=read_bundle(output/'bundle')
    arrays=json.loads((output/'arrays.json').read_text());sites=arrays['sites'];cases={}
    for angle in np.deg2rad(np.arange(0,360,15)):
        tx=np.array([250*np.cos(angle),250*np.sin(angle),200])*[1,-1,-1]
        rx=np.asarray(sites[0]['center_rf_m'])*[1,-1,-1]
        hit=nearest_intersections(document,[rx],[tx-rx],maximum_distance_m=float(np.linalg.norm(tx-rx)-.01))[0]
        cases.setdefault('blocked' if hit else 'clear',tx)
    if set(cases)!={'blocked','clear'}:raise RuntimeError('Dashboard scene must exercise both clear and blocked receiver links')
    probes=[]
    for label,tx in cases.items():
        for index,site in enumerate(sites):
            origin=np.asarray(site['center_rf_m'])*[1,-1,-1];direction=tx-origin
            yaw=np.degrees(np.arctan2(direction[1],direction[0]));pitch=-np.degrees(np.arctan2(direction[2],np.linalg.norm(direction[:2])))
            probes.append({'name':f'Probe_{label}_{index}','origin':origin.tolist(),'rpy':[0,float(pitch),float(yaw)],'blocked':label=='blocked','target_range_m':float(np.linalg.norm(direction))})
    grid=json.loads((output/'scenario.json').read_text())['terrain_grid']
    peak=np.unravel_index(np.argmax(grid['heights_m']),np.shape(grid['heights_m']))
    x,y=grid['x_m'][peak[1]],grid['y_m'][peak[0]]
    for index,(x,y) in enumerate(((x,y),(-x,-y),(90,50))):
        probes.append({'name':f'Probe_height_{index}','origin':[x,-y,-350.],'rpy':[0,-90,0],'blocked':True})
    robot={'physics-type':'non-physics','links':[{'name':'Frame','collision':{'enabled':False}}],
        'sensors':[{'id':'lidar','type':'lidar','lidar-type':'generic_cylindrical','enabled':True,
        'parent-link':'Frame','number-of-channels':1,'range':600,'points-per-second':1000,
        'horizontal-rotation-frequency':10,'horizontal-fov-start-deg':-.03,'horizontal-fov-end-deg':.03,
        'vertical-fov-upper-deg':0,'vertical-fov-lower-deg':0,'disable-self-hits':True,
        'draw-debug-points':False,'report-point-cloud':True,'report-no-return-points':False,
        'origin':{'xyz':'0 0 0','rpy-deg':'0 0 0'}}]}
    (output/'sim_config/probe.jsonc').write_text(json.dumps(robot))
    path=output/'sim_config/scene.jsonc';scene=json.loads(path.read_text())
    scene['actors']=[actor for actor in scene['actors'] if not actor['name'].startswith('Probe_')]
    scene['actors'].extend({'type':'robot','name':p['name'],'origin':{
        'xyz':' '.join(map(str,p['origin'])),'rpy-deg':' '.join(map(str,p['rpy']))},'robot-config':'probe.jsonc'} for p in probes)
    path.write_text(json.dumps(scene))
    return probes


def spawn_environment(output,world):
    document,_,bindings=read_bundle(output/'bundle');report=isolate_blocks_scene(world)
    binding=AirSimGeometryBinding(document,bindings)
    for obj in binding.plan['objects']:
        obj['mesh'].update(base_color_rgba=TERRAIN_BASE_COLOR_RGBA,emissive_rgb=TERRAIN_EMISSIVE_RGB)
    spawn_placements(world,binding.plan)
    report['airsim']=binding.require_static_match(world,int(world.get_sim_time()))
    return report


def compare_probes(output,probes,messages,drones):
    document,_,_=read_bundle(output/'bundle');reports={}
    for probe in probes:
        name=probe['name'];packets=messages[name]
        if not packets:raise RuntimeError('No independent LiDAR packet: '+name)
        chunks=[np.asarray(m['point_cloud']).reshape(-1,3) for m in packets if m['point_cloud']]
        if not probe['blocked']:
            # The visual drone is at one clear target endpoint. Its chassis
            # is outside the ideal point-antenna RF model; reject earlier hits.
            if chunks and np.any(np.linalg.norm(np.concatenate(chunks),axis=1)<probe['target_range_m']-2):
                raise RuntimeError('Expected clear receiver ray hit unexpected visual geometry: '+name)
            reports[name]={'clear_no_environment_hit':True,'packets':len(packets)};continue
        if not chunks:raise RuntimeError('Expected shared terrain return missing in Unreal: '+name)
        points=np.concatenate(chunks);points=points[np.linspace(0,len(points)-1,min(32,len(points))).astype(int)]
        pose=drones[name].get_ground_truth_kinematics()['pose'];q=pose['orientation']
        rotation=Rotation.from_quat([q[k] for k in ('x','y','z','w')]).as_matrix()
        origin=np.array([pose['position'][k] for k in ('x','y','z')]);vectors=points@rotation.T
        lengths=np.linalg.norm(vectors,axis=1)
        hits=nearest_intersections(document,np.tile(origin,(len(points),1)),vectors,maximum_distance_m=600)
        if any(hit is None or hit['object_id']!='Terrain' for hit in hits):raise RuntimeError('Unreal hit is absent from RF mesh: '+name)
        error=float(np.max(abs(np.array([hit['distance_m'] for hit in hits])-lengths)))
        if error>.001:raise RuntimeError(f'Unreal/RF terrain surfaces differ at {name}: {error} m')
        reports[name]={'rays':len(points),'maximum_error_m':error}
    import sionna.rt as rt
    scene=rt.load_scene(str(output/'bundle/scene.xml'),merge_shapes=False)
    return {'unreal_cpu_lidar':reports,'sionna_mesh':require_rf_mesh_match(scene,document)}
