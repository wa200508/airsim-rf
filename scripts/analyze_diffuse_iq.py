"""Check moving multipath recordings against a bounded-memory CPU CW reference.

Traced gains/delays/Dopplers are shared inputs, not independent scattering truth.
No path identity or constant path count is assumed across channel snapshots.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.signal import sosfilt

from airsim_rf.recording import iter_iq_blocks


def cw_reference(channel, count, fs, tone, source_start_s, power_scale):
    """Sum all exported paths in small batches, including empty channels."""
    tau=np.asarray(channel['delay_s']);fd=np.asarray(channel['doppler_hz'])
    a=np.asarray(channel['coefficient_real'])+1j*np.asarray(channel['coefficient_imag'])
    if not (tau.shape==fd.shape==a.shape) or tau.ndim!=1:
        raise ValueError('Path arrays must be aligned vectors')
    if not all(np.isfinite(v).all() for v in (tau,fd,a)):
        raise ValueError('Path arrays must be finite')
    t=np.arange(count)/fs
    result=np.zeros(count,dtype=np.complex128)
    for start in range(0,len(a),32):
        sl=slice(start,start+32)
        result+=np.sum(a[sl,None]*np.exp(2j*np.pi*(
            tone*(source_start_s+t[None,:]-tau[sl,None])+fd[sl,None]*t[None,:])),axis=0)
    return power_scale*result


def analyze(directory, *, inject_reset=False):
    directory=Path(directory)
    manifest=json.loads((directory/'capture/manifest.json').read_text())
    channels=json.loads((directory/'channels.json').read_text())
    p=manifest['provenance'];rows=manifest['rows'];fs=manifest['sample_rate_hz']
    if len(rows)!=len(channels) or len(rows)<2:
        raise ValueError('At least two aligned channel windows required')
    if p['noise_enabled']:
        raise ValueError('Deterministic reference requires receiver noise disabled')
    sos=np.asarray(p['filter_sos']);state=np.zeros((len(sos),2),dtype=complex)
    references=[];observations=[];counts=[]
    for index,(row,channel,block) in enumerate(zip(rows,channels,iter_iq_blocks(directory/'capture'))):
        count=len(block.samples);counts.append(count)
        signal=cw_reference(channel,count,fs,p['tone_hz'],
            (row['sim_time_ns']-p['waveform_origin_ns'])*1e-9,
            np.sqrt(p['impedance_ohm']*p['transmit_power_w']))
        reference,state=sosfilt(sos,signal,zi=state)
        references.append(reference)
        observed=block.samples.copy()
        if inject_reset and index>=len(rows)//2:observed*=-1
        observations.append(observed)
    reference=np.concatenate(references);observed=np.concatenate(observations)
    starts=np.cumsum(counts)[:-1]
    edges=np.concatenate([np.arange(max(0,s-128),min(len(reference),s+128)) for s in starts])
    def error(indices):
        energy=np.linalg.norm(reference[indices])
        if energy==0:raise ValueError('Reference has no energy for relative-error qualification')
        return float(np.linalg.norm(observed[indices]-reference[indices])/energy)
    whole=error(slice(None));boundary=error(edges)
    checks={'whole_iq_nrmse_below_1percent':whole<.01,
            'boundary_iq_nrmse_below_1percent':boundary<.01}
    if inject_reset:
        checks={'injected_reset_rejected_whole_recording':whole>=.01,
                'injected_reset_rejected_at_boundaries':boundary>=.01}
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,
        'scope':'injected pi reset rejection' if inject_reset else 'moving multipath CW rendering, continuous filtering and ADC readback; shared traced paths',
        'whole_iq_nrmse':whole,'boundary_iq_nrmse':boundary,
        'path_count_min':min(len(c['delay_s']) for c in channels),
        'path_count_max':max(len(c['delay_s']) for c in channels),
        'complex_samples':sum(counts),'signal_seconds_per_receiver':sum(counts)/fs,
        'diffuse_mode':p.get('diffuse_mode'),'boundary_samples_each_side':128}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--negative-control',action='store_true')
    args=parser.parse_args();result=analyze(args.directory,inject_reset=args.negative_control)
    name='diffuse-negative-control.json' if args.negative_control else 'diffuse-iq.json'
    (args.directory/name).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if result['status']!='passed':raise SystemExit(1)
