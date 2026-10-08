"""Actual CUDA path-counter semantics on the explicit older Pascal stack."""
import numpy as np
import pytest


def test_pascal_atomic_counter_preserves_counts_masks_and_unique_slots():
    import drjit as dr
    import mitsuba as mi
    if dr.__version__ != '1.3.1' or mi.__version__ != '3.8.0' or not mi.variant().startswith('cuda'):
        pytest.skip('Requires the explicit P100 CUDA propagation environment')
    from airsim_rf.p100_compat import enable_pascal_compat
    enable_pascal_compat()
    target = mi.UInt([3, 7])
    result = dr.scatter_inc(target, mi.UInt([0,0,1,1,0]), mi.Bool([True,True,True,True,False]))
    np.testing.assert_array_equal(target.numpy(), [5,9])
    actual = result.numpy()
    assert sorted(actual[:2]) == [3,4]
    assert sorted(actual[2:4]) == [7,8]
    assert actual[4] == 0
