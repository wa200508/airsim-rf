"""Live capture contracts without requiring a running simulator or GPU."""
import json
from types import SimpleNamespace
import numpy as np
import pytest

from airsim_rf.live import record
from airsim_rf.sdr_bridge import AirSimSDRBridge


class TickWorld:
    def __init__(self, tick_ns=6_000_000):
        self.time = 1_700_000_000_000_000_000
        self.tick_ns = tick_ns
        self.paused = True

    def is_paused(self):
        return self.paused

    def get_sim_time(self):
        return self.time

    def continue_until_sim_time(self, target, *, wait_until_complete):
        assert wait_until_complete
        self.time += ((target-self.time+self.tick_ns-1)//self.tick_ns)*self.tick_ns


def fixture(world):
    kin = {'pose': {'position': {'x': 2, 'y': 3, 'z': -10},
                   'orientation': {'w': 1, 'x': 0, 'y': 0, 'z': 0}},
           'twist': {'linear': {'x': 1, 'y': 2, 'z': 3},
                     'angular': {'x': 0, 'y': 0, 'z': 0}}}
    scene = SimpleNamespace(transmitters={'tx': SimpleNamespace()}, receivers={'rx': SimpleNamespace()})
    robots = {name: SimpleNamespace(get_ground_truth_kinematics=lambda: {'kinematics': kin}) for name in ('tx', 'rx')}
    calls = []
    def capture(epoch, *, num_samples):
        if calls:
            assert epoch == calls[-1][0]+calls[-1][1]*500
        calls.append((epoch, num_samples))
        return {'rx': SimpleNamespace(adc_codes=np.tile([123, -456], (num_samples, 1)),
                sim_time_ns=epoch, volts_per_count=0.001, clipped_component_fraction=0.)}
    receiver = SimpleNamespace(scene=scene, profile=SimpleNamespace(sample_rate_hz=2e6, carrier_hz=915e6),
             clocks={'rx': SimpleNamespace(error_ppm=0)}, capture=capture, continuous=True)
    return robots, receiver, calls


def test_elapsed_capture_includes_physics_overshoot_and_preserves_continuity():
    world = TickWorld()
    robots, receiver, calls = fixture(world)
    bridge = AirSimSDRBridge(world, robots, receiver)
    start = world.time
    bridge.capture_elapsed(advance_ns=10_000_000)
    bridge.capture_elapsed(advance_ns=10_000_000)
    assert calls == [(start, 24000), (start+12_000_000, 24000)]
    np.testing.assert_equal(receiver.scene.transmitters['tx'].position, [2, -3, 10])


@pytest.mark.parametrize('tick, cap, match', [(501, 100, 'sample-aligned'), (6000000, 22000, 'overshoot')])
def test_elapsed_capture_rejects_unrepresentable_or_excessive_intervals(tick, cap, match):
    world = TickWorld(tick)
    robots, receiver, calls = fixture(world)
    with pytest.raises(RuntimeError, match=match):
        AirSimSDRBridge(world, robots, receiver).capture_elapsed(advance_ns=1000 if tick==501 else 10_000_000, max_samples=cap)
    assert calls == []


def test_live_recording_has_correct_offsets_counts_and_samples(tmp_path):
    world = TickWorld()
    robots, receiver, calls = fixture(world)
    output = tmp_path/'run'
    result = record(world, robots, receiver, output, updates=2, advance_ns=10_000_000, max_samples=100000)
    assert result['status'] == 'complete'
    assert result['signal_seconds_per_receiver'] == 0.024
    metadata = json.loads((output/'rx.sigmf-meta').read_text())
    assert [c['core:sample_start'] for c in metadata['captures']] == [0, 24000]
    assert [c['airsim_rf:sim_time_ns'] for c in metadata['captures']] == [c[0] for c in calls]
    samples = np.fromfile(output/'rx.sigmf-data', dtype='<i2').reshape(-1, 2)
    np.testing.assert_equal(samples, np.tile([123, -456], (48000, 1)))
    assert json.loads((output/'manifest.json').read_text()) == result


def test_live_recording_keeps_completed_data_when_next_capture_fails(tmp_path):
    world = TickWorld()
    robots, receiver, calls = fixture(world)
    original = receiver.capture
    def fail_second(*args, **kwargs):
        if calls:
            raise RuntimeError('lost simulator')
        return original(*args, **kwargs)
    receiver.capture = fail_second
    with pytest.raises(RuntimeError, match='lost simulator'):
        record(world, robots, receiver, tmp_path/'run', updates=2, advance_ns=10_000_000, max_samples=100000)
    manifest = json.loads((tmp_path/'run/manifest.json').read_text())
    assert manifest['status'] == 'failed'
    assert len(manifest['rows']) == 1
    assert manifest['signal_seconds_per_receiver'] == .012


def test_generated_first_run_inputs_are_finite_and_paths_resolve(tmp_path):
    import importlib.util
    from pathlib import Path
    from airsim_rf.live import validate_inputs
    spec=importlib.util.spec_from_file_location('prepare_live',Path(__file__).resolve().parents[1]/'examples/prepare_live_example.py')
    example=importlib.util.module_from_spec(spec);spec.loader.exec_module(example)
    path=example.prepare(tmp_path/'example')
    provenance=validate_inputs(path)
    assert provenance['waveforms']['tx0']['samples']==500000
    assert provenance['waveforms']['tx0']['signal_seconds']==.25
    assert provenance['rf_scene']['scene_id']=='rf_ground'
    np.testing.assert_allclose(provenance['waveforms']['tx0']['mean_sample_power'],1)
    np.save(path.parent/'tx0.npy',np.array([complex(float('nan'),0)]))
    with pytest.raises(ValueError,match='finite'):
        validate_inputs(path)


def test_real_projectairsim_rpc_pose_twist_is_not_wrapped():
    world=TickWorld();robots,receiver,calls=fixture(world)
    for robot in robots.values():
        wrapped=robot.get_ground_truth_kinematics()
        robot.get_ground_truth_kinematics=lambda value=wrapped['kinematics']: value
    bridge=AirSimSDRBridge(world,robots,receiver)
    bridge.capture_elapsed(advance_ns=10_000_000)
    assert calls[0][1]==24000
    np.testing.assert_equal(receiver.scene.transmitters['tx'].position,[2,-3,10])


def test_recording_inspector_rejects_timestamp_discontinuity(tmp_path):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('inspect_live',Path(__file__).resolve().parents[1]/'scripts/inspect_live_recording.py')
    tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
    world=TickWorld();robots,receiver,_=fixture(world)
    directory=tmp_path/'run';record(world,robots,receiver,directory,updates=2,advance_ns=10_000_000,max_samples=100000)
    assert tool.inspect(directory)['updates']==2
    path=directory/'manifest.json';manifest=json.loads(path.read_text());manifest['rows'][1]['sim_time_ns']+=500
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='contiguous'):
        tool.inspect(directory)
