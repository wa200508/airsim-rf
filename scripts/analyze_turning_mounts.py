"""Compare offset-mount paths with independently transformed recorded poses.

Finite differences of pose-derived mount positions check angular lever-arm
velocity without reusing bridge.mount_kinematics or reported angular velocity.
"""
import argparse
import json
from pathlib import Path
import numpy as np

C=299792458.


def mount_position(message, offset):
    pose=message['pose'];q=pose['orientation']
    xyz=np.array([q[k] for k in 'xyz']);w=q['w']
    norm=np.sqrt(w*w+xyz@xyz);xyz=xyz/norm;w=w/norm
    offset=np.asarray(offset)
    rotated=offset+2*w*np.cross(xyz,offset)+2*np.cross(xyz,np.cross(xyz,offset))
    return (np.array([pose['position'][k] for k in 'xyz'])+rotated)*[1,-1,-1]


def analyze(directory):
    directory=Path(directory)
    read=lambda name:json.loads((directory/name).read_text())
    manifest=read('capture/manifest.json');trajectory=read('trajectory.json');channels=read('channels.json');motion=read('motion.json')
    p=manifest['provenance'];mounts=p['mounts_body_m'];rows=manifest['rows']
    if not p.get('turning_mounts') or len(rows)<3 or len(trajectory)!=2*len(rows) or len(channels)!=len(rows):
        raise ValueError('Aligned turning-mount capture required')
    time=np.array([(r['sim_time_ns']-rows[0]['sim_time_ns'])*1e-9 for r in rows])
    positions={};velocity_errors={};heading_changes={}
    for index,name in enumerate(('tx0','rx0')):
        positions[name]=np.array([mount_position(r['kinematics'],mounts[name]) for r in trajectory[index::2]])
        derivative=np.gradient(positions[name],time,axis=0,edge_order=2)
        reported=np.array([r['tx_velocity_rf_m_s' if index==0 else 'rx_velocity_rf_m_s'] for r in motion['rows']])
        velocity_errors[name]=float(np.max(np.linalg.norm(derivative[1:-1]-reported[1:-1],axis=1)))
        # The actual mount's horizontal direction of travel must change.
        heading=np.unwrap(np.arctan2(derivative[:,1],derivative[:,0]))
        heading_changes[name]=float(abs(heading[-2]-heading[1]))
    ranges=np.linalg.norm(positions['rx0']-positions['tx0'],axis=1)
    expected_doppler=-np.gradient(ranges,time,edge_order=2)*p['carrier_hz']/C
    if any(len(c['delay_s'])!=1 for c in channels):raise ValueError('Exactly one direct path required')
    lengths=np.array([c['delay_s'][0]*C for c in channels])
    doppler=np.array([c['doppler_hz'][0] for c in channels])
    centers={name:np.array([mount_position(r['kinematics'],[0,0,0]) for r in trajectory[index::2]])
             for index,name in enumerate(('tx0','rx0'))}
    center_ranges=np.linalg.norm(centers['rx0']-centers['tx0'],axis=1)
    metrics={'max_mount_velocity_error_m_s':velocity_errors,'heading_change_rad':heading_changes,
        'max_path_length_error_m':float(np.max(abs(lengths-ranges))),
        'max_doppler_finite_difference_error_hz':float(np.max(abs(doppler[1:-1]-expected_doppler[1:-1]))),
        'minimum_error_if_offsets_ignored_m':float(np.min(abs(lengths-center_ranges)))}
    checks={'each_heading_changes_over_0_1rad':all(v>.1 for v in heading_changes.values()),
        'mount_velocity_within_0_05m_s':all(v<.05 for v in velocity_errors.values()),
        'path_length_within_1mm':metrics['max_path_length_error_m']<.001,
        'doppler_within_0_15Hz':metrics['max_doppler_finite_difference_error_hz']<.15,
        'ignoring_mounts_rejected_at_1mm':metrics['minimum_error_if_offsets_ignored_m']>.001}
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,'metrics':metrics,
        'scope':'actual turning pose/mount positions, finite-difference velocity and direct path geometry; interior time samples',
        'signal_seconds_per_receiver':manifest['signal_seconds_per_receiver']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    args=parser.parse_args();result=analyze(args.directory)
    (args.directory/'turning-mounts.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if result['status']!='passed':raise SystemExit(1)
