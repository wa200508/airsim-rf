import importlib.util
from pathlib import Path
import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('directional',Path(__file__).resolve().parents[1]/'scripts/analyze_directional_turns.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_gain_boresight_half_width_and_rear_cap():
    assert module.gain_db([1,0,0])==8
    angle=np.radians(32.5)
    assert module.gain_db([np.cos(angle),np.sin(angle),0])==pytest.approx(5)
    assert module.gain_db([-1,0,0])==-22


def test_yaw_rotates_rf_west_direction_to_local_forward():
    state={'pose':{'orientation':{'x':0,'y':0,'z':-2**-.5,'w':2**-.5}}}
    np.testing.assert_allclose(module.local_direction([0,1,0],state),[1,0,0],atol=1e-12)
