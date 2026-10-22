"""Independent analytic reference checks, including changing/empty paths."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
import json
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location('diffuse_iq',Path(__file__).resolve().parents[1]/'scripts/analyze_diffuse_iq.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_cw_reference_crosses_batch_boundary():
    n=35;count=100;fs=1000.;tone=123.;start=.75;scale=2.
    tau=np.arange(n)*1e-6;fd=np.arange(n)*.1
    gains=np.exp(1j*np.arange(n))
    channel={'delay_s':tau,'doppler_hz':fd,'coefficient_real':gains.real,'coefficient_imag':gains.imag}
    t=np.arange(count)/fs
    expected=sum(scale*g*np.exp(2j*np.pi*(tone*(start+t-delay)+doppler*t))
                 for g,delay,doppler in zip(gains,tau,fd))
    np.testing.assert_allclose(module.cw_reference(channel,count,fs,tone,start,scale),expected,atol=1e-11)


def test_empty_channel_and_malformed_arrays():
    channel={k:[] for k in ('delay_s','doppler_hz','coefficient_real','coefficient_imag')}
    np.testing.assert_array_equal(module.cw_reference(channel,5,1000,123,0,1),np.zeros(5))
    channel['delay_s']=[0]
    with pytest.raises(ValueError,match='aligned'):module.cw_reference(channel,5,1000,123,0,1)


@pytest.mark.parametrize('inject_reset',[False,True])
def test_streaming_statistics_match_materialized_reference(tmp_path,monkeypatch,inject_reset):
    counts=[40,170,90];fs=1000.;scales=[.001,.002,.003]
    starts=np.r_[0,np.cumsum(counts)];tone=123.
    channel={'delay_s':[.0001],'doppler_hz':[.5],
             'coefficient_real':[.4],'coefficient_imag':[.2]}
    rows=[{'samples_per_receiver':n,'sim_time_ns':int(start*1e9/fs)}
          for n,start in zip(counts,starts)]
    provenance={'noise_enabled':False,'filter_sos':[[.25,.125,0,1,-.625,0]],
                'tone_hz':tone,'waveform_origin_ns':0,'impedance_ohm':1,'transmit_power_w':1}
    capture=tmp_path/'capture';capture.mkdir()
    (capture/'manifest.json').write_text(json.dumps({'rows':rows,'sample_rate_hz':fs,'provenance':provenance}))
    (tmp_path/'channels.json').write_text(json.dumps([channel]*3))
    (capture/'rx0.sigmf-meta').write_text(json.dumps({'captures':[{'airsim_rf:volts_per_count':s} for s in scales]}))
    raw=[module.cw_reference(channel,n,fs,tone,start/fs,1) for n,start in zip(counts,starts)]
    filtered=module.sosfilt(np.asarray(provenance['filter_sos']),np.concatenate(raw))
    references=np.split(filtered,starts[1:-1])
    observed=[(np.rint(r.real/s)+1j*np.rint(r.imag/s))*s for r,s in zip(references,scales)]
    monkeypatch.setattr(module,'iter_iq_blocks',lambda _:iter(SimpleNamespace(samples=o) for o in observed))
    result=module.analyze(tmp_path,inject_reset=inject_reset)
    ref=np.concatenate(references)
    obs=np.concatenate([(-o if inject_reset and i>=1 else o) for i,o in enumerate(observed)])
    scale=np.repeat(scales,counts)
    edges=np.concatenate([np.arange(max(0,s-128),min(len(ref),s+128)) for s in starts[1:-1]])
    assert result['whole_iq_nrmse']==pytest.approx(np.linalg.norm(obs-ref)/np.linalg.norm(ref))
    assert result['boundary_iq_nrmse']==pytest.approx(np.linalg.norm((obs-ref)[edges])/np.linalg.norm(ref[edges]))
    assert result['reference_rms_adc_counts']==pytest.approx(np.sqrt(np.mean(abs(ref/scale)**2)))
    delta=obs-ref
    assert result['max_component_error_adc_counts']==pytest.approx(max(np.max(abs(delta.real)/scale),np.max(abs(delta.imag)/scale)))
    assert result['status']=='passed'


@pytest.mark.parametrize('corrupt_transition',[False,True])
def test_transition_error_cannot_hide_in_aggregate_metrics(tmp_path,monkeypatch,corrupt_transition):
    count=1024;windows=200;fs=1024.;scale=.001
    channel={'delay_s':[0.],'doppler_hz':[0.],
             'coefficient_real':[.4],'coefficient_imag':[.2]}
    empty={k:[] for k in channel}
    channels=[empty if i==1 else channel for i in range(windows)]
    rows=[{'samples_per_receiver':count,'sim_time_ns':i*1_000_000_000} for i in range(windows)]
    provenance={'noise_enabled':False,'filter_sos':[[.25,.125,0,1,-.625,0]],
                'tone_hz':123.,'waveform_origin_ns':0,'impedance_ohm':1,'transmit_power_w':1}
    capture=tmp_path/'capture';capture.mkdir()
    (capture/'manifest.json').write_text(json.dumps({'rows':rows,'sample_rate_hz':fs,'provenance':provenance}))
    (tmp_path/'channels.json').write_text(json.dumps(channels))
    (capture/'rx0.sigmf-meta').write_text(json.dumps({'captures':[{'airsim_rf:volts_per_count':scale}]*windows}))
    raw=np.concatenate([module.cw_reference(c,count,fs,123.,i,1.) for i,c in enumerate(channels)])
    reference=module.sosfilt(np.asarray(provenance['filter_sos']),raw)
    quantized=(np.rint(reference.real/scale)+1j*np.rint(reference.imag/scale))*scale
    if corrupt_transition:quantized[count-1]*=-1
    blocks=np.split(quantized,windows)
    monkeypatch.setattr(module,'iter_iq_blocks',lambda _:iter(SimpleNamespace(samples=b) for b in blocks))
    result=module.analyze(tmp_path)
    assert result['checks']['whole_iq_nrmse_below_1percent']
    assert result['checks']['boundary_iq_nrmse_below_1percent']
    assert len(result['path_count_transitions'])==2
    assert result['checks']['each_path_count_transition_iq_nrmse_below_1percent']==(not corrupt_transition)
    assert result['status']==('failed' if corrupt_transition else 'passed')
