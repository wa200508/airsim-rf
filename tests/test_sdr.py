"""Independent link-budget, superposition, clock and sampled-front-end checks."""
import numpy as np
import pytest
from scipy.signal import sosfreqz

from airsim_rf.sdr import PlutoSDRProfile, RadioClock, SDREmitter, SDRNetworkReceiver, quantize_iq


def free_space_scene(tx_positions, rx_positions):
    import sionna.rt as rt
    scene = rt.load_scene()
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    for i, position in enumerate(tx_positions):
        scene.add(rt.Transmitter(f'tx{i}', position=position))
    for i, position in enumerate(rx_positions):
        scene.add(rt.Receiver(f'rx{i}', position=position))
    return scene


def tone(frequency):
    return lambda t: np.exp(2j*np.pi*frequency*t)


def test_actual_sionna_many_to_many_friis_and_separate_signal_powers():
    tx = np.array([[0, 0, 10], [0, 30, 10]])
    rx = np.array([[100, 0, 10], [150, 0, 10]])
    powers = [1e-3, 2e-4]
    frequencies = [100000., -200000.]
    scene = free_space_scene(tx.tolist(), rx.tolist())
    profile = PlutoSDRProfile(noise_enabled=False)
    emitters = {f'tx{i}': SDREmitter(tone(f), power, baseband_frequency_bounds_hz=(f, f))
                for i, (f, power) in enumerate(zip(frequencies, powers))}
    receiver = SDRNetworkReceiver(scene, emitters, profile, max_depth=0)
    captures = receiver.capture(100000000)
    assert set(captures) == {'rx0', 'rx1'}
    wavelength = 299792458./profile.carrier_hz
    _, response = sosfreqz(receiver.sos, worN=2*np.pi*np.abs(frequencies)/profile.sample_rate_hz)
    for ri, cap in enumerate(captures.values()):
        for ti in range(2):
            distance = np.linalg.norm(rx[ri]-tx[ti])
            expected = powers[ti]*(wavelength/(4*np.pi*distance))**2*abs(response[ti])**2
            assert cap.link_power_w[f'tx{ti}'] == pytest.approx(expected, rel=2e-5)
            assert cap.retained_paths[f'tx{ti}'] == 1
        # Superposition of different tones approaches the sum of link powers.
        measured = np.mean(np.abs(cap.input_iq_volts)**2)/profile.impedance_ohm
        assert measured == pytest.approx(sum(cap.link_power_w.values()), rel=.001)
        assert cap.adc_codes.shape == (4096, 2)
        assert cap.clipped_component_fraction == 0


def test_emitters_sum_coherently_before_quantization():
    scene = free_space_scene([[0, 0, 10]]*2, [[100, 0, 10]])
    emitters = {'tx0': SDREmitter(tone(100000)), 'tx1': SDREmitter(tone(100000), clock=RadioClock(0, np.pi))}
    receiver = SDRNetworkReceiver(scene, emitters, PlutoSDRProfile(noise_enabled=False), max_depth=0)
    cap = receiver.capture(0)['rx0']
    assert min(cap.link_power_w.values()) > 0
    assert np.max(np.abs(cap.input_iq_volts)) < 1e-10
    assert not np.any(cap.adc_codes)


def test_independent_radio_reference_affects_lo_and_sampling():
    scene = free_space_scene([[0, 0, 10]], [[100, 0, 10]])
    tx_clock, rx_clock = RadioClock(10, .4), RadioClock(-20, .8)
    profile = PlutoSDRProfile(noise_enabled=False)
    f = 80000.
    receiver = SDRNetworkReceiver(scene, {'tx0': SDREmitter(tone(f), clock=tx_clock)}, profile,
                                 clocks={'rx0': rx_clock}, max_depth=0)
    cap = receiver.capture(123456789)['rx0']
    observed = np.angle(np.mean(cap.input_iq_volts[1:]*cap.input_iq_volts[:-1].conj()))*profile.sample_rate_hz/(2*np.pi)
    # 30 ppm relative reference error contributes 27,450 Hz at 915 MHz.
    expected = (f*1.000010 + 27450.)/.999980
    assert observed == pytest.approx(expected, abs=.03)
    assert cap.actual_sample_rate_hz == pytest.approx(1999960.)


def test_receiver_noise_is_added_once_and_matches_filtered_thermal_budget():
    profile = PlutoSDRProfile(noise_figure_db=7.)
    captures = []
    for count in (1, 2):
        scene = free_space_scene([[0, 0, 10]]*count, [[100, 0, 10]])
        emitters = {f'tx{i}': SDREmitter(tone(100000), transmit_power_w=0.) for i in range(count)}
        receiver = SDRNetworkReceiver(scene, emitters, profile, max_depth=0, seed=87)
        captures.append(receiver.capture(0, num_samples=100000)['rx0'])
    np.testing.assert_array_equal(captures[0].input_iq_volts, captures[1].input_iq_volts)
    measured = np.mean(np.abs(captures[0].input_iq_volts)**2)/profile.impedance_ohm
    expected = 1.380649e-23*290*captures[0].noise_bandwidth_hz*10**.7
    assert measured == pytest.approx(expected, rel=.02)
    assert captures[0].thermal_noise_power_w == pytest.approx(expected)


def test_adc_resolution_clipping_and_input_reference():
    full_scale = np.sqrt(50e-6)  # -30 dBm into 50 ohms.
    values = np.array([0j, .5*full_scale+.25j*full_scale, 2*full_scale-2j*full_scale])
    codes, reconstructed, step, clipping = quantize_iq(values, full_scale_dbm=-30.)
    np.testing.assert_array_equal(codes, [[0, 0], [1024, 512], [2047, -2048]])
    assert step == pytest.approx(full_scale/2048)
    assert clipping == pytest.approx(2/6)
    np.testing.assert_allclose(reconstructed[:2], values[:2], rtol=1e-7)
    weak = np.array([full_scale/1024+0j])
    assert quantize_iq(weak, full_scale_dbm=-30., bits=8)[0][0, 0] == 0
    assert quantize_iq(weak, full_scale_dbm=-30., bits=12)[0][0, 0] == 2


def test_off_band_input_is_rejected_instead_of_silently_aliasing():
    scene = free_space_scene([[0, 0, 10]], [[100, 0, 10]])
    with pytest.raises(ValueError, match='Nyquist'):
        SDRNetworkReceiver(scene, {'tx0': SDREmitter(tone(2e6), baseband_frequency_bounds_hz=(2e6, 2e6))}, max_depth=0)
    with pytest.raises(ValueError, match='published Pluto range'):
        PlutoSDRProfile(carrier_hz=24.125e9)
    with pytest.raises(ValueError, match='published Pluto range'):
        PlutoSDRProfile(rf_bandwidth_hz=200e6)


@pytest.mark.parametrize('mode', ['first-order-scattering', 'single-bounce'])
def test_terrain_capture_has_scene_paths_and_finite_adc(mode):
    import sionna.rt as rt
    from pathlib import Path
    scene = rt.load_scene(str(Path(__file__).resolve().parents[1]/'benchmarks/scenes/terrain.xml'))
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='hw_dipole', polarization='V')
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='hw_dipole', polarization='V')
    scene.add(rt.Transmitter('tx0', position=[-30, -10, 14]))
    scene.add(rt.Receiver('rx0', position=[30, -50, 20]))
    receiver = SDRNetworkReceiver(scene, {'tx0': SDREmitter(tone(150e3))},
                                 path_solver=mode, samples_per_link=128)
    cap = receiver.capture(0, num_samples=1024)['rx0']
    assert cap.retained_paths['tx0'] > 1
    assert np.isfinite(cap.input_iq_volts).all()
    assert np.isfinite(cap.adc_iq_volts).all()


def test_airsim_network_bridge_uses_one_paused_snapshot_and_mounts():
    from types import SimpleNamespace
    from airsim_rf.sdr_bridge import AirSimSDRBridge
    kinematics = {'pose': {'position': {'x': 2, 'y': 3, 'z': -10},
                          'orientation': {'w': 1, 'x': 0, 'y': 0, 'z': 0}},
                  'twist': {'linear': {'x': 1, 'y': 2, 'z': 3},
                            'angular': {'x': 0, 'y': 0, 'z': 0}}}
    radios = {'tx': SimpleNamespace(), 'rx': SimpleNamespace()}
    scene = SimpleNamespace(transmitters={'tx': radios['tx']}, receivers={'rx': radios['rx']})
    world = SimpleNamespace(is_paused=lambda: True, get_sim_time=lambda: 123456789)
    robots = {name: SimpleNamespace(get_ground_truth_kinematics=lambda: {'kinematics': kinematics})
              for name in radios}
    receiver = SimpleNamespace(scene=scene, capture=lambda t, **kw: (t, kw))
    bridge = AirSimSDRBridge(world, robots, receiver, mounts_body_m={'rx': [1, 0, 0]})
    assert bridge.capture(num_samples=512) == (123456789, {'num_samples': 512})
    np.testing.assert_allclose(radios['tx'].position, [2, -3, 10])
    np.testing.assert_allclose(radios['rx'].position, [3, -3, 10])
    np.testing.assert_allclose(radios['rx'].velocity, [1, -2, -3])
    epochs = iter([123, 124])
    world.get_sim_time = lambda: next(epochs)
    with pytest.raises(RuntimeError, match='advanced'):
        bridge.capture()
    # Rejected snapshot does not mutate the RF mounts.
    np.testing.assert_allclose(radios['rx'].position, [3, -3, 10])
    world.is_paused = lambda: False
    with pytest.raises(RuntimeError, match='Pause'):
        bridge.capture()
