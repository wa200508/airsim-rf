import importlib.util
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('turning',Path(__file__).resolve().parents[1]/'scripts/analyze_turning_mounts.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_quaternion_mount_rotation_and_coordinate_conversion():
    state={'pose':{'position':{'x':10,'y':20,'z':-30},
                   'orientation':{'x':0,'y':0,'z':2**-.5,'w':2**-.5}}}
    # Body-forward lever points east after +90 degree NED yaw; RF y points west.
    np.testing.assert_allclose(module.mount_position(state,[2,0,1]),[10,-22,29],atol=1e-12)
