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
    report=tool.inspect(directory)
    assert report['updates']==2
    from hashlib import sha256
    data=(directory/'rx.sigmf-data').read_bytes()
    receiver_report=report['receivers']['rx']
    assert receiver_report['data_sha256']==sha256(data).hexdigest()
    assert receiver_report['data_bytes']==len(data)
    assert receiver_report['adc_component_min']==-456
    assert receiver_report['adc_component_max']==123
    assert receiver_report['nonzero_complex_sample_fraction']==1.
    path=directory/'manifest.json';manifest=json.loads(path.read_text());manifest['rows'][1]['sim_time_ns']+=500
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='contiguous'):
        tool.inspect(directory)


def test_check_config_cli_does_not_require_recording_output(tmp_path, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path
    from airsim_rf.live import main
    spec=importlib.util.spec_from_file_location('prepare_live',Path(__file__).resolve().parents[1]/'examples/prepare_live_example.py')
    example=importlib.util.module_from_spec(spec);spec.loader.exec_module(example)
    config=example.prepare(tmp_path/'inputs')
    monkeypatch.setattr('sys.argv',['airsim_rf.live','--config',str(config),'--check-config'])
    main()
    assert json.loads(capsys.readouterr().out)['waveforms']['tx0']['samples']==500000
    monkeypatch.setattr('sys.argv',['airsim_rf.live','--config',str(config)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code==2
    assert '--output is required when recording' in capsys.readouterr().err


def test_recording_reader_and_callback_preserve_samples_times_and_scaling(tmp_path):
    from airsim_rf.recording import iter_iq_blocks
    world=TickWorld();robots,receiver,_=fixture(world);seen=[]
    record(world,robots,receiver,tmp_path/'run',updates=2,advance_ns=10000000,max_samples=100000,
           on_capture=lambda name,cap:seen.append((name,cap.sim_time_ns,cap.adc_codes.copy())))
    blocks=list(iter_iq_blocks(tmp_path/'run','rx'))
    assert len(blocks)==len(seen)==2
    assert [b.sample_start for b in blocks]==[0,24000]
    for block,event in zip(blocks,seen):
        assert block.sim_time_ns==event[1]
        assert block.samples.dtype==np.complex64
        np.testing.assert_allclose(block.samples,.123-.456j,rtol=1e-6)
    raw=list(iter_iq_blocks(tmp_path/'run','rx',units='adc_codes'))
    np.testing.assert_array_equal(raw[0].samples,123-456j)
    path=tmp_path/'run/rx.sigmf-data';path.write_bytes(path.read_bytes()[:-4])
    with pytest.raises(ValueError,match='byte count'):
        list(iter_iq_blocks(tmp_path/'run','rx'))


def test_callback_failure_marks_saved_recording_failed(tmp_path):
    from airsim_rf.recording import iter_iq_blocks
    world=TickWorld();robots,receiver,_=fixture(world)
    def fail(name,capture):raise RuntimeError('processor failed')
    with pytest.raises(RuntimeError,match='processor failed'):
        record(world,robots,receiver,tmp_path/'run',updates=2,advance_ns=10000000,max_samples=100000,on_capture=fail)
    assert (tmp_path/'run/rx.sigmf-data').stat().st_size==24000*4
    with pytest.raises(ValueError,match='completed'):
        list(iter_iq_blocks(tmp_path/'run','rx'))


def test_propagation_choices_and_invalid_configuration():
    from airsim_rf.scenario import propagation_options
    assert propagation_options({})['surface_sampling'] is False
    assert propagation_options({'propagation':{'mode':'direct'}})['max_depth']==0
    assert propagation_options({'propagation':{'mode':'specular'}})['path_solver']=='single-bounce'
    assert propagation_options({'propagation':{'mode':'diffuse-surface','samples_per_link':4096}})['surface_sampling']
    for value in ({'mode':'unknown'},{'samples_per_link':True},{'seed':-1},{'typo':1}):
        with pytest.raises(ValueError):propagation_options({'propagation':value})


def test_multiple_receiver_files_keep_independent_scales(tmp_path):
    from airsim_rf.recording import iter_iq_blocks
    world=TickWorld();robots,receiver,_=fixture(world)
    receiver.scene.receivers['rx2']=SimpleNamespace()
    robots['rx2']=robots['rx']
    original=receiver.capture
    def capture(epoch,*,num_samples):
        result=original(epoch,num_samples=num_samples)
        result['rx2']=SimpleNamespace(adc_codes=np.tile([-20,30],(num_samples,1)),
            sim_time_ns=epoch,volts_per_count=.002,clipped_component_fraction=0.)
        return result
    receiver.capture=capture
    record(world,robots,receiver,tmp_path/'run',updates=2,advance_ns=10000000,max_samples=100000)
    first=list(iter_iq_blocks(tmp_path/'run','rx'));second=list(iter_iq_blocks(tmp_path/'run','rx2'))
    assert [b.sim_time_ns for b in first]==[b.sim_time_ns for b in second]
    np.testing.assert_allclose(first[0].samples,.123-.456j,rtol=1e-6)
    np.testing.assert_allclose(second[0].samples,-.04+.06j,rtol=1e-6)


def test_reader_rejects_mismatched_metadata(tmp_path):
    from airsim_rf.recording import iter_iq_blocks
    world=TickWorld();robots,receiver,_=fixture(world)
    record(world,robots,receiver,tmp_path/'run',updates=2,advance_ns=10000000,max_samples=100000)
    path=tmp_path/'run/rx.sigmf-meta';meta=json.loads(path.read_text())
    meta['captures'][1]['core:sample_start']+=1;path.write_text(json.dumps(meta))
    with pytest.raises(ValueError,match='offsets'):
        list(iter_iq_blocks(tmp_path/'run','rx'))


def test_antenna_config_preserves_defaults_and_separates_tx_rx():
    from airsim_rf.scenario import antenna_options
    default=antenna_options({})
    assert default['tx']['pattern']==default['rx']['pattern']=='hw_dipole'
    configured=antenna_options({'antennas':{'tx':{'pattern':'tr38901','polarization':'H'}}})
    assert configured['tx']['pattern']=='tr38901' and configured['tx']['polarization']=='H'
    assert configured['rx']==default['rx']
    for bad in ({'rx':{'polarization':'VH'}},{'tx':{'pattern':'bogus'}},{'rx':{'rows':2}},[],{'other':{}}):
        with pytest.raises(ValueError):antenna_options({'antennas':bad})


def test_recording_roundtrips_through_official_sigmf(tmp_path):
    sigmf=pytest.importorskip('sigmf')
    from airsim_rf.recording import iter_iq_blocks
    world=TickWorld();robots,receiver,_=fixture(world);output=tmp_path/'capture'
    record(world,robots,receiver,output,updates=2,advance_ns=10_000_000,max_samples=100000)
    external=sigmf.fromfile(str(output/'rx.sigmf-meta'),autoscale=False)
    external.validate()
    assert external.get_global_field('core:extensions')==[{'name':'airsim_rf','version':'0.1.0','optional':True}]
    for i,block in enumerate(iter_iq_blocks(output,'rx')):
        raw=external.read_samples_in_capture(i)
        np.testing.assert_array_equal(raw,np.full(len(raw),123-456j))
        np.testing.assert_allclose(raw*.001,block.samples,rtol=2e-7)


def test_recording_volts_exactly_match_adc_model_rounding(tmp_path):
    from airsim_rf.sdr import quantize_iq
    from airsim_rf.recording import iter_iq_blocks
    world=TickWorld();robots,receiver,_=fixture(world)
    analog=np.linspace(-.003,.003,24000)*(1+0.71j)
    codes,volts,scale,clipping=quantize_iq(analog,full_scale_dbm=-30)
    receiver.capture=lambda epoch,num_samples: {'rx':SimpleNamespace(adc_codes=codes,
        sim_time_ns=epoch,volts_per_count=scale,clipped_component_fraction=clipping)}
    record(world,robots,receiver,tmp_path/'run',updates=1,advance_ns=10_000_000,max_samples=100000)
    block=next(iter_iq_blocks(tmp_path/'run','rx'))
    np.testing.assert_array_equal(block.samples,volts)


def test_transport_disconnect_marks_recording_failed(tmp_path):
    import socket
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from airsim_rf.iq_stream import IQStreamWriter,iter_stream
    world=TickWorld();robots,receiver,_=fixture(world)
    original=receiver.capture
    def capture(epoch,*,num_samples):
        values=original(epoch,num_samples=num_samples)
        for value in values.values():
            value.adc_iq_volts=(value.adc_codes[:,0]+1j*value.adc_codes[:,1])*.001
            value.actual_sample_rate_hz=2e6
        return values
    receiver.capture=capture
    a,b=socket.socketpair();a.settimeout(2);b.settimeout(2);closed=threading.Event()
    with a,b,ThreadPoolExecutor(1) as pool:
        def consumer():
            next(iter_stream(b));b.close();closed.set()
        future=pool.submit(consumer);writer=IQStreamWriter(a,carrier_hz=915e6)
        def callback(name,value):
            writer.send_capture(name,value)
            assert closed.wait(2)
        with pytest.raises(OSError):
            record(world,robots,receiver,tmp_path/'run',updates=3,advance_ns=10_000_000,max_samples=100000,on_capture=callback)
        future.result(timeout=2)
    manifest=json.loads((tmp_path/'run/manifest.json').read_text())
    assert manifest['status']=='failed'
    assert (tmp_path/'run/rx.sigmf-data').stat().st_size>0


def test_geometry_guard_checks_both_epochs_and_preserves_start_report():
    world = TickWorld()
    robots, receiver, calls = fixture(world)
    epochs = []
    def guard(observed_world, epoch):
        assert observed_world is world
        assert epoch == world.time
        epochs.append(epoch)
        return {'sim_time_ns': epoch, 'geometry_sha256': 'static-scene'}
    bridge = AirSimSDRBridge(world, robots, receiver, geometry_guard=guard)
    start = world.time
    bridge.capture_elapsed(advance_ns=10_000_000)
    assert epochs == [start, start + 12_000_000]
    assert bridge.geometry_report['sim_time_ns'] == start
    assert calls == [(start, 24000)]


@pytest.mark.parametrize('fail_at', [1, 2])
def test_geometry_guard_failure_prevents_iq_generation(fail_at):
    world = TickWorld()
    robots, receiver, calls = fixture(world)
    epochs = []
    def guard(observed_world, epoch):
        epochs.append(epoch)
        if len(epochs) == fail_at:
            raise RuntimeError('static geometry changed')
        return {'sim_time_ns': epoch}
    bridge = AirSimSDRBridge(world, robots, receiver, geometry_guard=guard)
    with pytest.raises(RuntimeError, match='static geometry changed'):
        bridge.capture_elapsed(advance_ns=10_000_000)
    assert len(epochs) == fail_at
    assert calls == []
