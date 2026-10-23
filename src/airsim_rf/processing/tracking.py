"""Receiver-only bearing fusion and constant-velocity tracking."""
from importlib import metadata
import numpy as np
from .music import C,estimate_bearing,read_arrays

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



def track_windows(windows, config, *, reverse_first_array=False):
    """Estimate from ADC data; never read emitter truth or propagation exports."""
    try:
        from filterpy.kalman import KalmanFilter
        from filterpy.common import Q_discrete_white_noise
    except ImportError as error:
        raise RuntimeError('Tracking requires the tracking extra: pip install airsim-rf[tracking]') from error
    sites=config['sites'];names=[name for site in sites for name in site['channels']]
    rows=[];tracker=None;previous=None
    centers=np.asarray([site['center_rf_m'][:2] for site in sites])
    for blocks in windows:
        if len(blocks)!=len(names) or [b.receiver for b in blocks]!=names:raise ValueError('Ordered receiver channel IDs required')
        first=blocks[0]
        if any((b.timestamp_ns,b.sample_start,len(b.samples),b.sample_rate_hz,b.carrier_hz)!=
               (first.timestamp_ns,first.sample_start,len(first.samples),first.sample_rate_hz,first.carrier_hz) for b in blocks):
            raise ValueError('Array channels must share epochs, sample offsets, counts, rates and carrier')
        if first.carrier_hz!=config['carrier_hz'] or first.sample_rate_hz!=config['sample_rate_hz']:
            raise ValueError('Array carrier/sample rate differs from receiver configuration')
        epoch=first.timestamp_ns+round(.5*len(first.samples)/first.sample_rate_hz*1e9)
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
        rows.append({'timestamp_ns':epoch,'bearings':bearings,
                     'fused_position_rf_xy_m':None if position is None else position.tolist(),
                     'track_position_rf_xy_m':None if tracker is None else tracker.x[[0,2]].tolist(),
                     'track_velocity_rf_xy_m_s':None if tracker is None else tracker.x[[1,3]].tolist()})
        previous=epoch
    if not rows:
        raise ValueError('A nonempty complete synchronized recording is required')
    return {'status':'processed','scope':'single emitter, two coherent ULAs, known near-zero elevation and front hemisphere; 2D MUSIC/bearing-fusion/CV tracking',
            'consumer_inputs':['completed ADC I/Q','receiver array geometry and calibration','timestamps'],
            'doa_py':metadata.version('doa-py'),'filterpy':metadata.version('filterpy'),
            'reverse_first_array':reverse_first_array,'rows':rows}
