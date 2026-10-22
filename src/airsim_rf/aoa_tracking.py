"""Independent recorded-I/Q consumer: doa_py MUSIC, bearing fusion and FilterPy.

Only receiver geometry/calibration and completed ADC recordings enter consume().
Emitter poses, waveforms and traced paths belong exclusively to the evaluator.
"""
from importlib import metadata
import json
from pathlib import Path

import numpy as np

from .recording import iter_iq_blocks

C = 299792458.


class PhysicalULA:
    """doa_py steering protocol, using actual metre offsets and exact RF c.

    Broadside is local +x, elements lie on local +y, angles increase towards +y.
    A front-hemisphere prior resolves the ULA's front/back ambiguity.
    """
    def __init__(self, offsets_m):
        self.offsets=np.asarray(offsets_m,float)

    def steering_vector(self, signal_fre, angles, unit='deg'):
        angle=np.deg2rad(angles) if unit=='deg' else np.asarray(angles)
        return np.exp(2j*np.pi*signal_fre/C*self.offsets[:,None]*np.sin(angle)[None,:])


def estimate_bearing(samples, offsets_m, carrier_hz, *, grid_deg=None):
    """Use an external MUSIC implementation; return angle and rank-one contrast."""
    try:
        from doa_py.algorithm import music
    except ImportError as error:
        raise RuntimeError('AoA consumer requires the tracking extra: pip install airsim-rf[tracking]') from error
    samples=np.asarray(samples)
    offsets=np.asarray(offsets_m,float)
    if (samples.ndim!=2 or samples.shape[0]<3 or samples.shape[1]<64
            or offsets.shape!=(samples.shape[0],) or not np.isfinite(samples).all()
            or not np.isfinite(offsets).all() or np.any(np.diff(offsets)<=0)):
        raise ValueError('MUSIC needs finite ordered ULA channels and at least 64 simultaneous samples')
    if not np.isfinite(carrier_hz) or carrier_hz<=0 or np.max(np.diff(offsets))>C/carrier_hz/2*(1+1e-10):
        raise ValueError('Positive carrier and at most half-wavelength element spacing required')
    grid=np.linspace(-70,70,2801) if grid_deg is None else np.asarray(grid_deg,float)
    covariance=np.cov(samples)
    eigen=np.linalg.eigvalsh(covariance)
    contrast=float(max(eigen[-1],0)/max(eigen[-2],np.finfo(float).tiny))
    if eigen[-1]<=0 or contrast<5:
        return {'detected':False,'angle_deg':None,'eigenvalue_ratio':contrast}
    spectrum=music(samples,num_signal=1,array=PhysicalULA(offsets),signal_fre=carrier_hz,angle_grids=grid)
    if np.any(np.isnan(spectrum)):
        raise ValueError('MUSIC produced a NaN spectrum')
    index=int(np.argmax(spectrum))
    return {'detected':index not in (0,len(grid)-1),'angle_deg':float(grid[index]),
            'eigenvalue_ratio':contrast}


def intersect_bearings(centers_xy, angles_rad):
    """Two forward rays, rejecting nearly parallel and backward intersections."""
    centers=np.asarray(centers_xy,float);angles=np.asarray(angles_rad,float)
    if centers.shape!=(2,2) or angles.shape!=(2,) or not np.isfinite(centers).all() or not np.isfinite(angles).all():
        raise ValueError('Two finite 2D receiver centers and bearings required')
    directions=np.column_stack((np.cos(angles),np.sin(angles)))
    matrix=np.column_stack((directions[0],-directions[1]))
    if abs(np.linalg.det(matrix))<np.sin(np.deg2rad(5)):
        return None
    lengths=np.linalg.solve(matrix,centers[1]-centers[0])
    return centers[0]+lengths[0]*directions[0] if np.all(lengths>0) else None


def _position_covariance(centers, angles, angular_std_rad):
    epsilon=1e-5;derivatives=[]
    for i in range(2):
        delta=np.zeros(2);delta[i]=epsilon
        plus=intersect_bearings(centers,angles+delta)
        minus=intersect_bearings(centers,angles-delta)
        if plus is None or minus is None:
            return np.eye(2)*1e4
        derivatives.append((plus-minus)/(2*epsilon))
    jacobian=np.column_stack(derivatives)
    return jacobian @ jacobian.T*angular_std_rad**2+np.eye(2)*1e-6


def read_arrays(path):
    config=json.loads(Path(path).read_text())
    if config.get('schema_version')!=1 or len(config.get('sites',[]))!=2:
        raise ValueError('Array schema v1 requires exactly two sites for this single-emitter 2D example')
    names=[]
    for site in config['sites']:
        offsets=np.asarray(site['element_offsets_m'],float)
        center=np.asarray(site['center_rf_m'],float)
        if (offsets.shape!=(len(site['channels']),) or len(offsets)<3 or not np.isfinite(offsets).all()
                or np.any(np.diff(offsets)<=0) or center.shape!=(3,) or not np.isfinite(center).all()
                or not np.isfinite(site['yaw_rad'])):
            raise ValueError('Each site requires ordered element offsets, finite center and yaw')
        gains=np.asarray(site['calibration_complex'],float)
        if gains.shape!=(len(offsets),2) or not np.isfinite(gains).all() or np.any(np.linalg.norm(gains,axis=1)==0):
            raise ValueError('Each channel requires a finite nonzero complex calibration gain [real,imag]')
        names.extend(site['channels'])
    if len(set(names))!=len(names):
        raise ValueError('Array channel IDs must be unique across sites')
    return config


def consume(recording, arrays_path, *, reverse_first_array=False):
    """Estimate from ADC data; never read emitter truth or propagation exports."""
    try:
        from filterpy.kalman import KalmanFilter
        from filterpy.common import Q_discrete_white_noise
    except ImportError as error:
        raise RuntimeError('Tracking requires the tracking extra: pip install airsim-rf[tracking]') from error
    config=read_arrays(arrays_path)
    sites=config['sites'];names=[name for site in sites for name in site['channels']]
    streams=[iter_iq_blocks(recording,name) for name in names]
    rows=[];tracker=None;previous=None
    centers=np.asarray([site['center_rf_m'][:2] for site in sites])
    for blocks in zip(*streams,strict=True):
        first=blocks[0]
        if any((b.sim_time_ns,b.sample_start,len(b.samples),b.sample_rate_hz,b.carrier_hz)!=
               (first.sim_time_ns,first.sample_start,len(first.samples),first.sample_rate_hz,first.carrier_hz) for b in blocks):
            raise ValueError('Array channels must share epochs, sample offsets, counts, rates and carrier')
        if first.carrier_hz!=config['carrier_hz'] or first.sample_rate_hz!=config['sample_rate_hz']:
            raise ValueError('Array carrier/sample rate differs from recording metadata')
        epoch=first.sim_time_ns+round(.5*len(first.samples)/first.sample_rate_hz*1e9)
        bearings=[];offset=0
        for index,site in enumerate(sites):
            count=len(site['channels'])
            values=np.stack([block.samples for block in blocks[offset:offset+count]])
            offset+=count
            calibration=np.asarray(site['calibration_complex'])
            values=values/(calibration[:,0]+1j*calibration[:,1])[:,None]
            if reverse_first_array and index==0:
                values=values[::-1]
            result=estimate_bearing(values,site['element_offsets_m'],config['carrier_hz'])
            result['site_id']=site['id']
            result['global_angle_rad']=None if not result['detected'] else float(np.deg2rad(result['angle_deg'])+site['yaw_rad'])
            bearings.append(result)
        angles=[b['global_angle_rad'] for b in bearings]
        position=intersect_bearings(centers,angles) if all(a is not None for a in angles) else None
        if tracker is not None:
            dt=(epoch-previous)*1e-9
            tracker.F=np.array([[1,dt,0,0],[0,1,0,0],[0,0,1,dt],[0,0,0,1.]])
            tracker.Q=Q_discrete_white_noise(2,dt=dt,var=4.,block_size=2)
            tracker.predict()
        if position is not None:
            if tracker is None:
                tracker=KalmanFilter(dim_x=4,dim_z=2)
                tracker.x=np.array([position[0],0.,position[1],0.])
                tracker.P=np.diag([16.,100.,16.,100.])
                tracker.H=np.array([[1,0,0,0],[0,0,1,0.]])
            tracker.update(position,R=_position_covariance(centers,np.asarray(angles),np.deg2rad(.5)))
        rows.append({'sim_time_ns':epoch,'bearings':bearings,
                     'fused_position_rf_xy_m':None if position is None else position.tolist(),
                     'track_position_rf_xy_m':None if tracker is None else tracker.x[[0,2]].tolist(),
                     'track_velocity_rf_xy_m_s':None if tracker is None else tracker.x[[1,3]].tolist()})
        previous=epoch
    if not rows:
        raise ValueError('A nonempty complete synchronized recording is required')
    return {'status':'processed','scope':'single emitter, two coherent ULAs, known near-zero elevation and front hemisphere; 2D MUSIC/bearing-fusion/CV tracking',
            'consumer_inputs':['completed ADC I/Q','receiver array geometry and calibration','timestamps'],
            'truth_or_paths_used':False,'doa_py':metadata.version('doa-py'),'filterpy':metadata.version('filterpy'),
            'reverse_first_array':reverse_first_array,'rows':rows}


def score(result, truth_path):
    """Held-out evaluation is separate from consume(); fixed baseline gates."""
    truth=json.loads(Path(truth_path).read_text())
    rows=result['rows'];frames=truth['frames']
    if len(rows)!=len(frames) or any(a['sim_time_ns']!=b['sim_time_ns'] for a,b in zip(rows,frames)):
        raise ValueError('Consumer estimates and held-out truth epochs must match')
    angular=[];position=[];velocity=[];fused=0;retained=0
    start=rows[0]['sim_time_ns']
    for row,frame in zip(rows,frames):
        for bearing,angle in zip(row['bearings'],frame['bearings_rad'],strict=True):
            if bearing['global_angle_rad'] is not None:
                delta=bearing['global_angle_rad']-angle
                angular.append(np.rad2deg(np.arctan2(np.sin(delta),np.cos(delta))))
        fused+=row['fused_position_rf_xy_m'] is not None
        if row['sim_time_ns']-start>=240_000_000:
            retained+=1
            if row['track_position_rf_xy_m'] is not None:
                position.append(np.linalg.norm(np.asarray(row['track_position_rf_xy_m'])-frame['position_rf_m'][:2]))
                velocity.append(np.linalg.norm(np.asarray(row['track_velocity_rf_xy_m_s'])-frame['velocity_rf_m_s'][:2]))
    rms=lambda values:float(np.sqrt(np.mean(np.asarray(values)**2))) if values else None
    metrics={'bearing_rmse_deg':rms(angular),'track_position_rmse_m':rms(position),
             'track_velocity_rmse_m_s':rms(velocity),'bearing_detection_fraction':len(angular)/(2*len(rows)),
             'fused_measurement_fraction':fused/len(rows),'post_settling_track_fraction':len(position)/retained if retained else 0.}
    checks={'bearing_rmse_below_1deg':metrics['bearing_rmse_deg'] is not None and metrics['bearing_rmse_deg']<1.,
            'track_position_rmse_below_half_meter':metrics['track_position_rmse_m'] is not None and metrics['track_position_rmse_m']<.5,
            'track_velocity_rmse_below_2m_s':metrics['track_velocity_rmse_m_s'] is not None and metrics['track_velocity_rmse_m_s']<2.,
            'bearing_detection_above_95percent':metrics['bearing_detection_fraction']>=.95,
            'fusion_above_95percent':metrics['fused_measurement_fraction']>=.95,
            'track_coverage_above_95percent':metrics['post_settling_track_fraction']>=.95}
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,'metrics':metrics,
            'scope':'held-out single-emitter 2D trajectory scoring; first 0.240 s excluded from track-error metrics',
            'receiver_truth_used_only_for_scoring':True}
