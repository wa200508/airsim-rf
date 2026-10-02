from dataclasses import replace

import numpy as np
import pytest
from scipy.signal import find_peaks

from airsim_rf.fmcw import Distance2GoLProfile, FMCWRadar, quantize_iq, range_fft, save_frame
from airsim_rf.radar import C, PointTarget


@pytest.fixture(scope="module")
def radar():
    return FMCWRadar(replace(Distance2GoLProfile(), noise_enabled=False))


def test_published_profile_and_acquisition_limits():
    p = Distance2GoLProfile()
    assert p.eirp_dbm == 14
    assert p.nominal_range_resolution_m == pytest.approx(0.749481145)
    assert p.sampled_range_resolution_m == pytest.approx(0.8782982168)
    assert p.bandwidth_hz > p.sample_rate_hz  # ADC samples already-dechirped IF.
    with pytest.raises(ValueError, match="ADC window"):
        replace(p, num_samples=256)
    with pytest.raises(ValueError, match="Nyquist"):
        replace(p, if_high_hz=50000)
    # Published -3dB corners and suppression beyond the physical passband.
    np.testing.assert_allclose(abs(p.filter_response([7000, 15000])), 1/np.sqrt(2), atol=1e-12)
    assert abs(p.filter_response(110000)[0]) < 0.01


def test_fmcw_beat_and_physical_radar_power_after_if_chain(radar):
    p = radar.profile
    target = PointTarget("target", (10, 0, 2), rcs_m2=0.1)
    capture = radar.capture([target], position_m=[0, 0, 2])
    measured_beat = np.angle(np.mean(capture.if_volts[1:]*capture.if_volts[:-1].conj()))*p.sample_rate_hz/(2*np.pi)
    expected_beat = p.slope_hz_s*(2*10/C)
    assert measured_beat == pytest.approx(expected_beat, abs=0.01)
    gain = 10**(p.antenna_gain_dbi/10)
    received_w = p.tx_power_w*gain**2*(C/p.carrier_hz)**2*target.rcs_m2/((4*np.pi)**3*10**4)
    if_gain = 10**((p.if_gain_db+p.mixer_voltage_gain_db)/20)
    expected_v2 = p.reference_impedance_ohm*received_w*if_gain**2*abs(p.filter_response(expected_beat)[0])**2
    assert np.mean(abs(capture.if_volts)**2) == pytest.approx(expected_v2, rel=1e-5)


def test_doppler_coupling_for_closing_drone(radar):
    p = radar.profile
    capture = radar.capture([PointTarget("target", (10, 0, 2), 0.1)],
                            position_m=[0, 0, 2], velocity_m_s=[0.3, 0, 0])
    doppler = 2*0.3*p.carrier_hz/C
    beat = p.slope_hz_s*2*10/C-doppler
    measured = np.angle(np.mean(capture.if_volts[1:]*capture.if_volts[:-1].conj()))*p.sample_rate_hz/(2*np.pi)
    assert capture.target_doppler_hz[0] == pytest.approx(doppler)
    assert measured == pytest.approx(beat, abs=0.01)
    ranges, profile = range_fft(capture.if_volts, p, zero_padding=8)
    assert ranges[abs(profile).argmax()] == pytest.approx(beat*C/(2*p.slope_hz_s), abs=0.06)


def test_directional_beam_and_two_way_gain(radar):
    p = radar.profile
    theta = np.radians(40)
    half_power = p.antenna_power_gain([np.cos(theta), np.sin(theta), 0])
    peak = p.antenna_power_gain([1, 0, 0])
    assert half_power/peak == pytest.approx(0.5)
    assert p.antenna_power_gain([-1, 0, 0]) == 0
    on = radar.capture([PointTarget("on", (10, 0, 2), 0.1)], position_m=[0, 0, 2])
    off = radar.capture([PointTarget("off", (10*np.cos(theta), 10*np.sin(theta), 2), 0.1)], position_m=[0, 0, 2])
    assert np.mean(abs(off.if_volts)**2)/np.mean(abs(on.if_volts)**2) == pytest.approx(0.25, rel=1e-5)


def test_adc_bias_clipping_and_quantization():
    p = Distance2GoLProfile()
    signal = np.array([-5-5j, 5+5j, 0.003-0.002j])
    codes, iq, clipped = quantize_iq(signal, p)
    assert codes.dtype == np.uint16
    np.testing.assert_array_equal(codes[:2], [[0, 0], [4095, 4095]])
    assert clipped == 4
    quantization_error = np.array([iq[2].real-signal[2].real, iq[2].imag-signal[2].imag])
    assert np.max(abs(quantization_error)) <= p.adc_full_scale_v/4095/2 + 1e-9


def test_two_target_frame_and_slow_time_motion(radar, tmp_path):
    p = radar.profile
    targets = [PointTarget("near", (10, 0, 2), 0.1), PointTarget("far", (14, 0, 2), 0.4)]
    frame = radar.capture_frame(targets, position_m=[0, 0, 2], velocity_m_s=[0.1, 0, 0],
                                sim_time_ns=1790976000000000000, num_chirps=3)
    ranges, spectrum = range_fft(frame[0].if_volts, p)
    peaks, _ = find_peaks(abs(spectrum), height=abs(spectrum).max()*0.5, distance=8)
    np.testing.assert_allclose(ranges[peaks], [10, 14], atol=0.15)
    assert frame[1].target_ranges_m[0] == pytest.approx(10-0.1*p.pri_s)
    assert frame[1].sim_time_ns-frame[0].sim_time_ns == round(p.pri_s*1e9)
    save_frame(frame, tmp_path/"frame.npz")
    with np.load(tmp_path/"frame.npz") as data:
        assert data["if_volts"].shape == (3, 128)
        assert data["adc_codes"].shape == (3, 128, 2)
        assert data["target_names"].tolist() == ["near", "far"]


def test_frame_phase_is_coherent_and_independent_of_clock_epoch(radar):
    p = radar.profile
    target = PointTarget("near", (10, 0, 2), 0.1)
    frame = radar.capture_frame([target], position_m=[0, 0, 2], velocity_m_s=[0.1, 0, 0], num_chirps=3)
    phase_step = np.angle(np.mean(frame[1].if_volts*frame[0].if_volts.conj()))
    expected = -2*np.pi*(2*0.1*p.carrier_hz/C)*p.pri_s
    assert phase_step == pytest.approx(expected, abs=0.015)
    large_epoch = radar.capture([target], position_m=[0, 0, 2], velocity_m_s=[0.1, 0, 0],
                                sim_time_ns=1790976000000000000)
    np.testing.assert_array_equal(large_epoch.if_volts, frame[0].if_volts)


def test_batched_target_mapping_matches_sum_of_individual_echoes(radar):
    near = PointTarget("near", (10, 0, 2), 0.1)
    far = PointTarget("far", (14, 0, 2), 0.4)
    hidden = PointTarget("behind", (-10, 0, 2), 0.1)
    zero = PointTarget("zero", (12, 0, 2), 0)
    individual = (radar.capture([near], position_m=[0, 0, 2]).if_volts
                  + radar.capture([far], position_m=[0, 0, 2]).if_volts)
    batch = radar.capture([hidden, near, zero, far], position_m=[0, 0, 2])
    np.testing.assert_allclose(batch.if_volts, individual, atol=1e-8)
    assert batch.target_names == ("behind", "near", "zero", "far")
    assert len(radar.probes) == 2
    empty = radar.capture([hidden, zero], position_m=[0, 0, 2])
    assert not np.any(empty.if_volts)
    assert len(radar.probes) == 0
