"""Check independent one-way channels against native Sionna and image geometry."""
import numpy as np
import pytest

from airsim_rf import RFReceiver, ReceiverConfig
from airsim_rf.single_bounce import SingleBouncePathSolver, _plane_key


def make_scene(*, pattern="iso", empty=False):
    import sionna.rt as rt
    scene = rt.load_scene(None if empty else rt.scene.floor_wall)
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern=pattern, polarization="V")
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern=pattern, polarization="V")
    scene.add(rt.Transmitter("tx", position=[0.5, 0.2, 2], velocity=[0.3, 0, 0]))
    scene.add(rt.Receiver("rx", position=[1.5, 0.2, 2], velocity=[1, 0, 0]))
    return scene


def ordered(paths):
    a, tau = paths.cir(normalize_delays=False, out_type="numpy")
    doppler = paths.doppler.numpy()
    links = []
    for r in range(tau.shape[0]):
        for t in range(tau.shape[1]):
            indices = np.flatnonzero(tau[r, t] >= 0)
            indices = indices[np.argsort(tau[r, t, indices])]
            links.append((tau[r, t, indices], a[r, 0, t, 0, indices, 0], doppler[r, t, indices]))
    return links


@pytest.mark.parametrize("pattern", ["iso", "tr38901"])
def test_reflected_one_way_channels_and_antenna_rotation_match_native(pattern):
    import sionna.rt as rt
    scene = make_scene(pattern=pattern)
    scene.add(rt.Transmitter("tx2", position=[0.6, -0.1, 2.2], velocity=[-0.2, 0.1, 0]))
    scene.add(rt.Receiver("rx2", position=[1.4, -0.1, 1.8], velocity=[0, 0.2, 0]))
    solver = SingleBouncePathSolver()
    native = rt.PathSolver(deterministic=True)
    for angle in (0, 0.7):
        scene.transmitters["tx"].orientation = [angle, 0.1, -0.2]
        actual = ordered(solver(scene, max_num_paths_per_src=100))
        expected = ordered(native(scene, max_depth=1, samples_per_src=10000,
                                  max_num_paths_per_src=100, refraction=False))
        for (tau, gain, fd), (ref_tau, ref_gain, ref_fd) in zip(actual, expected):
            assert len(tau) == 3
            np.testing.assert_allclose(tau, ref_tau, rtol=2e-6, atol=1e-13)
            np.testing.assert_allclose(gain, ref_gain, rtol=3e-4, atol=1e-9)
            np.testing.assert_allclose(fd, ref_fd, atol=2e-4)
    assert solver.mesh_rebuilds == 1  # Antenna rotations do not alter the mesh.


def test_geometry_edit_invalidates_cached_planes_and_changes_reflection():
    scene = make_scene()
    solver = SingleBouncePathSolver()
    before = ordered(solver(scene))[0][0]
    # Sionna merges this fixture's floor and wall into one mesh. Translating
    # it along x moves the wall plane while keeping the floor plane unchanged.
    wall = next(iter(scene.objects.values()))
    wall.position = wall.position + [-0.5, 0, 0]
    after = ordered(solver(scene))[0][0]
    np.testing.assert_allclose(before*299792458, [1, 2, np.sqrt(17)], rtol=1e-5)
    np.testing.assert_allclose(after*299792458, [1, 3, np.sqrt(17)], rtol=1e-5)
    assert solver.mesh_rebuilds == 2


@pytest.mark.parametrize("depth", [0, 1])
def test_blocked_los_does_not_pass_through_wall(depth):
    scene = make_scene()
    solver = SingleBouncePathSolver()
    clear = ordered(solver(scene, max_depth=depth))[0][0]
    assert np.any(np.isclose(clear*299792458, 1))
    scene.receivers["rx"].position = [-0.5, 0.2, 2]
    blocked = ordered(solver(scene, max_depth=depth))[0][0]
    assert not np.any(np.isclose(blocked*299792458, 1))
    scene.receivers["rx"].position = [1.5, 0.2, 2]
    restored = ordered(solver(scene, max_depth=depth))[0][0]
    np.testing.assert_allclose(restored, clear)


def test_receiver_opt_in_preserves_complex_voltage():
    scene = make_scene()
    cfg = ReceiverConfig(num_samples=64)
    native = RFReceiver(scene, cfg).capture(np.ones_like, 7000000)
    optimized = RFReceiver(scene, cfg, path_solver="single-bounce").capture(np.ones_like, 7000000)
    np.testing.assert_allclose(optimized.iq_volts, native.iq_volts, rtol=3e-4, atol=1e-9)


def test_exact_coplanarity_preserves_nearby_reflectors():
    triangle = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
    assert _plane_key(triangle) == _plane_key(triangle[::-1])
    assert _plane_key(triangle) != _plane_key(triangle + [0, 0, 1e-9])


@pytest.mark.parametrize("options", [{"max_depth": 2}, {"diffuse_reflection": True},
                                    {"refraction": True}, {"diffraction": True}])
def test_unsupported_physics_is_rejected(options):
    with pytest.raises(ValueError, match="LoS and specular"):
        SingleBouncePathSolver()(make_scene(), **options)


def test_candidate_budget_rejects_truncation():
    with pytest.raises(ValueError, match="path cap"):
        SingleBouncePathSolver()(make_scene(), max_num_paths_per_src=1)
    with pytest.raises(ValueError, match="exceeds limit"):
        SingleBouncePathSolver(candidate_limit=1)(make_scene())
