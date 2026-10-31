"""Late echoes use earlier transmissions, including through TX-off windows."""
from dataclasses import replace

import numpy as np
import pytest

from airsim_rf.fmcw import Distance2GoLProfile, FMCWRadar
from airsim_rf.radar import C, PointTarget


def profile():
    # Long ranges below are deliberate delay stress tests, not hobbyist claims.
    return replace(Distance2GoLProfile(), bandwidth_hz=1e6, chirp_duration_s=32e-6,
        pri_s=40e-6, sample_rate_hz=2e6, num_samples=32, adc_start_s=0.,
        if_low_hz=1000., if_high_hz=900000., noise_enabled=False)


def ramp_epoch(p, index, origin=0):
    return origin+round(index*p.pri_s*1e9)


def reference_echo(p, target, transmit_ns, receive_ns, weight=1.):
    """Independent TX * conj(RX), evaluated from the two chirp phases."""
    distance=np.linalg.norm(target.position_m)
    delay=2*distance/C
    fd=-2*np.dot(target.velocity_m_s,np.asarray(target.position_m)/distance)*p.carrier_hz/C
    fast=p.adc_start_s+np.arange(p.num_samples)/p.sample_rate_hz
    elapsed=(receive_ns-transmit_ns)*1e-9+fast
    emitted=elapsed-delay
    # Exact gate edges remain half-open despite floating-point subtraction.
    tolerance=1e-9/p.sample_rate_hz
    emitted[np.abs(emitted)<tolerance]=0.
    emitted[np.abs(emitted-p.chirp_duration_s)<tolerance]=p.chirp_duration_s
    transmit_phase=np.pi*p.slope_hz_s*emitted**2-np.pi*p.bandwidth_hz*emitted
    lo_phase=np.pi*p.slope_hz_s*fast**2-np.pi*p.bandwidth_hz*fast
    carrier_phase=2*np.pi*np.remainder(p.carrier_hz*delay,1.)
    phase=carrier_phase+lo_phase-transmit_phase-2*np.pi*fd*elapsed
    gain=p.antenna_power_gain(np.asarray(target.position_m)/distance)
    received_power=p.tx_power_w*gain**2*(C/p.carrier_hz)**2*target.rcs_m2/((4*np.pi)**3*distance**4)
    beat=p.slope_hz_s*(delay-(receive_ns-transmit_ns)*1e-9)-fd
    amplitude=np.sqrt(p.reference_impedance_ohm*received_power)*np.conj(weight)
    amplitude*=p.filter_response(beat)[0]*10**((p.if_gain_db+p.mixer_voltage_gain_db)/20)
    return amplitude*np.exp(1j*phase)*((emitted>=0)&(emitted<p.chirp_duration_s))


@pytest.mark.parametrize('origin',[0,1790976000000000000])
def test_first_pulse_arrives_in_fifth_window_with_fractional_delay_and_doppler(origin):
    p=profile();radar=FMCWRadar(p)
    delay=4*p.pri_s+6.25/p.sample_rate_hz
    target=PointTarget('late',(C*delay/2,0.,0.),1e14,(3.,0.,0.))
    captures=[radar.capture([target],position_m=[0,0,0],sim_time_ns=ramp_epoch(p,i,origin)) for i in range(5)]
    assert all(not np.any(c.if_volts) for c in captures[:4])
    expected=reference_echo(p,target,origin,ramp_epoch(p,4,origin))
    np.testing.assert_allclose(captures[4].if_volts,expected,rtol=2e-6,atol=1e-10)
    assert not np.any(captures[4].if_volts[:7]) and np.any(captures[4].if_volts[7:])
    assert radar.last_render_diagnostics['target_echoes']==1
    assert radar.last_render_diagnostics['pending_transmissions']==5

    # No new radiation: pulse 2 still arrives during window 6, then 3, 4, 5.
    for i in range(5,9):
        cap=radar.capture([],position_m=[0,0,0],sim_time_ns=ramp_epoch(p,i,origin),transmit_enabled=False)
        expected=reference_echo(p,target,ramp_epoch(p,i-4,origin),ramp_epoch(p,i,origin))
        np.testing.assert_allclose(cap.if_volts,expected,rtol=2e-6,atol=1e-10)
        assert radar.last_render_diagnostics['target_echoes']==1
    expired=radar.capture([],position_m=[0,0,0],sim_time_ns=ramp_epoch(p,9,origin),transmit_enabled=False)
    assert not np.any(expired.if_volts)
    assert radar.last_render_diagnostics['pending_transmissions']==0
    assert radar.last_render_diagnostics['pending_echoes']==0


def test_old_echo_and_current_echo_add_at_the_same_fast_time_samples():
    p=profile();radar=FMCWRadar(p)
    near=PointTarget('near',(C*2.25/p.sample_rate_hz/2,0.,0.),2e5)
    far=PointTarget('far',(C*(4*p.pri_s+6.25/p.sample_rate_hz)/2,0.,0.),1e14)
    for i in range(5):
        cap=radar.capture([near,far],position_m=[0,0,0],sim_time_ns=ramp_epoch(p,i))
    expected=reference_echo(p,near,ramp_epoch(p,4),ramp_epoch(p,4))+reference_echo(p,far,0,ramp_epoch(p,4))
    np.testing.assert_allclose(cap.if_volts,expected,rtol=2e-6,atol=1e-10)
    assert radar.last_render_diagnostics['target_echoes']==2


def test_expiration_discards_individual_paths_and_releases_the_last_packet():
    p=profile();radar=FMCWRadar(p)
    targets=[PointTarget(str(i),(C*(i*p.pri_s+6.25/p.sample_rate_hz)/2,0.,0.),1e14) for i in (2,4)]
    radar.capture(targets,position_m=[0,0,0])
    assert radar.last_render_diagnostics['pending_echoes']==2
    radar.capture([],position_m=[0,0,0],sim_time_ns=ramp_epoch(p,3),transmit_enabled=False)
    assert radar.last_render_diagnostics['pending_echoes']==1
    radar.capture([],position_m=[0,0,0],sim_time_ns=ramp_epoch(p,5),transmit_enabled=False)
    assert radar.last_render_diagnostics['pending_transmissions']==0


def test_history_storage_is_bounded_by_delay_rather_than_run_length():
    p=profile();radar=FMCWRadar(p)
    target=PointTarget('late',(C*(4*p.pri_s+6.25/p.sample_rate_hz)/2,0.,0.),1e14)
    for i in range(40):
        radar.capture([target],position_m=[0,0,0],sim_time_ns=ramp_epoch(p,i))
        assert radar.last_render_diagnostics['pending_echoes']<=5
        assert radar.last_render_diagnostics['pending_transmissions']<=5


def test_rewinds_are_explicit_and_pending_echoes_do_not_silently_change_waveform():
    p=profile();radar=FMCWRadar(p)
    target=PointTarget('late',(C*(4*p.pri_s+6.25/p.sample_rate_hz)/2,0.,0.),1e14)
    radar.capture([target],position_m=[0,0,0])
    with pytest.raises(ValueError,match='strictly increase'):
        radar.capture([],position_m=[0,0,0])
    radar.profile=replace(p,bandwidth_hz=2e6)
    with pytest.raises(ValueError,match='pending'):
        radar.capture([],position_m=[0,0,0],sim_time_ns=ramp_epoch(p,1),transmit_enabled=False)
    radar.reset_history()
    cap=radar.capture([],position_m=[0,0,0],transmit_enabled=False)
    assert not np.any(cap.if_volts) and radar.last_render_diagnostics['pending_echoes']==0


def test_delayed_echo_ends_at_transmitted_ramp_end_instead_of_extending_forever():
    p=replace(profile(),num_samples=64)
    radar=FMCWRadar(p)
    # First echo arrives 10 us before window 5 and ends 22 us into it.
    target=PointTarget('late',(C*(4*p.pri_s-10e-6)/2,0.,0.),1e14)
    radar.capture([target],position_m=[0,0,0])
    cap=radar.capture([],position_m=[0,0,0],sim_time_ns=ramp_epoch(p,4),transmit_enabled=False)
    expected=reference_echo(p,target,0,ramp_epoch(p,4))
    np.testing.assert_allclose(cap.if_volts,expected,rtol=2e-6,atol=1e-10)
    assert np.any(cap.if_volts[:44]) and not np.any(cap.if_volts[44:])
    assert radar.last_render_diagnostics['pending_echoes']==0


def test_dashboard_windows_preserve_late_echoes_and_lossless_iq_archive(tmp_path):
    """Production adapter, real mesh visibility, ADC gates and saved samples."""
    import sionna.rt as rt
    from airsim_rf.dashboard_radar import RadarWindowReceiver
    from airsim_rf.fmcw import quantize_iq
    from airsim_rf.sample_recording import SampleRecordingWriter, iter_recorded_windows
    from airsim_rf.sample_stream import SampleBlock
    from airsim_rf.scenario_definition import load

    config=load('mmwave-radar');radio=config['radios'];mode=config['skill']['mode_config']
    mode['waveform']['bandwidth_hz']=1e6
    radio['radar']['max_range_m']=30000.
    radio['radar']['clutter']['enabled']=False
    radio['radar']['profile']['noise_enabled']=False
    arrays={'sample_rate_hz':10e6,'carrier_hz':77e9,'sites':[{'channels':['radar_rx0']}],
        'acquisition':{**{k:mode['waveform'][k] for k in ('pri_s','bandwidth_hz','chirp_duration_s')},
                       **{k:mode['receiver'][k] for k in ('num_samples','adc_start_s')}}}
    delay=4*mode['waveform']['pri_s']+mode['receiver']['adc_start_s']+.75/arrays['sample_rate_hz']
    target=PointTarget('late',(C*delay/2,0.,0.),1e17)

    def receiver():
        rx=RadarWindowReceiver(rt.load_scene(),radio,arrays)
        rx.position=np.zeros(3);rx.velocity=np.zeros(3);rx.orientation=np.zeros(3);rx.targets=[target]
        rx.control.configure(mode);rx.control.set_state({'transmit':True,'receive':True})
        return rx

    rx=receiver();writer=SampleRecordingWriter(tmp_path/'iq',arrays);captures=[]
    for i in range(5):
        cap=rx.capture(i*40000,num_samples=400)['radar_rx0'];captures.append(cap)
        writer.write_window([SampleBlock('radar_rx0',cap.adc_iq_volts,i*400,i*40000,10e6,77e9,cap.clipped_component_fraction)])
    writer.close()
    assert all(not np.any(c.input_iq_volts) for c in captures[:4])
    p=rx.radar.profile;expected=reference_echo(p,target,0,160000)
    np.testing.assert_allclose(captures[4].input_iq_volts[30:286],expected,rtol=2e-6,atol=1e-10)
    _,expected_adc,_=quantize_iq(expected,p)
    np.testing.assert_array_equal(captures[4].adc_iq_volts[30:286],expected_adc)
    assert not np.any(captures[4].adc_iq_volts[:30]) and not np.any(captures[4].adc_iq_volts[286:])
    restored=list(iter_recorded_windows(tmp_path/'iq'))
    assert len(restored)==5
    for saved,cap in zip(restored,captures):assert saved[0].samples.tobytes()==cap.adc_iq_volts.tobytes()

    # A single acquisition containing five chirps agrees with five separate calls.
    grouped=receiver().capture(0,num_samples=2000)['radar_rx0']
    np.testing.assert_array_equal(grouped.adc_iq_volts,np.concatenate([c.adc_iq_volts for c in captures]))
    rx.control.set_state({'transmit':False,'receive':True})
    off=rx.capture(200000,num_samples=400)['radar_rx0']
    assert np.any(off.input_iq_volts)  # Pulse 2 is still in flight.
    expired=rx.capture(360000,num_samples=400)['radar_rx0']
    assert not np.any(expired.input_iq_volts)
    assert rx.radar.last_render_diagnostics['pending_echoes']==0
