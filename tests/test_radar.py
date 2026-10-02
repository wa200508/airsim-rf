from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.signal import find_peaks

from airsim_rf.bridge import AirSimRadarBridge
from airsim_rf.radar import C, PointTarget, PointTargetRadar, RadarConfig, range_compress


@pytest.fixture(scope="module")
def radar():
    return PointTargetRadar()


def test_lfm_sweep_gating_and_invalid_configuration():
    cfg = RadarConfig()
    t = np.arange(50) / cfg.sample_rate_hz
    chirp = cfg.chirp(t)
    instantaneous_frequency = np.angle(chirp[1:] * chirp[:-1].conj()) * cfg.sample_rate_hz / (2*np.pi)
    expected = -cfg.bandwidth_hz/2 + cfg.bandwidth_hz/cfg.pulse_width_s * (t[:-1]+0.5/cfg.sample_rate_hz)
    np.testing.assert_allclose(instantaneous_frequency, expected, atol=1e-6)
    assert np.all(cfg.chirp([-1e-9, cfg.pulse_width_s, 10]) == 0)
    with pytest.raises(ValueError, match="bandwidth"):
        replace(cfg, bandwidth_hz=cfg.sample_rate_hz)
    with pytest.raises(ValueError, match="shorter"):
        replace(cfg, pulse_width_s=cfg.pri_s)
    with pytest.raises(ValueError, match="integer"):
        replace(cfg, pri_s=cfg.pri_s+0.5/cfg.sample_rate_hz)


def test_radar_equation_round_trip_phase_and_delay(radar):
    target = PointTarget("target", (300, 0, 50), rcs_m2=3)
    result = radar.capture([target], position_m=[0, 0, 50])
    cfg = radar.config
    wavelength = C / cfg.carrier_hz
    expected_power = cfg.peak_power_w * wavelength**2 * target.rcs_m2 / ((4*np.pi)**3 * 300**4)
    t = np.arange(cfg.num_samples)/cfg.sample_rate_hz
    tau = float(result.block.path_delays_s[0])
    assert tau == pytest.approx(2*300/C, rel=1e-6)
    mask = (t > tau + 2/cfg.sample_rate_hz) & (t < tau+cfg.pulse_width_s-2/cfg.sample_rate_hz)
    measured_power = np.mean(np.abs(result.block.iq_volts[mask])**2) / cfg.impedance_ohm
    assert measured_power == pytest.approx(expected_power, rel=1e-5)
    stripped = result.block.iq_volts[mask] / cfg.chirp(t[mask]-tau)
    measured_phase = stripped[0] / abs(stripped[0])
    expected_phase = np.exp(-2j*np.pi*cfg.carrier_hz*tau)
    np.testing.assert_allclose(measured_phase, expected_phase, atol=0.008)


def test_two_targets_range_compression_and_voltage_rcs_scaling(radar, tmp_path):
    targets = [PointTarget("near", (300, 0, 50), 1), PointTarget("far", (600, 0, 50), 16)]
    capture = radar.capture(targets, position_m=[0, 0, 50])
    ranges, profile = range_compress(capture.block.iq_volts, radar.config)
    peaks, _ = find_peaks(abs(profile), height=abs(profile).max()*0.7, distance=5)
    np.testing.assert_allclose(ranges[peaks], [300, 600], atol=C/(2*radar.config.sample_rate_hz))
    # Quadrupled voltage from sqrt(16) offsets the 4x R^-2 voltage loss.
    assert abs(profile[peaks[0]])/abs(profile[peaks[1]]) == pytest.approx(1, rel=0.03)
    capture.save(tmp_path / "radar.npz")
    with np.load(tmp_path / "radar.npz") as data:
        assert data["iq_volts"].dtype == np.complex64
        assert data["target_names"].tolist() == ["near", "far"]
        np.testing.assert_array_equal(data["range_m"], ranges)
        np.testing.assert_allclose(data["range_profile_volts"], profile)


def test_two_way_doppler_for_receding_drone_and_moving_target(radar):
    target = PointTarget("moving", (300, 0, 50), velocity_m_s=(5, 0, 0))
    result = radar.capture([target], position_m=[0, 0, 50], velocity_m_s=[-10, 0, 0])
    cfg = radar.config
    t = np.arange(cfg.num_samples) / cfg.sample_rate_hz
    tau = result.block.path_delays_s[0]
    mask = (t > tau+2/cfg.sample_rate_hz) & (t < tau+cfg.pulse_width_s-2/cfg.sample_rate_hz)
    stripped = result.block.iq_volts[mask] / cfg.chirp(t[mask]-tau)
    doppler = np.angle(np.mean(stripped[1:] * stripped[:-1].conj())) * cfg.sample_rate_hz/(2*np.pi)
    expected = -2*15*cfg.carrier_hz/C
    assert doppler == pytest.approx(expected, abs=0.2)
    assert result.target_doppler_hz[0] == pytest.approx(expected)


def test_pulse_precision_at_unix_scale_epoch_and_transmit_blanking(radar):
    targets = [PointTarget("near", (300, 0, 50))]
    a = radar.capture(targets, position_m=[0, 0, 50], sim_time_ns=0)
    b = radar.capture(targets, position_m=[0, 0, 50], sim_time_ns=1790976000000000000)
    np.testing.assert_array_equal(a.block.iq_volts, b.block.iq_volts)
    assert b.block.sim_time_ns == 1790976000000000000
    assert np.count_nonzero(b.block.iq_volts[:50]) == 0
    empty = radar.capture([], position_m=[0, 0, 50])
    assert np.count_nonzero(empty.block.iq_volts) == 0
    with pytest.raises(ValueError, match="coincide"):
        radar.capture([PointTarget("bad", (0, 0, 50))], position_m=[0, 0, 50])


def test_drone_bridge_forwards_antenna_pose_and_epoch():
    kin = {"pose": {"position": {"x": 0, "y": 2, "z": -50},
                    "orientation": {"w": 1, "x": 0, "y": 0, "z": 0}},
           "twist": {"linear": {"x": 20, "y": 0, "z": 0},
                     "angular": {"x": 0, "y": 0, "z": 0}}}
    world = SimpleNamespace(is_paused=lambda: True, get_sim_time=lambda: 123456789)
    drone = SimpleNamespace(get_ground_truth_kinematics=lambda: {"kinematics": kin})
    radar = SimpleNamespace(capture=lambda targets, **kwargs: (targets, kwargs))
    bridge = AirSimRadarBridge(world, drone, radar, offset_body_m=[0.5, 0, 0])
    targets, args = bridge.capture(["target"])
    assert targets == ["target"]
    np.testing.assert_allclose(args["position_m"], [0.5, -2, 50])
    np.testing.assert_allclose(args["velocity_m_s"], [20, 0, 0])
    assert args["sim_time_ns"] == 123456789
