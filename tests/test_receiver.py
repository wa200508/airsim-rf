from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from airsim_rf import ReceiverConfig, RFReceiver, synthesize_voltage
from airsim_rf.bridge import AirSimRFBridge, mount_kinematics


def test_fractional_delays_multipath_and_loaded_voltage():
    cfg = ReceiverConfig(num_samples=64, transmit_power_w=0.25)
    time_ns, frequency = 123456789, 12345.0
    delays = np.array([0.37 / cfg.sample_rate_hz, 2.13 / cfg.sample_rate_hz, -1])
    gains = np.array([0.1 + 0.2j, -0.15j, 100 + 100j])
    a = np.repeat(gains[:, None], cfg.num_samples, axis=1)
    block = synthesize_voltage(a, delays, lambda t: np.exp(2j * np.pi * frequency * t),
                               sim_time_ns=time_ns, config=cfg)
    t = time_ns * 1e-9 + np.arange(cfg.num_samples) / cfg.sample_rate_hz
    effective_gain = np.sum(gains[:2] * np.exp(-2j * np.pi * frequency * delays[:2]))
    expected = np.sqrt(cfg.impedance_ohm * cfg.transmit_power_w) * effective_gain * np.exp(2j * np.pi * frequency * t)
    np.testing.assert_allclose(block.iq_volts, expected, rtol=1e-6)
    assert block.sim_time_ns == time_ns


def test_coherent_paths_can_cancel():
    cfg = ReceiverConfig(num_samples=32)
    block = synthesize_voltage(np.array([[1j]*32, [-1j]*32]), [0, 0], np.ones_like,
                               sim_time_ns=0, config=cfg)
    assert np.count_nonzero(block.iq_volts) == 0


def test_compact_multipath_doppler_is_continuous_across_pulses():
    cfg = ReceiverConfig(num_samples=128, sample_rate_hz=100000, transmit_power_w=0.25)
    gains = np.array([0.1+0.2j, -0.15j])
    delays = np.array([0.7e-6, 3.2e-6])
    doppler = np.array([-123.0, 245.0])
    tone = 20000.0
    for epoch_ns in (27000000, 28280000):
        epoch = epoch_ns*1e-9
        channel_at_pulse = gains*np.exp(2j*np.pi*doppler*epoch)
        block = synthesize_voltage(channel_at_pulse, delays,
            lambda t: np.exp(2j*np.pi*tone*t), sim_time_ns=epoch_ns,
            config=cfg, doppler_hz=doppler)
        t = epoch + np.arange(cfg.num_samples)/cfg.sample_rate_hz
        expected = np.sqrt(cfg.impedance_ohm*cfg.transmit_power_w)*sum(
            g*np.exp(-2j*np.pi*tone*delay)*np.exp(2j*np.pi*(tone+fd)*t)
            for g, delay, fd in zip(gains, delays, doppler))
        np.testing.assert_allclose(block.iq_volts, expected, rtol=2e-6, atol=1e-7)


def test_empty_channel_and_thermal_noise_power():
    cfg = ReceiverConfig(num_samples=100000, noise_enabled=True, noise_figure_db=6)
    # waveform should not be called on an empty channel.
    block = synthesize_voltage(np.empty((0, cfg.num_samples)), [], None,
                               sim_time_ns=0, config=cfg, rng=np.random.default_rng(12))
    expected = 1.380649e-23 * cfg.temperature_k * cfg.sample_rate_hz * 10**0.6
    actual = np.mean(np.abs(block.iq_volts)**2) / cfg.impedance_ohm
    assert actual == pytest.approx(expected, rel=0.015)
    assert abs(np.mean(block.iq_volts)) < np.std(block.iq_volts) * 0.01


def test_sionna_free_space_loss_absolute_delay_carrier_phase_and_doppler(tmp_path):
    from sionna.rt import PlanarArray, Receiver, Transmitter, load_scene
    scene = load_scene()
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.add(Transmitter("tx", position=[0, 0, 10]))
    scene.add(Receiver("rx", position=[100, 0, 10], velocity=[10, 0, 0]))
    cfg = ReceiverConfig(num_samples=512)
    receiver = RFReceiver(scene, cfg, max_depth=0)
    block = receiver.capture(np.ones_like, 0)
    wavelength = 299792458.0 / cfg.carrier_hz
    expected_power = cfg.transmit_power_w * (wavelength / (4 * np.pi * 100))**2
    measured = np.mean(np.abs(block.iq_volts)**2) / cfg.impedance_ohm
    assert measured == pytest.approx(expected_power, rel=1e-5)
    assert block.path_delays_s[0] == pytest.approx(100 / 299792458.0, rel=1e-6)
    expected_phase = np.exp(-2j * np.pi * cfg.carrier_hz * block.path_delays_s[0])
    np.testing.assert_allclose(block.iq_volts[0] / abs(block.iq_volts[0]), expected_phase, atol=0.002)
    measured_doppler = np.angle(np.mean(block.iq_volts[1:] * block.iq_volts[:-1].conj())) * cfg.sample_rate_hz / (2*np.pi)
    assert measured_doppler == pytest.approx(-10 / wavelength, abs=0.02)
    filename = tmp_path / "iq.npz"
    block.save(filename)
    with np.load(filename) as data:
        np.testing.assert_array_equal(data["iq_volts"], block.iq_volts)
        assert data["iq_volts"].dtype == np.complex64
        assert data["impedance_ohm"] == 50


def test_single_reflection_geometry_and_compact_moving_channel():
    from sionna.rt import PlanarArray, Receiver, Transmitter, load_scene, scene as scenes
    scene = load_scene(scenes.floor_wall)
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.add(Transmitter("tx", position=[0.5, 0.2, 2]))
    scene.add(Receiver("rx", position=[1.5, 0.2, 2], velocity=[1, 0, 0]))
    cfg = ReceiverConfig(num_samples=64)
    receiver = RFReceiver(scene, cfg)
    block = receiver.capture(np.ones_like, 0)
    # Exactly direct, wall image and floor image paths; no wall-floor bounce.
    np.testing.assert_allclose(np.sort(block.path_delays_s*299792458.0),
                               [1, 2, np.sqrt(17)], rtol=1e-5)
    paths = receiver.solver(scene, max_depth=1, samples_per_src=10000,
                            max_num_paths_per_src=1000, refraction=False, seed=42)
    a, tau = paths.cir(sampling_frequency=cfg.sample_rate_hz,
                       num_time_steps=cfg.num_samples, normalize_delays=False, out_type="numpy")
    dense_reference = synthesize_voltage(a[0, 0, 0, 0], tau[0, 0], np.ones_like,
                                         sim_time_ns=0, config=cfg)
    np.testing.assert_allclose(block.iq_volts, dense_reference.iq_volts, rtol=1e-5, atol=1e-8)


def tilted_kinematics():
    # Body rotated +90deg around y: body x points NED down-negative.
    q = Rotation.from_euler("y", np.pi/2).as_quat()
    return {"pose": {"position": {"x": 2, "y": 3, "z": -4},
                     "orientation": dict(zip(("x", "y", "z", "w"), q))},
            "twist": {"linear": {"x": 0, "y": 0, "z": 0},
                      "angular": {"x": 0, "y": 0, "z": 2}}}


def test_mount_frame_rotation_and_body_angular_lever_arm():
    position, velocity, orientation = mount_kinematics(tilted_kinematics(), [1, 0, 0])
    np.testing.assert_allclose(position, [2, -3, 5], atol=1e-12)
    np.testing.assert_allclose(velocity, [0, -2, 0], atol=1e-12)
    np.testing.assert_allclose(Rotation.from_euler("ZYX", orientation).apply([1, 0, 0]), [0, 0, 1], atol=1e-12)


def test_bridge_uses_paused_sim_time_and_rejects_racing_snapshot():
    times = iter([987654321, 987654321])
    world = SimpleNamespace(is_paused=lambda: True, get_sim_time=lambda: next(times))
    robot = SimpleNamespace(get_ground_truth_kinematics=lambda: {"kinematics": tilted_kinematics()})
    rx = SimpleNamespace()
    receiver = SimpleNamespace(capture=lambda waveform, epoch: epoch)
    bridge = AirSimRFBridge(world, robot, receiver, rx)
    assert bridge.capture(np.ones_like) == 987654321
    np.testing.assert_allclose(rx.position, [2, -3, 4])
    times = iter([1, 2])
    with pytest.raises(RuntimeError, match="advanced"):
        bridge.capture(np.ones_like)
    world.is_paused = lambda: False
    with pytest.raises(RuntimeError, match="Pause"):
        bridge.capture(np.ones_like)
