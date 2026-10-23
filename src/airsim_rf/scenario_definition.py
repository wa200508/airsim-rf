"""Portable scenario input package. Standard-library only; no source or skill imports."""
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile


def default_directory():
    candidates=(Path(__file__).resolve().parents[2]/'scenarios/drone-orbit',
                Path(__file__).parent/'scenarios/drone-orbit',
                Path(sys.prefix)/'share/airsim-rf/scenarios/drone-orbit')
    return next((p for p in candidates if (p/'scenario.json').is_file()),candidates[0])


def asset(directory,name):
    root=Path(directory).resolve()
    if not isinstance(name,str) or not name or Path(name).is_absolute():
        raise ValueError('Scenario assets must use relative paths inside the scenario directory')
    path=(root/name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Missing or out-of-package scenario asset: '+name)
    return path


def _number(value,label,minimum=None,integer=False):
    if (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value)
            or (minimum is not None and value<minimum) or (integer and not isinstance(value,int))):
        raise ValueError('Invalid '+label)
    return value


def _vector(value,size,label):
    if not isinstance(value,list) or len(value)!=size:raise ValueError('Invalid '+label)
    for item in value:_number(item,label)


def _identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*',value):
        raise ValueError('Invalid scenario identifier: '+str(value))


def load(directory=None):
    """Read related JSON inputs, reject inconsistent clocks/assets before Docker."""
    root=Path(directory or default_directory()).resolve()
    if root.is_file():
        if root.name!='scenario.json':raise ValueError('Point --scenario to a package directory or its scenario.json')
        root=root.parent
    config=json.loads((root/'scenario.json').read_text())
    required={'schema_version','id','title','environment','flight','radios','mission','camera','appearance','skill'}
    if set(config)!=required or type(config['schema_version']) is not int or config['schema_version']!=1:raise ValueError('Scenario schema v1 fields required: '+', '.join(sorted(required)))
    _identifier(config['id'])
    for name in ('environment','flight','radios'):
        config[name]=json.loads(asset(root,config[name]).read_text())
    mission=config['mission'];rate=config['radios']['sample_rate_hz'];carrier=config['radios']['carrier_hz']
    for key in ('physics_step_ns','rf_update_ns'):_number(mission[key],key,1,integer=True)
    _number(mission['duration_s'],'duration_s',.001)
    if mission['duration_s']>3600:raise ValueError('Mission duration must not exceed 3600 s')
    _number(rate,'sample_rate_hz',1);_number(carrier,'carrier_hz',1)
    count=mission['rf_update_ns']*rate/1e9
    if mission['rf_update_ns']%mission['physics_step_ns'] or abs(count-round(count))>1e-6 or not 64<=count<=2_000_000:
        raise ValueError('RF update must align with physics steps and contain 64..2000000 whole receiver samples')
    env=config['environment']
    if env['type']=='geometry':asset(root,env['file'])
    elif env['type']=='heightfield':
        if len(env['x_m'])<2 or len(env['y_m'])<2 or len(env['heights_m'])!=len(env['y_m']) or any(len(row)!=len(env['x_m']) for row in env['heights_m']):raise ValueError('Heightfield axes/heights shape mismatch')
        for axis in (env['x_m'],env['y_m']):
            for value in axis:_number(value,'terrain coordinate')
            if any(b<=a for a,b in zip(axis,axis[1:])):raise ValueError('Terrain axes must increase')
        for row in env['heights_m']:
            for value in row:_number(value,'terrain elevation')
    else:raise ValueError('Environment type must be heightfield or geometry')
    actors=config['flight']['actors'];names=[]
    if not actors:raise ValueError('At least one flight actor required')
    for actor in actors:
        _identifier(actor['id']);names.append(actor['id']);asset(root,actor['vehicle'])
        _vector(actor['position_rf_m'],3,'actor position');_number(actor['yaw_deg'],'actor yaw')
        _number(actor['settle_s'],'settle duration',0)
        flight=actor['flight'];kind=flight['type']
        if kind not in ('circle','waypoints','hold'):raise ValueError('Flight type must be circle, waypoints or hold')
        if kind!='hold':
            _number(flight['speed_m_s'],'flight speed',.001);_number(flight['lookahead_m'],'flight lookahead',.001)
            _number(flight['adaptive_lookahead'],'adaptive lookahead',0)
        if kind=='circle':
            _vector(flight['center_rf_m'],3,'orbit center');_number(flight['radius_m'],'orbit radius',.001)
            _number(flight['waypoint_step_deg'],'waypoint spacing',.01)
            if flight['waypoint_step_deg']>90 or flight['direction'] not in ('left','right'):raise ValueError('Invalid circle direction/waypoint spacing')
            center=flight['center_rf_m'];position=actor['position_rf_m']
            if abs(math.hypot(position[0]-center[0],position[1]-center[1])-flight['radius_m'])>.01 or abs(position[2]-center[2])>.01:
                raise ValueError('Circle actor must start on its declared orbit at the orbit altitude')
        if kind=='waypoints':
            if len(flight['points_rf_m'])<2:raise ValueError('At least two waypoints required')
            for point in flight['points_rf_m']:_vector(point,3,'waypoint')
    if len(set(names))!=len(names):raise ValueError('Duplicate actor IDs')
    radios=config['radios'];tx_names=[];channels=[]
    if not radios['transmitters'] or not radios['sites']:raise ValueError('Transmitters and receiver sites required')
    for tx in radios['transmitters']:
        _identifier(tx['id']);tx_names.append(tx['id'])
        if tx['actor'] not in names:raise ValueError('Unknown transmitter actor: '+tx['actor'])
        _vector(tx['mount_body_m'],3,'TX mount');_number(tx['power_w'],'TX power',0)
        _vector(tx['baseband_bounds_hz'],2,'baseband bounds')
        lo,hi=tx['baseband_bounds_hz']
        if not -rate/2<lo<hi<rate/2:raise ValueError('TX baseband bounds must be ordered inside Nyquist')
        wave=json.loads(asset(root,tx['waveform']).read_text())
        if wave['type']=='samples':asset(root,wave['file'])
        elif wave['type']=='qpsk':
            for key in ('samples_per_symbol','filter_taps','history_samples'):_number(wave[key],key,1,integer=True)
            _number(wave['seed'],'waveform seed',0,integer=True);
            if wave['seed']>2**64-1:raise ValueError('QPSK seed must fit uint64')
            _number(wave['kaiser_beta'],'Kaiser beta',0)
            _number(wave['cutoff_hz'],'waveform cutoff',.001)
            if wave['filter_taps']%2!=1 or wave['cutoff_hz']>=rate/2:raise ValueError('QPSK FIR needs odd taps and sub-Nyquist cutoff')
        else:raise ValueError('Waveform type must be qpsk or samples')
    site_names=[]
    for site in radios['sites']:
        _identifier(site['id']);site_names.append(site['id']);_vector(site['center_rf_m'],3,'receiver center')
        _number(site['yaw_rad'],'receiver yaw')
        if site['altitude_reference'] not in ('agl','absolute'):raise ValueError('Receiver altitude_reference must be agl or absolute')
        offsets=site['element_offsets_m']
        if not offsets or len(offsets)!=len(site['channels']) or len(offsets)!=len(site['calibration_complex']):raise ValueError('Array offsets/channels/calibration lengths differ')
        for offset in offsets:_number(offset,'element offset')
        if any(b<=a for a,b in zip(offsets,offsets[1:])):raise ValueError('Array offsets must be ordered')
        for gain in site['calibration_complex']:
            _vector(gain,2,'calibration');
            if gain==[0,0]:raise ValueError('Calibration gain must be nonzero')
        for channel in site['channels']:_identifier(channel);channels.append(channel)
    if len(set(tx_names+channels))!=len(tx_names+channels) or len(set(site_names))!=len(site_names):raise ValueError('Duplicate radio/channel/site IDs')
    if radios['receiver_profile'].get('sample_rate_hz',rate)!=rate or radios['receiver_profile'].get('carrier_hz',carrier)!=carrier:
        raise ValueError('Receiver profile rate/carrier disagree with radio configuration')
    bandwidth=radios['receiver_profile']['rf_bandwidth_hz']
    _number(bandwidth,'receiver RF bandwidth',.001)
    if bandwidth>=rate:raise ValueError('Receiver RF bandwidth must be below the sample rate')
    if not radios['propagation'].get('continuous',False) or not radios['propagation'].get('path_diagnostics',False):
        raise ValueError('Dashboard requires continuous receiver state and path diagnostics')
    camera=config['camera']
    if not isinstance(camera['labels'],bool):raise ValueError('Camera labels must be boolean')
    if camera['actor'] not in names:raise ValueError('Camera actor missing from flight')
    for key in ('distance_m','capture_interval_s','fov_deg'):_number(camera[key],'camera '+key,.001)
    if camera['fov_deg']>=179 or camera['capture_interval_s']>mission['rf_update_ns']/1e9:
        raise ValueError('Camera FOV must be <179 degrees and interval no longer than an RF window')
    for key in ('width','height'):_number(camera[key],'camera '+key,64,integer=True)
    _number(camera['elevation_bias'],'camera elevation bias',0)
    for key,size in (('terrain_base_color_rgba',4),('terrain_emissive_rgb',3)):
        _vector(config['appearance'][key],size,key)
        if any(not 0<=x<=1 for x in config['appearance'][key]):raise ValueError('Visual color/emission must lie in [0,1]')
    skill=config['skill']
    if skill['kind'] not in ('music','custom'):raise ValueError('Skill kind must be music or custom')
    if skill['contract']!='receiver-tcp-v2' or skill['revision_policy'] not in ('matching','independent'):raise ValueError('Unsupported skill contract/revision policy')
    if not isinstance(skill['image'],str) or not skill['image'] or not isinstance(skill['command'],list) or any(not isinstance(x,str) for x in skill['command']):raise ValueError('Skill image and argument list required')
    ports=skill['ports'];used=[]
    for key in ('iq','http','control'):
        port=ports[key]
        if key=='control' and port is None:continue
        _number(port,'skill port',1024,integer=True)
        if port>65535:raise ValueError('Invalid skill port')
        used.append(port)
    if len(set(used))!=len(used):raise ValueError('Skill ports must differ')
    if skill['kind']=='music' and (len(radios['sites'])!=2 or any(len(s['channels'])<3 for s in radios['sites'])):
        raise ValueError('Bundled MUSIC skill requires two sites, each with >=3 coherent ULA channels; choose a compatible custom skill for other layouts')
    if skill['kind']=='music' and any(max((b-a for a,b in zip(site['element_offsets_m'],site['element_offsets_m'][1:])),default=0)>299792458./carrier/2*(1+1e-10) for site in radios['sites']):
        raise ValueError('MUSIC array spacing must be at most half a wavelength at the declared carrier')
    config['_directory']=str(root)
    return config


def snapshot(directory,destination):
    """Copy one complete input package atomically; retain previously generated runs."""
    source=Path(directory).resolve();target=Path(destination).resolve()
    if target.is_relative_to(source):raise ValueError('Run/snapshot directory must be outside the scenario input directory')
    load(source)
    for path in source.rglob('*'):
        if path.is_symlink() and not path.resolve().is_relative_to(source):raise ValueError('Scenario symlink escapes input package: '+str(path))
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.scenario-',dir=target.parent) as temp:
        staging=Path(temp)/'input';shutil.copytree(source,staging,ignore=shutil.ignore_patterns('.git','__pycache__'))
        previous=Path(temp)/'previous'
        if target.exists():target.rename(previous)
        try:staging.rename(target)
        except BaseException:
            if previous.exists():previous.rename(target)
            raise
    return load(target)


def fingerprints(directory):
    root=Path(directory);result={}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            digest=sha256()
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
            result[str(path.relative_to(root))]=digest.hexdigest()
    return result
