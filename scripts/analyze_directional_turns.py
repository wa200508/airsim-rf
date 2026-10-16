"""Check rotating directional gain against an isotropic flight baseline.

The ratio cancels shared propagation and polarization factors. It does not
independently qualify the absolute polarization model or antenna calibration.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation


def gain_db(direction):
    direction=np.asarray(direction,dtype=float)
    direction=direction/np.linalg.norm(direction)
    theta=np.degrees(np.arccos(np.clip(direction[2],-1,1)))
    phi=np.degrees(np.arctan2(direction[1],direction[0]))
    vertical=min(12*((theta-90)/65)**2,30)
    horizontal=min(12*(phi/65)**2,30)
    return 8-min(vertical+horizontal,30)


def local_direction(direction, state):
    q=state['pose']['orientation']
    body_to_ned=Rotation.from_quat([q[k] for k in ('x','y','z','w')]).as_matrix()
    d=np.diag([1.,-1.,-1.])
    return d@body_to_ned.T@d@direction


def analyze(directory, baseline):
    directory,baseline=Path(directory),Path(baseline)
    def load(root,name):return json.loads((root/name).read_text())
    manifest=load(directory,'capture/manifest.json');base_manifest=load(baseline,'capture/manifest.json')
    trajectory=load(directory,'trajectory.json');base_trajectory=load(baseline,'trajectory.json')
    channels=load(directory,'channels.json');base_channels=load(baseline,'channels.json')
    positions=load(directory,'motion.json')['rows']
    if manifest['status']!='complete' or base_manifest['status']!='complete':raise ValueError('Complete recordings required')
    if manifest['provenance']['antenna']!='tr38901 V' or base_manifest['provenance']['antenna'] not in ('iso V','isotropic V'):
        raise ValueError('Directional and isotropic baselines required')
    # Exact deterministic replay is required before taking gain ratios.
    if trajectory!=base_trajectory or len(channels)!=len(base_channels) or len(channels)!=len(positions):
        raise ValueError('Baseline and directional flight poses/timestamps must match exactly')
    rows=[]
    for i,(channel,reference,position) in enumerate(zip(channels,base_channels,positions)):
        if len(channel['delay_s'])!=1 or len(reference['delay_s'])!=1:raise ValueError('One direct path required')
        if not np.allclose(channel['delay_s'],reference['delay_s'],rtol=0,atol=1e-12):raise ValueError('Path delays differ')
        coefficient=complex(channel['coefficient_real'][0],channel['coefficient_imag'][0])
        reference_coefficient=complex(reference['coefficient_real'][0],reference['coefficient_imag'][0])
        direction=np.array(position['rx_position_rf_m'])-position['tx_position_rf_m']
        expected=sum(gain_db(local_direction(d,trajectory[2*i+j]['kinematics']))
                     for j,d in enumerate((direction,-direction)))
        fixed=gain_db(direction)+gain_db(-direction)
        measured=20*np.log10(abs(coefficient/reference_coefficient))
        rows.append({'sim_time_ns':position['sim_time_ns'],'expected_gain_db':float(expected),
            'measured_gain_db':float(measured),'fixed_orientation_gain_db':float(fixed)})
    expected=np.array([r['expected_gain_db'] for r in rows]);measured=np.array([r['measured_gain_db'] for r in rows]);fixed=np.array([r['fixed_orientation_gain_db'] for r in rows])
    metrics={'max_gain_error_db':float(np.max(abs(expected-measured))),
        'observed_gain_change_db':float(np.ptp(measured)),
        'fixed_orientation_rms_error_db':float(np.sqrt(np.mean((fixed-measured)**2)))}
    checks={'gain_error_below_0_01dB':metrics['max_gain_error_db']<.01,
        'gain_changes_over_0_5dB':metrics['observed_gain_change_db']>.5,
        'fixed_orientation_rejected_over_0_5dB':metrics['fixed_orientation_rms_error_db']>.5}
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,'metrics':metrics,
        'scope':'direct-path directional/isotropic gain ratio under matched turning poses; shared polarization',
        'signal_seconds_per_receiver':manifest['signal_seconds_per_receiver'],'rows':rows}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path);parser.add_argument('--baseline',type=Path,required=True)
    args=parser.parse_args();result=analyze(args.directory,args.baseline)
    (args.directory/'directional-gain.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
    if result['status']!='passed':raise SystemExit(1)
