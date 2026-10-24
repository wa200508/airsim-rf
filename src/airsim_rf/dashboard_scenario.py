"""Compile a portable input package into shared simulator/RF runtime artifacts."""
from copy import deepcopy
import json
import shutil
from pathlib import Path
import tempfile
import numpy as np
from scipy.signal import firwin,upfirdn
from .scenario_definition import load,asset,snapshot,fingerprints

# Historical example constants are lazy aliases; a custom scenario never needs
# to load the packaged example just to import this runtime/compiler module.
def __getattr__(name):
    if name not in ('FS','CARRIER','ADVANCE_NS','RADIUS','SPEED','ALTITUDE'):raise AttributeError(name)
    config=load()
    values={'FS':config['radios']['sample_rate_hz'],'CARRIER':config['radios']['carrier_hz'],
        'ADVANCE_NS':config['mission']['rf_update_ns']}
    flight=config['flight']['actors'][0]['flight']
    values.update(RADIUS=flight['radius_m'],SPEED=flight['speed_m_s'],ALTITUDE=flight['center_rf_m'][2])
    if name not in values:raise AttributeError(name)
    return values[name]


def atomic_json(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,allow_nan=False)+'\n');tmp.replace(path)


def orbit_pose(seconds,radius=None,speed=None):
    flight=load()['flight']['actors'][0]['flight']
    radius=flight['radius_m'] if radius is None else radius
    speed=flight['speed_m_s'] if speed is None else speed
    angle=speed/radius*seconds
    return np.array([radius*np.cos(angle),radius*np.sin(angle),flight['center_rf_m'][2]]),np.array([-speed*np.sin(angle),speed*np.cos(angle),0.])


def flight_path(actor,duration_s):
    """Compile declared RF-coordinate circle/waypoints; no simulated pose feedback."""
    flight=actor['flight']
    if flight['type']=='hold':return []
    if flight['type']=='waypoints':
        points=np.asarray(flight['points_rf_m'],float)
        if flight.get('repeat',False):
            points=np.vstack((points,points[0]));length=np.linalg.norm(np.diff(points,axis=0),axis=1).sum()
            if length<=0:raise ValueError('Repeated waypoint route must have nonzero length')
            points=np.vstack([points[:-1]]*(int(np.ceil(duration_s*flight['speed_m_s']/length))+1)+[points[-1:]])
        return points.tolist()
    if flight['type']=='racetrack':
        c=np.asarray(flight['center_rf_m']);half=flight['straight_length_m']/2;r=flight['turn_radius_m']
        # Clockwise stadium: upper straight eastbound, right arc, lower straight, left arc.
        n=max(2,int(np.ceil(180/flight['waypoint_step_deg'])));theta=np.linspace(np.pi/2,-np.pi/2,n+1)
        upper=np.column_stack((np.linspace(-half,half,max(2,int(2*half/5))),np.full(max(2,int(2*half/5)),r)))
        right=np.column_stack((half+r*np.cos(theta),r*np.sin(theta)))
        lower=upper[::-1]*[1,-1]
        left=np.column_stack((-half+r*np.cos(theta-np.pi),r*np.sin(theta-np.pi)))
        points=np.vstack((upper,right[1:],lower[1:],left[1:]))
        cycles=int(np.ceil(duration_s*flight['speed_m_s']/(4*half+2*np.pi*r)))+1
        points=np.vstack([points[:-1]]*cycles+[points[-1:]])
        return (c+np.column_stack((points,np.zeros(len(points))))).tolist()
    center=np.asarray(flight['center_rf_m']);start=np.asarray(actor['position_rf_m'])-center
    cycles=int(np.ceil(duration_s/(2*np.pi*flight['radius_m']/flight['speed_m_s'])))+1
    sign=1 if flight['direction']=='left' else -1
    angle=np.arctan2(start[1],start[0])+sign*np.linspace(0,cycles*2*np.pi,cycles*int(np.ceil(360/flight['waypoint_step_deg']))+1)
    return (center+np.column_stack((flight['radius_m']*np.cos(angle),flight['radius_m']*np.sin(angle),np.zeros(len(angle))))).tolist()


class WaveformSource:
    """Private continuous TX samples, from a configurable QPSK source or .npy file."""
    def __init__(self,directory,definition,sample_rate_hz):
        self.config=json.loads(asset(directory,definition).read_text());self.rate=sample_rate_hz
        self.samples=None
        if self.config['type']=='samples':
            self.samples=np.load(asset(directory,self.config['file']),allow_pickle=False)
            if self.samples.ndim!=1 or self.samples.dtype.kind not in 'fc' or not np.isfinite(self.samples).all():
                raise ValueError('Waveform .npy must contain a finite 1-D real or complex sample array')
        else:
            c=self.config
            self.taps=firwin(c['filter_taps'],c['cutoff_hz'],fs=self.rate,window=('kaiser',c['kaiser_beta']))*c['samples_per_symbol']

    def window(self,epoch_ns,count,origin_ns):
        if self.samples is not None:return self.samples,origin_ns,'zero'
        c=self.config;sps=c['samples_per_symbol'];halo=max(c['history_samples'],c['filter_taps'])
        first=round((epoch_ns-origin_ns)*self.rate/1e9)-halo
        margin=int(np.ceil(c['filter_taps']/sps))+2
        start=first//sps-margin;end=(first+count+2*halo)//sps+margin
        index=np.arange(start,end,dtype=np.int64).astype(np.uint64)
        with np.errstate(over='ignore'):
            hashed=(index+np.uint64(c['seed']))*np.uint64(0x9E3779B97F4A7C15)
            hashed=(hashed^(hashed>>np.uint64(30)))*np.uint64(0xBF58476D1CE4E5B9)
            hashed=(hashed^(hashed>>np.uint64(27)))*np.uint64(0x94D049BB133111EB)
            hashed^=hashed>>np.uint64(31)
        symbols=((2*(hashed&1).astype(float)-1)+1j*(2*((hashed>>1)&1).astype(float)-1))/np.sqrt(2)
        samples=upfirdn(self.taps,symbols,up=sps)
        offset=first-start*sps+(len(self.taps)-1)//2
        return samples[offset:offset+count+2*halo],origin_ns+round(first*1e9/self.rate),'error'


def waveform_window(epoch_ns,count,origin_ns):
    """Compatibility wrapper for the packaged example; not the runtime producer."""
    config=load();tx=config['radios']['transmitters'][0]
    samples,reference,_=WaveformSource(config['_directory'],tx['waveform'],config['radios']['sample_rate_hz']).window(epoch_ns,count,origin_ns)
    return samples,reference


def prepare(output,runtime_source=None,scenario_dir=None,duration_s=None,check_iq_space=False):
    """Snapshot input files; compile them without loading Sionna or connecting AirSim."""
    import commentjson
    from .geometry import export_sionna_geometry,validate_geometry
    from .geometry_sync import placement_plan
    from .terrain import TerrainGrid
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    config=load(scenario_dir);source=Path(config['_directory']);frozen=output/'scenario-input'
    if source.resolve()!=frozen.resolve():config=snapshot(source,frozen)
    if duration_s is not None:
        if not 0<duration_s<=3600:raise ValueError('Duration must be in (0,3600] seconds')
        config['mission']['duration_s']=duration_s
    if check_iq_space and config['mission'].get('record_iq',True):
        mission=config['mission'];radio=config['radios']
        windows=max(1,int(np.ceil(mission['duration_s']*1e9/mission['rf_update_ns'])))
        count=round(mission['rf_update_ns']*radio['sample_rate_hz']/1e9)
        required=windows*count*sum(len(site['channels']) for site in radio['sites'])*8
        if shutil.disk_usage(output).free<required+64*1024**2:
            raise ValueError(f'Insufficient output space for bulk I/Q: need {required} sample bytes plus 64 MiB headroom; shorten mission or set mission.record_iq=false')
    env=config['environment'];terrain=None
    if env['type']=='heightfield':
        terrain=TerrainGrid(env['x_m'],env['y_m'],env['heights_m']);vertices,faces=terrain.mesh()
        geometry={'schema_version':1,'scene_id':env['scene_id'],'revision':env['revision'],
            'source':{'adapter':'scenario-heightfield','version':'1','asset':'environment.json','revision':env['revision'],'geometry_kind':'shared'},
            'materials':env['materials'],'objects':[{'id':'Terrain','material':env['material'],
            'vertices_local':(vertices*[1,-1,-1]).tolist(),'faces':faces.tolist(),'local_to_ned_m':np.eye(4).tolist()}]}
    elif env['type']=='geometry':geometry=validate_geometry(json.loads(asset(frozen,env['file']).read_text()))
    else:raise ValueError('Environment type must be heightfield or geometry')
    bindings={'version':1,'geodetic_anchor':env['geodetic_anchor'],
        'objects':{obj['id']:{'simulator':{'object_name':obj['id'],'asset_path':'generated:glb','local_to_actor_m':np.eye(4).tolist(),
        'asset_provenance':'Same scenario triangles in Unreal and RF'}} for obj in geometry['objects']}}
    with tempfile.TemporaryDirectory(prefix='.prepare-',dir=output) as temporary:
        staging=Path(temporary);target=output/'bundle';previous=staging/'previous'
        export_sionna_geometry(geometry,staging/'bundle',provenance={'scope':'scenario shared geometry'},bindings=bindings)
        if target.is_symlink() or (target.exists() and not target.is_dir()):raise ValueError('Dashboard bundle path must be a directory; choose a fresh --run-dir')
        replaced=target.exists()
        if replaced:target.rename(previous)
        try:(staging/'bundle').rename(target)
        except BaseException:
            if replaced:previous.rename(target)
            raise
    atomic_json(output/'placement.json',placement_plan(geometry,bindings))
    radio=config['radios'];sites=deepcopy(radio['sites'])
    if radio.get('mode')=='fmcw-radar':
        clutter=radio['radar']['clutter']
        clutter['shape_materials']={'obj_'+obj['id']:obj['material'] for obj in geometry['objects'] if obj['material'] in clutter['materials']}
        if clutter['enabled'] and not clutter['shape_materials']:raise ValueError('Enabled clutter requires configured surface objects')
    for site in sites:
        reference=site.pop('altitude_reference')
        if reference=='agl':
            if terrain is None:raise ValueError('AGL receiver sites need a heightfield; use absolute RF coordinates with a geometry scene')
            site['center_rf_m'][2]+=float(terrain.elevation_at(*site['center_rf_m'][:2]))
    # Fixed target coordinates are resolved once from the exact shared DEM.
    # Snapshot input retains AGL edit values; runtime and visual markers use
    # the same absolute scattering center. These are not flight actors.
    for target in radio.get('radar',{}).get('targets',[]):
        if 'actor' not in target and target['altitude_reference']=='agl':
            if terrain is None:raise ValueError('AGL targets need a heightfield; use absolute coordinates with a geometry scene')
            target['position_rf_m'][2]+=float(terrain.elevation_at(*target['position_rf_m'][:2]))
            target['altitude_reference']='absolute'
    arrays={'schema_version':1,'sample_rate_hz':radio['sample_rate_hz'],'carrier_hz':radio['carrier_hz'],'sites':sites}
    if radio.get('mode')=='fmcw-radar':
        mode=config['skill']['mode_config'];tx=mode['waveform'];rx=mode['receiver']
        arrays['acquisition']={k:tx[k] for k in ('bandwidth_hz','chirp_duration_s','pri_s')}
        arrays['acquisition'].update({k:rx[k] for k in ('num_samples','adc_start_s')})
        atomic_json(output/'radar-mode.json',mode)
        arrays['voltage_reference']='bias-subtracted ADC volts'
        arrays['acquisition'].update(type='fmcw-dechirped',adc_gate='zero-filled outside acquisition gate',chirp_origin='first window timestamp',impedance_ohm=50.)
    atomic_json(output/'arrays.json',arrays);atomic_json(output/'receiver-config.json',arrays)
    # Validate finite source coverage before GPU/service launch. No file looping.
    for tx in radio['transmitters']:
        waveform=WaveformSource(frozen,tx['waveform'],radio['sample_rate_hz'])
        count=round(config['mission']['rf_update_ns']*radio['sample_rate_hz']/1e9)
        if waveform.samples is not None:
            windows=int(np.ceil(config['mission']['duration_s']*1e9/config['mission']['rf_update_ns']))
            if len(waveform.samples)<windows*count+32:raise ValueError('Sampled waveform must cover the rounded mission duration plus 32 lookahead samples: '+tx['id'])
    sim=output/'sim_config';sim.mkdir(exist_ok=True);actors=[];camera=config['camera']
    for actor in config['flight']['actors']:
        robot=commentjson.loads(asset(frozen,actor['vehicle']).read_text())
        if actor['id']==camera['actor']:
            sensor=next((s for s in robot['sensors'] if s['id']==camera['sensor']),None)
            if sensor is None:raise ValueError('Camera sensor missing from scenario vehicle: '+camera['sensor'])
            sensor['capture-interval']=camera['capture_interval_s']
            sensor['capture-settings'][0].update(width=camera['width'],height=camera['height'],compress=False,**{'fov-degrees':camera['fov_deg']})
        filename=actor['id']+'.jsonc';atomic_json(sim/filename,robot)
        if actor['id']=='OrbitDrone':atomic_json(sim/'orbit.jsonc',robot)  # Old inspection tools.
        actors.append({'type':'robot','name':actor['id'],'origin':{'xyz':' '.join(map(str,np.asarray(actor['position_rf_m'])*[1,-1,-1])),
            'rpy-deg':f'0 0 {-actor["yaw_deg"]}'},'robot-config':filename})
    anchor=env['geodetic_anchor'];step=config['mission']['physics_step_ns']
    atomic_json(sim/'scene.jsonc',{'id':config['id'],'scene-type':'UnrealNative','actors':actors,
        'clock':{'type':'steppable','step-ns':step,'real-time-update-rate':step,'pause-on-start':True},
        'home-geo-point':{'latitude':anchor['latitude'],'longitude':anchor['longitude'],'altitude':anchor['altitude_m']}})
    runtime={k:v for k,v in config.items() if k!='_directory'}
    runtime['input_sha256']=fingerprints(frozen);atomic_json(output/'runtime.json',runtime)
    first=config['flight']['actors'][0];flight=first['flight'];routes=[flight_path(actor,config['mission']['duration_s']) for actor in config['flight']['actors']]
    summary={'id':config['id'],'title':config['title'],'input_sha256':runtime['input_sha256'],'advance_ns':config['mission']['rf_update_ns'],
        'flight_type':flight['type'],'straight_length_m':flight.get('straight_length_m',0),'turn_radius_m':flight.get('turn_radius_m',0),'radius_m':flight.get('radius_m',0),'speed_m_s':flight.get('speed_m_s',0),'turn':flight.get('direction',flight['type']),
        'altitude_rf_m':first['position_rf_m'][2],'sites':sites,'routes_rf_m':routes,
        'sample_rate_hz':radio['sample_rate_hz'],'carrier_hz':radio['carrier_hz'],'transmitters':len(radio['transmitters']),
        'camera':camera,'source':'Scenario package; actual ProjectAirSim pose readback drives RF',
        'propagation':radio['propagation'],'skill_kind':config['skill']['kind'],'skill_name':config['skill'].get('name',config['skill']['kind'])}
    if radio.get('mode')=='fmcw-radar':summary['radar_targets']=deepcopy(radio['radar']['targets'])
    if terrain is not None:
        summary.update(terrain_width_m=float(max(np.ptp(terrain.x_m),np.ptp(terrain.y_m))),terrain_relief_m=float(np.ptp(terrain.heights_m)),
            terrain_grid={'x_m':terrain.x_m.tolist(),'y_m':terrain.y_m.tolist(),'heights_m':terrain.heights_m.tolist()})
    else:summary['terrain_width_m']=max(np.ptp(np.asarray(obj['vertices_local'])[:,:2],axis=0).max() for obj in geometry['objects'])
    atomic_json(output/'scenario.json',summary)
    return arrays


def emitters_for_window(radio,sources,epoch_ns,count,origin_ns):
    """Build independent source buffers using only configured radio inputs."""
    from .sdr import SDREmitter
    from .sampled_waveform import SampledWaveform
    emitters={}
    for tx in radio['transmitters']:
        values,reference,boundary=sources[tx['id']].window(epoch_ns,count,origin_ns)
        emitters[tx['id']]=SDREmitter(SampledWaveform(values,radio['sample_rate_hz'],reference,boundary=boundary),
            transmit_power_w=tx['power_w'],baseband_frequency_bounds_hz=tuple(tx['baseband_bounds_hz']))
    return emitters


def create_receiver(scene,radio,arrays,sources,origin_ns,count):
    """Shared live/qualification adapter; all physical settings come from inputs."""
    import sionna.rt as rt
    from .sdr import SDRNetworkReceiver,PlutoSDRProfile
    antenna=radio['antenna']
    scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern=antenna['tx_pattern'],polarization=antenna['polarization'])
    scene.rx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern=antenna['rx_pattern'],polarization=antenna['polarization'])
    for tx in radio['transmitters']:scene.add(rt.Transmitter(tx['id'],position=[0,0,1]))
    for site in arrays['sites']:
        direction=np.array([-np.sin(site['yaw_rad']),np.cos(site['yaw_rad']),0.])
        for name,offset in zip(site['channels'],site['element_offsets_m']):
            scene.add(rt.Receiver(name,position=(np.asarray(site['center_rf_m'])+offset*direction).tolist(),orientation=[site['yaw_rad'],0,0]))
    profile={**radio['receiver_profile'],'carrier_hz':radio['carrier_hz'],'sample_rate_hz':radio['sample_rate_hz']}
    return SDRNetworkReceiver(scene,emitters_for_window(radio,sources,origin_ns,count,origin_ns),
        PlutoSDRProfile(**profile),**radio['propagation'])
