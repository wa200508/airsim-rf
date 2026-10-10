"""Independent RF height/delay check for the focused visualization."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
import pytest

# Load the benchmark by filename so the tests work from the container's /work
# directory without installing the documentation examples as a package.
_spec = spec_from_file_location('terrain_scan_example', Path(__file__).resolve().parents[1]/'benchmarks/terrain_scan.py')
_example = module_from_spec(_spec)
_spec.loader.exec_module(_example)
TerrainScan, scan_scene, total_length_to_height = _example.TerrainScan, _example.scan_scene, _example.total_length_to_height


def test_narrow_pattern_gain_and_half_power_angle():
    import drjit as dr
    import mitsuba as mi
    scene, peak_dbi = scan_scene('ground')
    pattern = scene.tx_array.antenna_pattern.v_pattern
    boresight = float(dr.squared_norm(pattern(mi.Float(np.pi/2), mi.Float(0)))[0])
    half = float(dr.squared_norm(pattern(mi.Float(np.pi/2), mi.Float(np.deg2rad(6))))[0])
    assert 10*np.log10(boresight) == pytest.approx(peak_dbi, abs=1e-3)
    assert half/boresight == pytest.approx(.5, rel=1e-3)
    back = float(dr.squared_norm(pattern(mi.Float(np.pi/2), mi.Float(np.pi)))[0])
    assert 0 < back/boresight < 2e-6


@pytest.mark.parametrize("renderer", ["numpy", "direct-cuda"])
def test_actual_iq_peak_moves_earlier_when_ground_is_raised(renderer):
    if renderer == "direct-cuda":
        import drjit as dr
        if not dr.has_backend(dr.JitBackend.CUDA):
            pytest.skip("CUDA device unavailable")
    scene, _ = scan_scene('ground')
    scan = TerrainScan(scene, renderer=renderer)
    estimates, lengths = [], []
    gate = (scan.length_m >= 60) & (scan.length_m <= 100)
    ground = next(iter(scene.objects.values()))
    for height in (0, 5):
        ground.position = [0, 0, height]
        iq, compressed, count = scan.capture([0, 0, 40], velocity=[0, 0, 0], epoch_s=0)
        assert count > 800
        assert iq.dtype == np.complex64 and np.isfinite(iq).all()
        peak = np.flatnonzero(gate)[np.argmax(np.abs(compressed[gate]))]
        lengths.append(scan.length_m[peak])
        estimates.append(float(total_length_to_height(scan.length_m[peak])))
        # Expected bistatic delay is independent of the visualization code.
        expected_length = 2*np.sqrt((40-height)**2+1)
        assert lengths[-1] == pytest.approx(expected_length, abs=.6)
    assert lengths[1] < lengths[0]
    assert estimates == pytest.approx([0, 5], abs=.4)
