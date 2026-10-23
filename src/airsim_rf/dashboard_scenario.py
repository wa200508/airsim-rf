"""Shared terrain and a 250 m left-hand orbit for the localhost use case."""
import json
from pathlib import Path
import tempfile
import numpy as np
from scipy.signal import firwin, upfirdn
FS=2_000_000
CARRIER=915_000_000.
RADIUS=250.
ALTITUDE=200.
SPEED=25.
ADVANCE_NS=120_000_000


def atomic_json(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,allow_nan=False)+'\n');tmp.replace(path)


def orbit_pose(seconds,radius=RADIUS,speed=SPEED):
    angle=speed/radius*seconds
    return np.array([radius*np.cos(angle),radius*np.sin(angle),ALTITUDE]),np.array([-speed*np.sin(angle),speed*np.cos(angle),0.])


def waveform_window(epoch_ns,count,origin_ns):
    """Counter-indexed QPSK: overlapping finite buffers preserve the same samples."""
    first=round((epoch_ns-origin_ns)*FS/1e9)-4000
    start=first//80-12;end=(first+count+8000)//80+12
    index=np.arange(start,end,dtype=np.int64).astype(np.uint64)
    with np.errstate(over='ignore'):
        hashed=(index+np.uint64(20261021))*np.uint64(0x9E3779B97F4A7C15)
        hashed=(hashed^(hashed>>np.uint64(30)))*np.uint64(0xBF58476D1CE4E5B9)
        hashed=(hashed^(hashed>>np.uint64(27)))*np.uint64(0x94D049BB133111EB)
        hashed^=hashed>>np.uint64(31)
    symbols=((2*(hashed&1).astype(float)-1)+1j*(2*((hashed>>1)&1).astype(float)-1))/np.sqrt(2)
    taps=firwin(801,20000,fs=FS,window=('kaiser',8.))*80
    samples=upfirdn(taps,symbols,up=80)
    offset=first-start*80+400
    return samples[offset:offset+count+8000],origin_ns+round(first*1e9/FS)


def prepare(output,runtime_source):
    import commentjson
    from .dashboard_view import CAMERA_FOV_DEG
    from .geometry import export_sionna_geometry
    from .geometry_sync import placement_plan
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    from .terrain import demo_terrain, TerrainGrid
    original=demo_terrain()
    terrain=TerrainGrid(original.x_m*4,original.y_m*4,100+original.heights_m*3)
    rf_vertices,faces=terrain.mesh()
    vertices=rf_vertices*[1,-1,-1]
    objects=[{'id':'Terrain','material':'earth','vertices_local':vertices.tolist(),'faces':faces.tolist(),'local_to_ned_m':np.eye(4).tolist()}]
    geometry={'schema_version':1,'scene_id':'OrbitRF','revision':'2','source':{'adapter':'demo_terrain','version':'2','asset':'demo_terrain:xy4:z3:base100','revision':'2','geometry_kind':'shared'},
        'materials':{name:{'relative_permittivity':value,'conductivity_s_m':.01,'assumption':'Illustrative uncalibrated dielectric'} for name,value in [('earth',5.),('rock',6.)]},'objects':objects}
    bindings={'version':1,'geodetic_anchor':{'latitude':47.641468,'longitude':-122.140165,'altitude_m':122.},
        'objects':{obj['id']:{'simulator':{'object_name':obj['id'],'asset_path':'generated:glb','local_to_actor_m':np.eye(4).tolist(),'asset_provenance':'Same triangles in Unreal and RF'}} for obj in objects}}
    # The exporter deliberately requires a fresh directory. Build there first,
    # then replace only our generated bundle; keep logs and recorded I/Q intact.
    with tempfile.TemporaryDirectory(prefix='.prepare-',dir=output) as temporary:
        staging=Path(temporary);target=output/'bundle';previous=staging/'previous'
        export_sionna_geometry(geometry,staging/'bundle',provenance={'scope':'dashboard shared terrain'},bindings=bindings)
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            raise ValueError('Dashboard bundle path must be a directory; choose a fresh --run-dir')
        replaced=target.exists()
        if replaced:target.rename(previous)
        try:(staging/'bundle').rename(target)
        except BaseException:
            if replaced:previous.rename(target)
            raise
    atomic_json(output/'placement.json',placement_plan(geometry,bindings))
    offsets=(np.arange(4)-1.5)*299792458./CARRIER/2
    arrays={'schema_version':1,'sample_rate_hz':FS,'carrier_hz':CARRIER,'sites':[{'id':f'site{i}','channels':[f'site{i}_e{j}' for j in range(4)],'center_rf_m':[0.,float(y),float(terrain.elevation_at(0,y)+8)],'yaw_rad':0.,'element_offsets_m':offsets.tolist(),'calibration_complex':[[1.,0.]]*4} for i,y in enumerate((-25,25))],
        'scope':'Ideal coherent ULAs; full-circle azimuth/elevation ambiguities remain explicit'}
    atomic_json(output/'arrays.json',arrays)
    # Receiver-facing metadata contains only rate/frequency and known sensor
    # geometry/calibration. Scene assumptions and source truth stay elsewhere.
    atomic_json(output/'receiver-config.json',{key:arrays[key] for key in
        ('schema_version','sample_rate_hz','carrier_hz','sites')})
    source=Path(runtime_source)/'client/python/example_user_scripts/sim_config/robot_quadrotor_fastphysics_sensors.jsonc'
    if not source.exists():
        source=Path('/opt/airsim-rf/.deps/ProjectAirSim/client/python/example_user_scripts/sim_config/robot_quadrotor_fastphysics_sensors.jsonc')
    if not source.exists():raise ValueError('Pinned ProjectAirSim robot template is missing; rebuild the qualified CPU base image')
    robot=commentjson.loads(source.read_text());robot['controller']['simple-flight-api-settings']['parameters']={'MPC_XY_VEL_MAX':30.}
    robot['sensors']=[s for s in robot['sensors'] if s['id']=='Chase']
    camera=robot['sensors'][0];camera['gimbal']={'lock-roll':False,'lock-pitch':False,'lock-yaw':False};camera['capture-interval']=.12;camera['origin']={'xyz':'-4.85 0 -1.2','rpy-deg':'0 -20 0'}
    camera['capture-settings'][0].update(width=960,height=540,compress=False,**{'fov-degrees':CAMERA_FOV_DEG})
    sim=output/'sim_config';sim.mkdir(exist_ok=True);atomic_json(sim/'orbit.jsonc',robot)
    atomic_json(sim/'scene.jsonc',{'id':'OrbitDashboard','scene-type':'UnrealNative','actors':[{'type':'robot','name':'OrbitDrone','origin':{'xyz':f'250 0 {-ALTITUDE}','rpy-deg':'0 0 -90'},'robot-config':'orbit.jsonc'}],
        'clock':{'type':'steppable','step-ns':3_000_000,'real-time-update-rate':3_000_000,'pause-on-start':True},'home-geo-point':{'latitude':47.641468,'longitude':-122.140165,'altitude':122.}})
    atomic_json(output/'scenario.json',{'radius_m':RADIUS,'speed_m_s':SPEED,'turn':'left','period_s':2*np.pi*RADIUS/SPEED,'terrain_width_m':800,'advance_ns':ADVANCE_NS,'source':'ProjectAirSim Fast Physics actual pose readback; native closed-loop carrot follower on a 250 m circle','altitude_rf_m':ALTITUDE,'terrain':'Existing demo_terrain hills/swale; horizontal scale 4, relief scale 3, RF base 100 m','terrain_relief_m':90,'terrain_grid':{'x_m':terrain.x_m.tolist(),'y_m':terrain.y_m.tolist(),'heights_m':terrain.heights_m.tolist()},'sites':arrays['sites'],'screen':'Natural hills and drainage valley; no artificial screen','camera':'Inward-looking gimballed Chase; native Blocks physical scenery removed','propagation':'direct visibility + retained first-order specular paths'})
    return arrays
