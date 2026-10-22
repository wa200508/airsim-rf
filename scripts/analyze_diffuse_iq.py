"""Check moving multipath recordings against a bounded-memory CPU CW reference.

Traced gains/delays/Dopplers are shared inputs, not independent scattering truth.
No path identity or constant path count is assumed across channel snapshots.
I/Q working memory scales with one window; channel and recording metadata are
still loaded in full.
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
    metadata=json.loads((directory/'capture/rx0.sigmf-meta').read_text())
    if len(rows)!=len(channels) or len(rows)<2:
        raise ValueError('At least two aligned channel windows required')
    if p['noise_enabled']:
        raise ValueError('Deterministic reference requires receiver noise disabled')
    sos=np.asarray(p['filter_sos']);state=np.zeros((len(sos),2),dtype=complex)
    counts=[row['samples_per_receiver'] for row in rows]
    starts=np.cumsum(counts)[:-1]
    edge_error=np.zeros(len(starts));edge_energy=np.zeros(len(starts))
    whole_error=whole_energy=boundary_error=boundary_energy=code_energy=0.
    max_code_error=0.;matching_components=0;offset=0
    for index,(row,channel,block) in enumerate(zip(rows,channels,iter_iq_blocks(directory/'capture'),strict=True)):
        count=len(block.samples)
        if count!=counts[index]:
            raise ValueError('Recording block length differs from manifest')
        scale=metadata['captures'][index]['airsim_rf:volts_per_count']
        signal=cw_reference(channel,count,fs,p['tone_hz'],
            (row['sim_time_ns']-p['waveform_origin_ns'])*1e-9,
            np.sqrt(p['impedance_ohm']*p['transmit_power_w']))
        reference,state=sosfilt(sos,signal,zi=state)
        observed=block.samples.copy()
        if inject_reset and index>=len(rows)//2:observed*=-1
        error_power=abs(observed-reference)**2
        reference_power=abs(reference)**2
        whole_error+=float(np.sum(error_power));whole_energy+=float(np.sum(reference_power))
        # Intersect every boundary neighborhood with this block. This preserves
        # overlapping neighborhoods even when windows contain fewer than 256 samples.
        first=np.searchsorted(starts,offset-128,side='right')
        last=np.searchsorted(starts,offset+count+128,side='left')
        for edge_index in range(first,last):
            boundary=starts[edge_index]
            region=slice(max(0,int(boundary)-128-offset),min(count,int(boundary)+128-offset))
            error_sum=float(np.sum(error_power[region]));energy_sum=float(np.sum(reference_power[region]))
            boundary_error+=error_sum;boundary_energy+=energy_sum
            edge_error[edge_index]+=error_sum;edge_energy[edge_index]+=energy_sum
        components=lambda x:np.column_stack((x.real,x.imag))
        max_code_error=max(max_code_error,float(np.max(abs(components(observed-reference)/scale))))
        quantized=np.clip(np.rint(components(reference)/scale),-2048,2047)
        observed_codes=np.rint(components(observed)/scale)
        matching_components+=int(np.count_nonzero(quantized==observed_codes))
        code_energy+=float(np.sum(reference_power/scale**2))
        offset+=count
    if whole_energy==0 or boundary_energy==0:
        raise ValueError('Reference has no energy for relative-error qualification')
    whole=float(np.sqrt(whole_error/whole_energy))
    boundary=float(np.sqrt(boundary_error/boundary_energy))
    checks={'whole_iq_nrmse_below_1percent':whole<.01,
            'boundary_iq_nrmse_below_1percent':boundary<.01}
    transitions=[]
    for index in range(len(starts)):
        before=len(channels[index]['delay_s']);after=len(channels[index+1]['delay_s'])
        if before!=after:
            transitions.append({'sample_offset':int(starts[index]),
                'paths_before':before,'paths_after':after,
                'iq_nrmse':float(np.sqrt(edge_error[index]/edge_energy[index])) if edge_energy[index]>0 else None})
    if transitions:
        checks['each_path_count_transition_iq_nrmse_below_1percent']=all(
            t['iq_nrmse'] is not None and t['iq_nrmse']<.01 for t in transitions)
    if inject_reset:
        checks={'injected_reset_rejected_whole_recording':whole>=.01,
                'injected_reset_rejected_at_boundaries':boundary>=.01}
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,
        'scope':'injected pi reset rejection' if inject_reset else 'moving multipath CW rendering, continuous filtering and ADC readback; shared traced paths',
        'whole_iq_nrmse':whole,'boundary_iq_nrmse':boundary,
        'path_count_transitions':transitions,
        'max_component_error_adc_counts':max_code_error,
        'fraction_components_matching_reference_adc_codes':matching_components/(2*offset),
        'reference_rms_adc_counts':float(np.sqrt(code_energy/offset)),
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
