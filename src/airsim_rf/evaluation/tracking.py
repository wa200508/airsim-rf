"""Held-out tracking evaluation; source truth is used only here."""
import json
from pathlib import Path
import numpy as np

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
