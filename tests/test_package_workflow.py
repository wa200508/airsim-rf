"""User setup failures must be diagnosed before simulator mutation or I/Q capture."""
import json

import numpy as np
import pytest

from airsim_rf.example import prepare
from airsim_rf.preflight import check


def test_plan_accounts_for_tick_overshoot_and_source_margin(tmp_path):
    config=prepare(tmp_path/'inputs')
    result=check(config,output=tmp_path/'capture')
    plan=result['plan']
    assert plan['samples_per_window']==24000
    assert plan['complex_samples_per_receiver']==240000
    assert plan['raw_iq_bytes']==960000
    assert result['server_contacted'] is False
    assert result['backend']['status']=='not_requested'
    assert not (tmp_path/'capture').exists()
    np.save(config.parent/'tx0.npy',np.ones(240000,dtype=complex))
    with pytest.raises(ValueError,match='lookahead'):
        check(config)


@pytest.mark.parametrize('change,match',[
    (lambda d:d.update(reciever_profile={}), 'unknown'),
    (lambda d:d['radios']['rx0'].update(robot='missing'), 'absent from simulator'),
    (lambda d:d['radios']['tx0'].pop('transmit_power_w'), 'requires transmit_power_w'),
    (lambda d:d['receiver_profile'].update(bandwith=10), 'Invalid receiver_profile'),
    (lambda d:d['radios']['rx0'].update(mount_boddy_m=[0,0,0]), 'unknown keys'),
])
def test_misconfigurations_are_actionable_before_capture(tmp_path,change,match):
    path=prepare(tmp_path/'inputs')
    config=json.loads(path.read_text());change(config);path.write_text(json.dumps(config))
    with pytest.raises(ValueError,match=match):
        check(path)


def test_missing_robot_assets_and_overshoot_caps_fail(tmp_path):
    path=prepare(tmp_path/'inputs')
    with pytest.raises(ValueError,match='including tick overshoot'):
        check(path,max_samples=22000)
    (path.parent/'sim_config/robot_rf.jsonc').unlink()
    with pytest.raises(ValueError,match='missing robot-config'):
        check(path)


def test_shared_example_is_self_contained_and_does_not_overwrite(tmp_path):
    pytest.importorskip('pxr')
    path=prepare(tmp_path/'shared',geometry='shared')
    result=check(path)
    assert result['inputs']['geometry_bundle']['placement']=='spawn'
    assert len(result['inputs']['geometry_bundle']['manifest']['object_map'])==3
    config=json.loads(path.read_text())
    assert config['receiver_profile']['noise_enabled'] is False
    robots=json.loads((path.parent/'sim_config/scene_rf.jsonc').read_text())['actors']
    assert [r['origin']['xyz'] for r in robots]==['-20 0 -120','20 0 -120']
    before=path.read_bytes()
    with pytest.raises(FileExistsError):
        prepare(path.parent,geometry='shared')
    assert path.read_bytes()==before


def test_plan_rejects_existing_recording_and_nonintegral_intervals(tmp_path):
    path=prepare(tmp_path/'inputs')
    with pytest.raises(ValueError,match='already exists'):
        check(path,output=path.parent)
    with pytest.raises(ValueError,match='positive integer'):
        check(path,updates=True)
    scene=path.parent/'sim_config/scene_rf.jsonc'
    value=json.loads(scene.read_text());value['clock']['step-ns']=501
    scene.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='not sample-aligned'):
        check(path,advance_ns=1000)


def test_live_run_rejects_short_source_before_backend_or_output_creation(tmp_path):
    from airsim_rf.live import run
    path=prepare(tmp_path/'inputs')
    with pytest.raises(ValueError,match='Waveform too short'):
        run(path,tmp_path/'capture',updates=1000)
    assert not (tmp_path/'capture').exists()
