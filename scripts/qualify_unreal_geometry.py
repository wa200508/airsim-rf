"""Qualify a packaged Unreal cube against RF geometry using CPU LiDAR and CUDA rays.

Requires the verified Blocks server. This is shared primitive geometry, not
arbitrary Unreal mesh export or rendered-camera qualification.
"""
import argparse,json,time
import numpy as np
from pathlib import Path
from projectairsim import ProjectAirSimClient,World,Drone
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--pascal-compat',action='store_true');args=parser.parse_args()
root=args.output;root.mkdir(parents=True,exist_ok=False);sim=root/'sim';sim.mkdir()
robot={'physics-type':'non-physics','links':[{'name':'Frame','collision':{'enabled':False}}],
 'sensors':[{'id':'lidar1','type':'lidar','lidar-type':'generic_cylindrical','enabled':True,'parent-link':'Frame','number-of-channels':1,'range':20,'points-per-second':10000,'horizontal-rotation-frequency':10,'horizontal-fov-start-deg':-5,'horizontal-fov-end-deg':5,'vertical-fov-upper-deg':0,'vertical-fov-lower-deg':0,'disable-self-hits':True,'draw-debug-points':False,'report-point-cloud':True,'report-no-return-points':False,'origin':{'xyz':'0 0 0','rpy-deg':'0 0 0'}}]}
(sim/'robot.jsonc').write_text(json.dumps(robot))
scene={'id':'RFUnrealGeometry','scene-type':'UnrealNative','actors':[{'type':'robot','name':'Probe','origin':{'xyz':'0 0 -100','rpy-deg':'0 0 0'},'robot-config':'robot.jsonc'}],'clock':{'type':'steppable','step-ns':3_000_000,'real-time-update-rate':3_000_000,'pause-on-start':True},'home-geo-point':{'latitude':47.641468,'longitude':-122.140165,'altitude':122.}}
(sim/'scene.jsonc').write_text(json.dumps(scene))
client=ProjectAirSimClient(address='127.0.0.1');client.connect();messages=[]
try:
 world=World(client,'scene.jsonc',sim_config_path=str(sim.resolve()));world.pause();drone=Drone(client,world,'Probe')
 pose={'frame_id':'DEFAULT_ID','translation':{'x':5.,'y':0.,'z':-100.},'rotation':{'w':1.,'x':0.,'y':0.,'z':0.}}
 name=world.spawn_object('RFCheckCube','Cube',pose,[2.,2.,2.],False)
 print('spawned',name,'pose',world.get_object_pose(name),'scale',world.get_object_scale(name),flush=True)
 client.subscribe(drone.sensors['lidar1']['lidar'],lambda _,message:messages.append(message));time.sleep(.2)
 for _ in range(10):
  world.continue_until_sim_time(int(world.get_sim_time())+30_000_000,wait_until_complete=True);time.sleep(.05)
 blocked=list(messages);messages.clear()
 world.set_object_pose(name,{'frame_id':'DEFAULT_ID','translation':{'x':5.,'y':3.,'z':-100.},'rotation':{'w':1.,'x':0.,'y':0.,'z':0.}},True)
 for _ in range(10):
  world.continue_until_sim_time(int(world.get_sim_time())+30_000_000,wait_until_complete=True);time.sleep(.05)
 clear=list(messages)
 result={'name':name,'blocked_center_ned_m':[5,0,-100],'clear_pose':world.get_object_pose(name),'scale':world.get_object_scale(name),'kinematics':drone.get_ground_truth_kinematics(),'blocked_lidar':blocked,'clear_lidar':clear}
 (root/'unreal.json').write_text(json.dumps(result,indent=2)+'\n')
finally:client.disconnect()

import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
if args.pascal_compat:
 from airsim_rf.p100_compat import enable_pascal_compat
 enable_pascal_compat()
import sionna.rt as rt
from airsim_rf.single_bounce import SingleBouncePathSolver
vertices=[[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]]
faces=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]]
(root/'cube.ply').write_text('ply\nformat ascii 1.0\nelement vertex 8\nproperty float x\nproperty float y\nproperty float z\nelement face 12\nproperty list uchar int vertex_indices\nend_header\n'+'\n'.join(' '.join(map(str,v)) for v in vertices)+'\n'+'\n'.join('3 '+' '.join(map(str,f)) for f in faces)+'\n')
(root/'cube.xml').write_text('<scene version="2.1.0"><bsdf type="radio-material" id="material"><float name="relative_permittivity" value="5"/></bsdf><shape type="ply" id="cube"><string name="filename" value="cube.ply"/><ref id="material" name="bsdf"/><transform name="to_world"><translate x="5" y="0" z="100"/></transform></shape></scene>')
scene=rt.load_scene(str(root/'cube.xml'))
scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V');scene.rx_array=scene.tx_array
scene.add(rt.Transmitter('tx',position=[0,0,100]));scene.add(rt.Receiver('rx',position=[10,0,100]))
points=np.concatenate([np.array(m['point_cloud']).reshape(-1,3) for m in blocked])
if len(points)==0:raise ValueError('Unreal LiDAR produced no blocked-phase points')
# Sensor-frame points are NED-aligned; origin is RF (0,0,100).
rf_relative=points*np.array([1,-1,-1]);direction=rf_relative/np.linalg.norm(rf_relative,axis=1)[:,None]
hits=scene.mi_scene.ray_intersect(mi.Ray3f(mi.Point3f(0,0,100),mi.Vector3f(direction.T)))
actual=hits.p.numpy().T;expected=rf_relative+[0,0,100]
ray_error=float(np.max(np.linalg.norm(actual-expected,axis=1)))
solver=SingleBouncePathSolver()
def path_count():
 paths=solver(scene,max_depth=0);_,delay=paths.cir(normalize_delays=False,out_type='numpy');return int(np.sum(delay>=0))
blocked_paths=path_count();next(iter(scene.objects.values())).position=[5,-3,100];clear_paths=path_count()
# Ignore stale subscription messages by simulator epoch after relocation.
last_blocked=max(m['time_stamp'] for m in blocked)
clear_points=sum(len(m['point_cloud'])//3 for m in clear if m['time_stamp']>last_blocked)
checks={'unreal_face_at_4m':bool(np.max(abs(points[:,0]-4))<.001),
 'rf_lidar_hits_within_1mm':bool(np.isfinite(ray_error) and ray_error<.001),
 'blocked_direct_path_absent':blocked_paths==0,'relocated_direct_path_present':clear_paths==1,
 'clear_lidar_messages_received':any(m['time_stamp']>last_blocked for m in clear),
 'relocated_cube_outside_lidar_view':clear_points==0}
report={'status':'passed' if all(checks.values()) else 'failed','checks':checks,
 'scope':'Unreal CPU-LiDAR collision primitive and CUDA RF mesh alignment; null-RHI, no rendered images or arbitrary mesh export',
 'blocked_points':len(points),'maximum_rf_lidar_hit_error_m':ray_error,'clear_points':clear_points,
 'blocked_direct_paths':blocked_paths,'clear_direct_paths':clear_paths,
 'simulation_seconds_per_phase':.3,'backend':mi.variant(),'sionna_rt':rt.__version__}
(root/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if report['status']!='passed':raise SystemExit(1)
