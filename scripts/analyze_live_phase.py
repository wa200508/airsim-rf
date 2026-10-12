"""Check saved live captures against geometric paths and an analytic CW sum.

The signal reference reuses traced complex gains: it independently checks signal
rendering/filter continuity, not Fresnel amplitudes. Geometric delays and Doppler
are checked separately against the flat-ground image construction.
"""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np
from scipy.signal import sosfilt

from airsim_rf.bridge import mount_kinematics

C=299792458.


def wrap(value):
    return np.angle(np.exp(1j*value))


def phase_fit(block, fs, tone_hz, offset):
    margin=round(.001*fs);i=np.arange(margin,len(block)-margin)
    return np.polyfit(i/fs,np.unwrap(np.angle(block[i]*np.exp(-2j*np.pi*tone_hz*(i+offset)/fs))),1)


def geometry(tx, rx, reflection=False):
    pt,vt,_=mount_kinematics(tx);pr,vr,_=mount_kinematics(rx)
    if reflection:
        pr=pr.copy();vr=vr.copy();pr[2]*=-1;vr[2]*=-1
    direction=pr-pt;length=np.linalg.norm(direction)
    return length,float(np.dot(vt-vr,direction/length))


def analyze(directory):
    directory=Path(directory)
    read=lambda name:json.loads((directory/name).read_text())
    manifest=read('capture/manifest.json');channels=read('channels.json');trajectory=read('trajectory.json')
    meta=read('capture/rx0.sigmf-meta');p=manifest['provenance'];fs=manifest['sample_rate_hz'];tone=p['tone_hz'];fc=p['carrier_hz']
    rows=manifest['rows'];expected_paths=1+p['max_depth']
    if manifest['status']!='complete' or len(channels)!=len(rows) or len(trajectory)!=2*len(rows):
        raise ValueError('Complete, aligned channels/trajectory/recording required')
    codes=np.fromfile(directory/'capture/rx0.sigmf-data',dtype='<i2').reshape(-1,2)
    iq=codes[:,0]+1j*codes[:,1]
    offset=0;references=[];observations=[];geometry_errors=[];fits=[];boundaries=[];previous=None
    for index,(row,channel) in enumerate(zip(rows,channels)):
        if len(channel['delay_s'])!=expected_paths:
            raise ValueError(f'Expected {expected_paths} paths at every snapshot')
        order=np.argsort(channel['delay_s'])
        tau=np.array(channel['delay_s'])[order];fd=np.array(channel['doppler_hz'])[order]
        a=(np.array(channel['coefficient_real'])+1j*np.array(channel['coefficient_imag']))[order]
        geometric=[geometry(trajectory[2*index]['kinematics'],trajectory[2*index+1]['kinematics'],j==1) for j in range(expected_paths)]
        lengths=np.array([g[0] for g in geometric]);velocities=np.array([g[1] for g in geometric])
        geometry_errors.append({'length_error_m':(tau*C-lengths).tolist(),'doppler_error_hz':(fd-fc/C*velocities).tolist()})
        count=row['samples_per_receiver'];t=np.arange(count)/fs
        source_time=(row['sim_time_ns']-p['waveform_origin_ns'])*1e-9+t
        reference=np.sqrt(p['impedance_ohm']*p['transmit_power_w'])*np.sum(
            a[:,None]*np.exp(2j*np.pi*(tone*(source_time[None,:]-tau[:,None])+fd[:,None]*t[None,:])),axis=0)
        references.append(reference)
        block=iq[offset:offset+count];observations.append(block*meta['captures'][index]['airsim_rf:volts_per_count'])
        if expected_paths==1: fits.append(phase_fit(block,fs,tone,offset))
        if previous is not None:
            pa,ptau,pfd,plen,ptime,pduration=previous;dt=(row['sim_time_ns']-ptime)*1e-9
            # Endpoint coefficient phase includes the carrier path length; the
            # frozen envelope delay adds a small tone-frequency correction.
            measured=wrap(np.angle(a/pa)-2*np.pi*tone*(tau-ptau)-2*np.pi*pfd*dt)
            predicted=wrap(-2*np.pi*(fc+tone)*(lengths-plen)/C-2*np.pi*(fc/C*np.array(previous_velocities))*dt)
            boundary={'sim_time_ns':row['sim_time_ns'],'path_refresh_jump_rad':measured.tolist(),
                'geometry_refresh_jump_rad':predicted.tolist(),'path_phase_residual_rad':wrap(measured-predicted).tolist()}
            if expected_paths==1:
                boundary['adc_fitted_jump_rad']=float(wrap(fits[-1][1]-np.polyval(fits[-2],pduration)))
                boundary['adc_vs_geometry_residual_rad']=float(wrap(boundary['adc_fitted_jump_rad']-predicted[0]))
            boundaries.append(boundary)
        previous=(a,tau,fd,lengths,row['sim_time_ns'],count/fs);previous_velocities=velocities
        offset+=count
    if offset!=len(iq):raise ValueError('Recording sample count disagrees with manifest')
    # One continuous filter operation: no per-window reset in this reference.
    reference=sosfilt(np.array(p['filter_sos']),np.concatenate(references));observed=np.concatenate(observations)
    nrmse=float(np.linalg.norm(observed-reference)/np.linalg.norm(reference))
    starts=np.cumsum([r['samples_per_receiver'] for r in rows])[:-1]
    edges=np.concatenate([np.arange(s-128,s+128) for s in starts])
    edge_nrmse=float(np.linalg.norm(observed[edges]-reference[edges])/np.linalg.norm(reference[edges]))
    maximum=lambda field,items:float(max(np.max(abs(np.array(r[field]))) for r in items))
    metrics={'maximum_path_length_error_m':maximum('length_error_m',geometry_errors),
        'maximum_path_doppler_error_hz':maximum('doppler_error_hz',geometry_errors),
        'maximum_path_refresh_jump_rad':maximum('path_refresh_jump_rad',boundaries),
        'maximum_path_phase_residual_rad':maximum('path_phase_residual_rad',boundaries),
        'whole_recording_iq_nrmse':nrmse,'boundary_neighborhood_iq_nrmse':edge_nrmse}
    if expected_paths==1:
        metrics['maximum_adc_fitted_jump_rad']=maximum('adc_fitted_jump_rad',boundaries)
        metrics['maximum_adc_vs_geometry_residual_rad']=maximum('adc_vs_geometry_residual_rad',boundaries)
    checks={'path_length_within_1mm':metrics['maximum_path_length_error_m']<.001,
        'path_doppler_within_1mHz':metrics['maximum_path_doppler_error_hz']<.001,
        'path_phase_residual_below_0_01rad':metrics['maximum_path_phase_residual_rad']<.01,
        'whole_iq_nrmse_below_1percent':nrmse<.01,'boundary_iq_nrmse_below_1percent':edge_nrmse<.01}
    if expected_paths==1:checks['adc_geometry_residual_below_0_01rad']=metrics['maximum_adc_vs_geometry_residual_rad']<.01
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,'metrics':metrics,
        'scope':'flat-ground path geometry and piecewise narrowband signal/filter/ADC continuity; shared traced complex gains',
        'window_ms':p['requested_window_ms'],'paths_per_snapshot':expected_paths,
        'commanded_velocity_m_s':p['commanded_north_velocity_m_s'],
        'signal_seconds_per_receiver':manifest['signal_seconds_per_receiver'],
        'wall_seconds_per_signal_second':manifest['wall_seconds_per_signal_second'],
        'boundary_neighborhood_samples_each_side':128,'boundaries':boundaries,'geometry_errors':geometry_errors}


def negative_control(directory):
    """Inject a pi phase reset into a private recording copy; require rejection."""
    directory=Path(directory)
    with tempfile.TemporaryDirectory() as temporary:
        copy=Path(temporary)/'recording';shutil.copytree(directory,copy)
        rows=json.loads((copy/'capture/manifest.json').read_text())['rows']
        split=sum(r['samples_per_receiver'] for r in rows[:len(rows)//2])
        path=copy/'capture/rx0.sigmf-data'
        codes=np.fromfile(path,dtype='<i2').reshape(-1,2)
        codes[split:]*=-1;codes.tofile(path)
        report=analyze(copy)
    detected=not report['checks']['whole_iq_nrmse_below_1percent'] and not report['checks']['boundary_iq_nrmse_below_1percent']
    return {'status':'passed' if detected else 'failed','scope':'injected pi phase reset is rejected',
        'reset_sample_offset':split,'corrupted_capture_status':report['status'],'metrics':report['metrics']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    parser.add_argument('--negative-control',action='store_true')
    args=parser.parse_args();report=(negative_control if args.negative_control else analyze)(args.directory)
    filename='negative_control.json' if args.negative_control else 'phase.json'
    (args.directory/filename).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('boundaries','geometry_errors')},indent=2))
    if report['status']!='passed':raise SystemExit(1)
