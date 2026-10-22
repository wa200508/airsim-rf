"""Audit actual rendered orbit and independently received coherent I/Q evidence."""
import argparse
import json
from pathlib import Path
import numpy as np


def audit(run,status,pause):
    producer=json.loads((run/'producer.json').read_text());skill=status['skill']
    altitude=json.loads((run/'scenario.json').read_text()).get('altitude_rf_m',160.)
    history=producer['history'];received={row['sim_time_ns']:row for row in skill['history']}
    positions=np.asarray([row['position_rf_m'] for row in history])
    angle=np.unwrap(np.arctan2(positions[:,1],positions[:,0]))
    radius=np.linalg.norm(positions[:,:2],axis=1)
    origin=producer['sim_time_ns']-round(producer['sim_elapsed_s']*1e9)
    blocks=[];visible=[];both_blocked_no_detection=[]
    for row in history:
        epoch=origin+round(row['sim_elapsed_s']*1e9)
        observed=received.get(epoch)
        if observed is None:continue
        blocks.append(observed)
        if all(row['direct_visible']):visible.append(observed)
        if not any(row['direct_visible']) and not any(observed['detected']):both_blocked_no_detection.append(observed)
    totals=producer.get('acknowledged_sample_totals',{})
    expected=producer['windows']*240000*8*8
    checks={
        'actual_flight_and_stream_complete':producer['status']=='complete' and skill['status']=='complete',
        'one_complete_left_hand_circuit':float(angle[-1]-angle[0])>=2*np.pi,
        'radius_within_10m_of_250m':bool(np.max(abs(radius-250))<10),
        'altitude_within_8m_of_command':bool(np.max(abs(positions[:,2]-altitude))<8),
        'all_coherent_windows_received':skill['complete_windows']==producer['windows']==len(history)==len(blocks),
        'all_payload_bytes_received':skill['payload_bytes']==producer['raw_payload_bytes']==expected,
        'all_eight_sample_totals_acknowledged':len(totals)==8 and all(n==producer['windows']*240000 for n in totals.values()),
        'both_blocked_and_clear_geometry_observed':bool(both_blocked_no_detection and visible),
        'transport_continued_without_successful_sensing':len(both_blocked_no_detection)>=5,
        'nontrivial_music_candidate_change':any(np.ptp([r['angles_deg'][i] for r in blocks if r['detected'][i]])>10 for i in range(2)),
        'actual_first_order_multipath_retained':any(max(row['retained_paths_per_channel'])>=2 for row in history),
        'no_reported_adc_clipping':all(row['max_clipped_component_fraction']==0 for row in history),
        'pause_holds_clock_and_payload':pause['status']=='passed' and all(pause['checks'].values()),
        'camera_frames_received':producer['camera_frames']>=30 and (run/'camera.jpg').stat().st_size>1000,
        'separate_simulator_and_cpu_skill_alive':all(status['processes'][name]['state']=='running' for name in ('sim','skill')),
        'rf_process_exited_cleanly':status['processes']['rf']['state']=='exited' and status['processes']['rf']['exit_code']==0,
    }
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,
        'metrics':{'windows':producer['windows'],'signal_seconds':producer['windows']*.12,
                   'received_payload_bytes':skill['payload_bytes'],'left_hand_angle_rad':float(angle[-1]-angle[0]),
                   'radius_min_max_m':[float(radius.min()),float(radius.max())],
                   'altitude_min_max_rf_m':[float(positions[:,2].min()),float(positions[:,2].max())],
                   'blocked_without_detection_windows':len(both_blocked_no_detection),'clear_windows':len(visible),
                   'camera_frames':producer['camera_frames']},
        'scope':'Actual ProjectAirSim Fast Physics poses and Unreal scene camera; Sionna direct/first-order specular; independent CPU Docker MUSIC skill; coherent TCP metadata extension, not native MEL conformance or real-time/hardware accuracy'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--status',type=Path,required=True);parser.add_argument('--pause',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=audit(args.run,json.loads(args.status.read_text()),json.loads(args.pause.read_text()))
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    raise SystemExit(result['status']!='passed')
