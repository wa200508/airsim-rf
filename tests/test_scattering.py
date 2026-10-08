"""Antenna coverage, power normalization and physical first-order scattering."""
from pathlib import Path

import numpy as np
import pytest

from airsim_rf import RFReceiver, ReceiverConfig
from airsim_rf.scattering import FirstOrderScatteringPathSolver, _AngularProposal


def ground_scene(*, tx_pattern="iso", rx_pattern="iso", colocated=False):
    import sionna.rt as rt
    scene = rt.load_scene(str(Path(__file__).resolve().parents[1]/"benchmarks/scenes/ground.xml"))
    scene.frequency = 2.4e9
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern=tx_pattern, polarization="V")
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern=rx_pattern, polarization="V")
    scene.add(rt.Transmitter("tx", position=[-5, 0, 10], orientation=[0, np.pi/2, 0], velocity=[1, 0, 0]))
    scene.add(rt.Receiver("rx", position=[-5 if colocated else 5, 0, 10], orientation=[0, np.pi/2, 0], velocity=[0, .5, 0]))
    return scene


def path_data(paths):
    from sionna.rt.constants import InteractionType
    a, tau = paths.cir(normalize_delays=False, out_type="numpy")
    diffuse = paths.interactions.numpy()[0, 0, 0] == int(InteractionType.DIFFUSE)
    return a[0, 0, 0, 0, :, 0], tau[0, 0], diffuse


@pytest.mark.parametrize("receive", [False, True])
def test_both_endpoint_proposals_cover_boresight_and_keep_sidelobes(receive):
    import sionna.rt as rt
    patterns = rt.PlanarArray(num_rows=1, num_cols=1, pattern="tr38901", polarization="V").antenna_pattern.patterns
    proposal = _AngularProposal.from_patterns(patterns, receive=receive, uniform_fraction=.1)
    assert proposal.probability.sum() == pytest.approx(1)
    assert proposal.probability.min() >= .1/proposal.probability.size
    directions = proposal.draw(np.random.default_rng(11), 10000)
    # Local boresight is +x for both transmitting and receiving antennas.
    # Receiving pattern must look toward the scatterer, not away from it.
    assert directions[0].mean() > .7
    np.testing.assert_allclose(np.linalg.norm(directions, axis=0), 1, atol=1e-12)


def test_both_antenna_patterns_change_surface_coverage():
    solver = FirstOrderScatteringPathSolver()
    scene = ground_scene(tx_pattern="tr38901", rx_pattern="tr38901")
    paths = solver(scene, samples_per_src=1028, max_num_paths_per_src=1100,
                   los=False, specular_reflection=False)
    _, _, diffuse = path_data(paths)
    assert diffuse.sum() > 850
    assert solver.sampling["tx_launches"] == solver.sampling["rx_launches"] == 514
    # Aim RX upward while TX still illuminates the ground. RX proposal rays
    # then mostly miss it; keeping all nonzero sidelobes preserves some returns.
    scene.receivers["rx"].orientation = [0, -np.pi/2, 0]
    _, _, tilted = path_data(solver(scene, samples_per_src=1028, max_num_paths_per_src=1100,
                                    los=False, specular_reflection=False))
    assert tilted.sum() < diffuse.sum()*.7
    assert tilted.sum() > 0
    scene.receivers["rx"].orientation = [0, np.pi/2, 0]
    scene.transmitters["tx"].orientation = [0, -np.pi/2, 0]
    _, _, tilted_tx = path_data(solver(scene, samples_per_src=1028, max_num_paths_per_src=1100,
                                       los=False, specular_reflection=False))
    assert 0 < tilted_tx.sum() < diffuse.sum()*.7


def test_uniform_mixture_power_matches_native_and_does_not_grow_with_ray_count():
    import sionna.rt as rt
    scene = ground_scene(colocated=True)
    solver = FirstOrderScatteringPathSolver(uniform_fraction=1)
    powers = []
    for count in (4096, 16384):
        paths = solver(scene, samples_per_src=count, max_num_paths_per_src=count,
                       los=False, specular_reflection=False)
        a, _, diffuse = path_data(paths)
        powers.append(float(np.sum(np.abs(a[diffuse])**2)))
    assert powers[1] == pytest.approx(powers[0], rel=.08)
    native = rt.PathSolver(deterministic=True)(scene, max_depth=1, samples_per_src=16384,
             max_num_paths_per_src=16384, los=False, specular_reflection=False,
             diffuse_reflection=True, refraction=False)
    a, _, diffuse = path_data(native)
    assert powers[1] == pytest.approx(float(np.sum(np.abs(a[diffuse])**2)), rel=.05)


def test_importance_sampling_preserves_power_at_displaced_endpoints():
    scene = ground_scene(tx_pattern="tr38901", rx_pattern="tr38901")
    powers = []
    for fraction in (.1, 1):
        solver = FirstOrderScatteringPathSolver(uniform_fraction=fraction)
        paths = solver(scene, samples_per_src=32768, max_num_paths_per_src=32768,
                       los=False, specular_reflection=False)
        a, _, diffuse = path_data(paths)
        powers.append(float(np.sum(np.abs(a[diffuse])**2)))
    # Importance concentration must improve coverage without increasing power.
    assert powers[0] == pytest.approx(powers[1], rel=.08)


def test_scattered_delay_and_doppler_use_both_independent_endpoints():
    scene = ground_scene()
    paths = FirstOrderScatteringPathSolver()(scene, samples_per_src=1028,
                  max_num_paths_per_src=1100, los=False, specular_reflection=False)
    a, tau, diffuse = path_data(paths)
    vertices = paths.vertices.numpy()[0, 0, 0][diffuse]
    tx, rx = np.array([-5, 0, 10]), np.array([5, 0, 10])
    first, last = vertices-tx, rx-vertices
    lengths = np.linalg.norm(first, axis=1)+np.linalg.norm(last, axis=1)
    np.testing.assert_allclose(tau[diffuse], lengths/299792458, rtol=2e-6)
    wavelength = 299792458/2.4e9
    expected_fd = ((first/np.linalg.norm(first, axis=1)[:, None])[:, 0]
                  -.5*(last/np.linalg.norm(last, axis=1)[:, None])[:, 1])/float(wavelength)
    np.testing.assert_allclose(paths.doppler.numpy()[0, 0][diffuse], expected_fd, atol=2e-4)
    assert np.isfinite(a).all()


def test_zero_scattering_material_does_not_invent_ground_clutter():
    scene = ground_scene()
    for material in scene.radio_materials.values():
        material.scattering_coefficient = 0
    _, _, diffuse = path_data(FirstOrderScatteringPathSolver()(scene,
                      samples_per_src=1028, max_num_paths_per_src=1100))
    assert diffuse.sum() == 0


def test_receiver_can_generate_iq_from_scattering_channel():
    scene = ground_scene()
    receiver = RFReceiver(scene, ReceiverConfig(num_samples=32), path_solver="first-order-scattering",
                          samples_per_src=1028, max_num_paths_per_src=1100)
    block = receiver.capture(lambda t: np.exp(2j*np.pi*1000*t), 12300000)
    assert block.path_delays_s.size > 100
    assert block.iq_volts.dtype == np.complex64
    assert np.isfinite(block.iq_volts).all()


def test_budget_rejects_sample_truncation_and_missing_endpoint():
    scene = ground_scene()
    with pytest.raises(ValueError, match="path cap"):
        FirstOrderScatteringPathSolver()(scene, max_num_paths_per_src=1000)
    with pytest.raises(ValueError, match="both TX and RX"):
        FirstOrderScatteringPathSolver()(scene, samples_per_src=1)


def test_cached_draws_preserve_moving_paths_and_invalidate_seed_and_patterns():
    import sionna.rt as rt
    scene = ground_scene()
    cached = FirstOrderScatteringPathSolver(cache_sampling=True)
    fresh = FirstOrderScatteringPathSolver(cache_sampling=False)
    for index, seed in enumerate([42, 42, 99, 99]):
        scene.transmitters['tx'].position = [-5+.2*index, 0, 10]
        scene.receivers['rx'].orientation = [0, np.pi/2+.05*index, 0]
        if index == 3:
            scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='tr38901', polarization='V')
        options = dict(samples_per_src=1028, max_num_paths_per_src=1100, seed=seed)
        a, tau, diffuse = path_data(cached(scene, **options))
        expected_a, expected_tau, expected_diffuse = path_data(fresh(scene, **options))
        order, expected_order = np.argsort(tau), np.argsort(expected_tau)
        np.testing.assert_array_equal(diffuse[order], expected_diffuse[expected_order])
        np.testing.assert_allclose(a[order], expected_a[expected_order], atol=1e-12, rtol=1e-6)
        np.testing.assert_allclose(tau[order], expected_tau[expected_order], atol=1e-12, rtol=0)
        assert cached.sampling['sampling_cache_hit'] == (index == 1)
