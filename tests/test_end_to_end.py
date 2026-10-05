"""Real scene/channel/render/front-end/consumer integration, not synthetic channels."""
import importlib.util
import json
from pathlib import Path
import struct

import numpy as np
import pytest

from airsim_rf.sdr import PlutoSDRProfile, SDREmitter, SDRNetworkReceiver, RadioClock
from airsim_rf.sampled_waveform import SampledWaveform

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rf_end_to_end', ROOT/'benchmarks/benchmark_end_to_end.py')
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)


def terrain_receiver(renderer, *, continuous=True):
    import sionna.rt as rt
    scene = rt.load_scene(str(ROOT/'benchmarks/scenes/terrain.xml'))
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='hw_dipole', polarization='V')
    scene.rx_array = scene.tx_array
    source = np.random.default_rng(43).normal(size=1500)+1j*np.random.default_rng(61).normal(size=1500)
    emitters = {}
    for i, position in enumerate(([-30,-10,30], [20,10,25])):
        scene.add(rt.Transmitter(f'tx{i}', position=position, velocity=[3+i,2,0]))
        emitters[f'tx{i}'] = SDREmitter(SampledWaveform(source*(1+1j*i), 2e6, -150000),
                                      transmit_power_w=1e-4, clock=RadioClock(phase_rad=.2*i))
    scene.add(rt.Receiver('rx0', position=[30,-50,30], velocity=[4,0,1]))
    return SDRNetworkReceiver(scene, emitters, PlutoSDRProfile(noise_enabled=False),
        renderer=renderer, samples_per_link=1028, continuous=continuous, link_diagnostics=False)


@pytest.mark.parametrize('renderer', ['basis-cpu','basis-cuda'])
def test_moving_scene_basis_matches_direct_all_path_oracle_across_epochs(renderer):
    if renderer == 'basis-cuda':
        cp = pytest.importorskip('cupy')
        try:
            available = cp.cuda.runtime.getDeviceCount()
        except cp.cuda.runtime.CUDARuntimeError as exc:
            pytest.skip(f'CUDA runtime unavailable: {exc}')
        if not available:
            pytest.skip('CUDA device unavailable')
    basis = terrain_receiver(renderer)
    direct = terrain_receiver('batched-llvm')
    for index in range(3):
        for receiver in (basis, direct):
            receiver.scene.receivers['rx0'].position = [30+.1*index, -50, 30]
        actual = basis.capture(index*128000, num_samples=256)['rx0']
        expected = direct.capture(index*128000, num_samples=256)['rx0']
        assert min(actual.retained_paths.values()) > 1
        assert actual.retained_paths == expected.retained_paths
        np.testing.assert_allclose(actual.input_iq_volts, expected.input_iq_volts, rtol=2e-5, atol=1e-10)
        np.testing.assert_allclose(actual.adc_iq_volts, expected.adc_iq_volts,
                                   rtol=0, atol=actual.volts_per_count*1.01)


def test_continuous_filter_state_matches_unsplit_stationary_capture_and_rejects_gap():
    split = terrain_receiver('basis-cpu')
    whole = terrain_receiver('basis-cpu')
    for receiver in (split, whole):
        for device in list(receiver.scene.transmitters.values())+list(receiver.scene.receivers.values()):
            device.velocity = [0,0,0]
    a = split.capture(0, num_samples=256)['rx0']
    b = split.capture(128000, num_samples=256)['rx0']
    expected = whole.capture(0, num_samples=512)['rx0']
    np.testing.assert_allclose(np.concatenate([a.input_iq_volts,b.input_iq_volts]),
                               expected.input_iq_volts, rtol=2e-6, atol=1e-11)
    with pytest.raises(ValueError, match='consecutive'):
        split.capture(300000, num_samples=256)
    assert split._next_time_ns == 256000


def test_full_terrain_to_network_consumer_contiguous_sample_accounting(tmp_path):
    result = e2e.run(output=tmp_path/'run', tx=2, rx=2, iterations=3, warmup=0)
    assert result['scope'] == 'rf_pipeline_end_to_end'
    assert result['captured_files'] == 8  # First capture plus three timed epochs, two RX.
    rows = [result['first_capture'], *result['samples']]
    assert [row['samples'] for row in rows[:3]] == [16667,16666,16667]
    for previous, current in zip(rows, rows[1:]):
        assert current['sim_time_ns'] == previous['sim_time_ns']+previous['samples']*500
    for row in rows:
        assert row['channel_ms']>0 and row['rendering_ms']>0 and row['receiver_ms']>0
        assert row['delivery_storage_ms']>0
        assert all(min(paths.values())>1 for paths in row['retained_paths'].values())
        for ri in range(2):
            payload = (tmp_path/'run'/'captures'/f'{row["sequence"]:06d}_rx{ri}.sc16').read_bytes()
            assert struct.unpack('<III',payload[:12]) == (row['sequence'],ri,row['samples'])
            codes = np.frombuffer(payload[12:],dtype='<i2')
            assert codes.size == row['samples']*2 and np.any(codes != 0)
    stored = json.loads((tmp_path/'run'/'measurements.json').read_text())
    assert stored['summary'] == result['summary']
    assert (tmp_path/'run'/'REPORT.md').is_file()


def test_rolling_sources_keep_history_identical_and_transmitters_independent():
    sources = e2e.PrivateSources(['tx0','tx1'])
    a = sources.window(0,16667)
    b = sources.window(16667,16666)
    offset = (b['tx0'].reference_time_ns-a['tx0'].reference_time_ns)//500
    overlap = len(a['tx0'].samples)-offset
    np.testing.assert_array_equal(a['tx0'].samples[offset:], b['tx0'].samples[:overlap])
    assert not np.array_equal(a['tx0'].samples,a['tx1'].samples)
    assert not np.shares_memory(a['tx0'].samples,b['tx0'].samples)


def test_continuous_timestamps_keep_integer_nanoseconds_at_large_epochs():
    receiver = terrain_receiver('basis-cpu')
    epoch = 1_700_000_000_000_000_001
    for name, emitter in receiver.emitters.items():
        from dataclasses import replace
        receiver.emitters[name] = replace(emitter, waveform=replace(emitter.waveform,
            reference_time_ns=emitter.waveform.reference_time_ns+epoch))
    receiver.capture(epoch, num_samples=256)
    assert receiver._next_time_ns == epoch+128000
    receiver.capture(epoch+128000, num_samples=256)
    assert receiver._next_time_ns == epoch+256000


def test_container_build_provenance_does_not_require_git_checkout(tmp_path,monkeypatch):
    monkeypatch.setenv('RF_PROFILE_SOURCE_REV','container-build-revision')
    monkeypatch.setenv('RF_PROFILE_SOURCE_DIRTY','false')
    original = e2e.subprocess.check_output
    def no_git(command,*args,**kwargs):
        if command[0] == 'git':
            raise AssertionError('Container benchmark must use build provenance, not .git')
        return original(command,*args,**kwargs)
    monkeypatch.setattr(e2e.subprocess,'check_output',no_git)
    result=e2e.run(output=tmp_path/'container',tx=1,rx=1,iterations=2,warmup=0)
    assert result['source_revision']=='container-build-revision'
    assert result['source_dirty'] is False
    assert result['measurement_mode']=='unprofiled_end_to_end_benchmark'
