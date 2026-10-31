"""Transmission-history qualification, preserving this branch's channel model.

Reference synthesis consumes the same traced complex channel; this qualifies
late-echo rendering rather than independently calibrating Sionna's path phase.
"""
from dataclasses import replace
from importlib.util import find_spec
import numpy as np
import pytest
from airsim_rf.fmcw import Distance2GoLProfile, FMCWRadar
from airsim_rf.radar import C, PointTarget


def profile():
    return replace(Distance2GoLProfile(), bandwidth_hz=1e6, chirp_duration_s=32e-6,
        pri_s=40e-6, sample_rate_hz=2e6, num_samples=32, adc_start_s=0.,
        if_low_hz=1000., if_high_hz=900000., noise_enabled=False)


def epoch(p,i,origin=0):
    return origin+round(i*p.pri_s*1e9)


def reference(p,transmission,receive_ns):
    fast=p.adc_start_s+np.arange(p.num_samples)/p.sample_rate_hz
    elapsed=(receive_ns-transmission.start_ns)*1e-9+fast
    result=np.zeros(p.num_samples,complex)
    for delay,fd,gain in zip(transmission.delays,transmission.dopplers,transmission.voltage_gain):
        emitted=elapsed-delay
        tolerance=1e-9/p.sample_rate_hz
        emitted[np.abs(emitted)<tolerance]=0.
        emitted[np.abs(emitted-p.chirp_duration_s)<tolerance]=p.chirp_duration_s
        tx_phase=np.pi*p.slope_hz_s*emitted**2-np.pi*p.bandwidth_hz*emitted
        lo_phase=np.pi*p.slope_hz_s*fast**2-np.pi*p.bandwidth_hz*fast
        beat=p.slope_hz_s*(delay-(receive_ns-transmission.start_ns)*1e-9)-fd
        amplitude=gain*p.filter_response(beat)[0]*10**((p.if_gain_db+p.mixer_voltage_gain_db)/20)
        result+=amplitude*np.exp(1j*(lo_phase-tx_phase-2*np.pi*fd*elapsed))*((emitted>=0)&(emitted<p.chirp_duration_s))
    return result


@pytest.mark.parametrize('origin',[0,1790976000000000000])
def test_first_pulse_arrives_in_fifth_window_and_survives_tx_off(origin):
    p=profile();radar=FMCWRadar(p)
    target=PointTarget('late',(C*(4*p.pri_s+6.25/p.sample_rate_hz)/2,0.,0.),1e14,(3.,0.,0.))
    emissions=[];captures=[]
    for i in range(5):
        captures.append(radar.capture([target],position_m=[0,0,0],sim_time_ns=epoch(p,i,origin)))
        emissions.append(radar._transmissions[-1])
    assert all(not np.any(c.if_volts) for c in captures[:4])
    np.testing.assert_allclose(captures[4].if_volts,reference(p,emissions[0],epoch(p,4,origin)),rtol=2e-6,atol=1e-10)
    assert not np.any(captures[4].if_volts[:7]) and np.any(captures[4].if_volts[7:])
    assert radar.last_render_diagnostics['pending_transmissions']==5
    for i in range(5,9):
        cap=radar.capture([],position_m=[0,0,0],sim_time_ns=epoch(p,i,origin),transmit_enabled=False)
        np.testing.assert_allclose(cap.if_volts,reference(p,emissions[i-4],epoch(p,i,origin)),rtol=2e-6,atol=1e-10)
    cap=radar.capture([],position_m=[0,0,0],sim_time_ns=epoch(p,9,origin),transmit_enabled=False)
    assert not np.any(cap.if_volts) and radar.last_render_diagnostics['pending_echoes']==0


def test_old_and_current_returns_add_with_independent_path_dopplers():
    p=profile();radar=FMCWRadar(p);emissions=[]
    near=PointTarget('near',(C*2.25/p.sample_rate_hz/2,0.,0.),2e5,(-2.,0.,0.))
    far=PointTarget('far',(C*(4*p.pri_s+6.25/p.sample_rate_hz)/2,0.,0.),1e14,(3.,0.,0.))
    for i in range(5):
        cap=radar.capture([near,far],position_m=[0,0,0],sim_time_ns=epoch(p,i))
        emissions.append(radar._transmissions[-1])
    expected=sum((reference(p,tx,epoch(p,4)) for tx in emissions),start=np.zeros(p.num_samples,complex))
    np.testing.assert_allclose(cap.if_volts,expected,rtol=2e-6,atol=1e-10)
    assert radar.last_render_diagnostics['echo_terms']==2
    expected_fd=-2*np.array([-2.,3.])*p.carrier_hz/C
    np.testing.assert_allclose(emissions[-1].dopplers,expected_fd,rtol=2e-6)


def test_paths_expire_individually_and_storage_does_not_grow_with_run_length():
    p=profile();radar=FMCWRadar(p)
    targets=[PointTarget(str(i),(C*(i*p.pri_s+6.25/p.sample_rate_hz)/2,0.,0.),1e14) for i in (2,4)]
    radar.capture(targets,position_m=[0,0,0])
    radar.capture([],position_m=[0,0,0],sim_time_ns=epoch(p,3),transmit_enabled=False)
    assert radar.last_render_diagnostics['pending_echoes']==1
    radar.capture([],position_m=[0,0,0],sim_time_ns=epoch(p,5),transmit_enabled=False)
    assert radar.last_render_diagnostics['pending_transmissions']==0
    radar.reset_history()
    for i in range(40):
        radar.capture([targets[1]],position_m=[0,0,0],sim_time_ns=epoch(p,i))
        assert radar.last_render_diagnostics['pending_transmissions']<=5
        assert radar.last_render_diagnostics['pending_echoes']<=5


def test_finite_ramp_support_and_explicit_rewind():
    p=replace(profile(),num_samples=64);radar=FMCWRadar(p)
    target=PointTarget('late',(C*(4*p.pri_s-10e-6)/2,0.,0.),1e14)
    radar.capture([target],position_m=[0,0,0]);emission=radar._transmissions[0]
    with pytest.raises(ValueError,match='strictly increase'):radar.capture([],position_m=[0,0,0])
    cap=radar.capture([],position_m=[0,0,0],sim_time_ns=epoch(p,4),transmit_enabled=False)
    np.testing.assert_allclose(cap.if_volts,reference(p,emission,epoch(p,4)),rtol=2e-6,atol=1e-10)
    assert np.any(cap.if_volts[:43]) and not np.any(cap.if_volts[45:])
    assert radar.last_render_diagnostics['pending_echoes']==0
    radar.reset_history()
    assert not np.any(radar.capture([],position_m=[0,0,0],transmit_enabled=False).if_volts)


def test_pending_echoes_retain_original_tx_power_and_reject_new_ramp_shape():
    p=profile();radar=FMCWRadar(p)
    target=PointTarget('late',(C*(4*p.pri_s+6.25/p.sample_rate_hz)/2,0.,0.),1e14)
    radar.capture([target],position_m=[0,0,0]);emission=radar._transmissions[0]
    radar.profile=replace(p,bandwidth_hz=2e6)
    with pytest.raises(ValueError,match='pending'):
        radar.capture([],position_m=[0,0,0],sim_time_ns=epoch(p,1),transmit_enabled=False)
    radar.profile=replace(p,mmic_power_dbm=-20.)
    cap=radar.capture([],position_m=[0,0,0],sim_time_ns=epoch(p,4),transmit_enabled=False)
    np.testing.assert_allclose(cap.if_volts,reference(p,emission,epoch(p,4)),rtol=2e-6,atol=1e-10)


@pytest.mark.skipif(find_spec('airsim_rf.dashboard_radar') is None,
                    reason='This historical branch predates the dashboard radar adapter')
def test_dashboard_keeps_history_across_acquisition_windows():
    import sionna.rt as rt
    from airsim_rf.dashboard_radar import RadarWindowReceiver
    radio={'radar':{'profile':{'bandwidth_hz':1e6,'noise_enabled':False},'seed':42,'max_depth_per_leg':0}}
    def receiver():
        rx=RadarWindowReceiver(rt.load_scene(),radio,{'sites':[{'channels':['radar_rx0']}]})
        rx.position=np.zeros(3);rx.velocity=np.zeros(3);rx.orientation=np.zeros(3)
        p=rx.radar.profile
        rx.targets=[PointTarget('late',(C*(4*p.pri_s+p.adc_start_s+.75/p.sample_rate_hz)/2,0.,0.),1e17)]
        return rx
    rx=receiver();caps=[rx.capture(i*40000,num_samples=400)['radar_rx0'] for i in range(5)]
    assert all(not np.any(c.input_iq_volts) for c in caps[:4])
    assert np.any(caps[4].input_iq_volts)
    grouped=receiver().capture(0,num_samples=2000)['radar_rx0']
    np.testing.assert_array_equal(grouped.adc_iq_volts,np.concatenate([c.adc_iq_volts for c in caps]))
