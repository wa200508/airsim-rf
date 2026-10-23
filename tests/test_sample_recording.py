"""Lossless coherent archives, corruption detection and unchanged TCP consumers."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import socket
import numpy as np
import pytest
from airsim_rf.sample_stream import SampleBlock, iter_stream
from airsim_rf.sample_recording import SampleRecordingWriter, iter_recorded_windows, inspect, replay


def configuration():
    return {'schema_version': 1, 'sample_rate_hz': 1e6, 'carrier_hz': 433e6, 'sites': [
        {'id': f'array{i}', 'channels': [f'rx{i}_{j}' for j in range(4)], 'center_rf_m': [0, i*20, 0],
         'yaw_rad': 0., 'element_offsets_m': ((np.arange(4)-1.5)*299792458./433e6/2).tolist(),
         'calibration_complex': [[1, 0]]*4} for i in range(2)]}


def inputs(config, windows=3, count=2048):
    rng=np.random.default_rng(353)
    for index in range(windows):
        sample=index*count+np.arange(count)
        # Evolving phase/frequency across acquisition windows, not independent snapshots.
        signal=.001*np.exp(2j*np.pi*(.03*sample+1e-8*sample**2))
        blocks=[]
        for site in config['sites']:
            steering=np.exp(2j*np.pi*433e6/299792458.*np.asarray(site['element_offsets_m'])*np.sin(np.deg2rad(20)))
            for j,name in enumerate(site['channels']):
                values=(signal*steering[j]+1e-7*(rng.normal(size=count)+1j*rng.normal(size=count))).astype(np.complex64)
                blocks.append(SampleBlock(name,values,index*count,1_800_000_000_000_000_000+index*count*1000,1e6,433e6,.001*j))
        yield tuple(blocks)


def archive(tmp_path, *, status='complete'):
    config=configuration();groups=list(inputs(config));path=tmp_path/'iq'
    writer=SampleRecordingWriter(path,config)
    for blocks in groups:writer.write_window(blocks)
    writer.close(status)
    return path,groups


def test_exact_complex_volts_epochs_phase_and_sigmf(tmp_path):
    path,groups=archive(tmp_path)
    actual=list(iter_recorded_windows(path))
    for expected,received in zip(groups,actual):
        for a,b in zip(expected,received):
            assert a.receiver==b.receiver and a.timestamp_ns==b.timestamp_ns and a.sample_start==b.sample_start
            assert a.clipped_component_fraction==b.clipped_component_fraction
            assert a.samples.tobytes()==b.samples.tobytes()
    report=inspect(path,verify=True)
    assert report['payload_bytes']==3*2048*8*8 and report['sample_hashes_verified']
    assert report['signal_seconds']==3*2048/1e6
    metadata=json.loads((path/'rx0_0.sigmf-meta').read_text())
    assert metadata['global']['core:datatype']=='cf32_le'
    assert [c['core:sample_start'] for c in metadata['captures']]==[0,2048,4096]
    sigmf=pytest.importorskip('sigmf')
    capture=sigmf.sigmffile.fromfile(str(path/'rx0_0.sigmf-meta'))
    capture.validate()
    np.testing.assert_array_equal(capture.read_samples(),np.concatenate([g[0].samples for g in groups]))


@pytest.mark.parametrize('damage',['truncate','corrupt','journal','timing'])
def test_corruption_never_silently_changes_samples(tmp_path,damage):
    path,_=archive(tmp_path)
    data=path/'rx0_0.sigmf-data'
    if damage=='truncate':data.write_bytes(data.read_bytes()[:-8])
    elif damage=='corrupt':
        payload=bytearray(data.read_bytes());payload[77]^=1;data.write_bytes(payload)
    elif damage=='journal':(path/'windows.jsonl').write_text('')
    else:
        rows=[json.loads(line) for line in (path/'windows.jsonl').read_text().splitlines()]
        rows[1]['timestamp_ns']+=1
        (path/'windows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    with pytest.raises(ValueError):list(iter_recorded_windows(path))


def test_only_committed_prefix_is_opt_in_after_failure(tmp_path):
    path,groups=archive(tmp_path,status='failed')
    with (path/'rx0_0.sigmf-data').open('ab') as stream:stream.write(b'uncommitted')
    with pytest.raises(ValueError,match='incomplete'):list(iter_recorded_windows(path))
    actual=list(iter_recorded_windows(path,allow_partial=True))
    assert len(actual)==len(groups)
    np.testing.assert_array_equal(actual[-1][0].samples,groups[-1][0].samples)


def test_bad_channel_groups_rejected_before_journal_publish(tmp_path):
    config=configuration();blocks=next(inputs(config));writer=SampleRecordingWriter(tmp_path/'iq',config)
    try:
        with pytest.raises(ValueError,match='every'):writer.write_window(blocks[:-1])
        with pytest.raises(ValueError,match='coherent'):writer.write_window([replace(blocks[0],timestamp_ns=0),*blocks[1:]])
        writer.write_window(blocks)
        with pytest.raises(ValueError,match='discontinuous'):writer.write_window(blocks)
    finally:writer.close('stopped')
    assert inspect(tmp_path/'iq')['windows']==1


def test_failed_bulk_write_publishes_no_partial_channel_group(tmp_path):
    config=configuration();groups=list(inputs(config,windows=2));path=tmp_path/'iq'
    writer=SampleRecordingWriter(path,config);writer.write_window(groups[0])
    class FullDisk:
        def write(self,payload):raise OSError('disk full')
    writer.files['rx0_1']=FullDisk()
    with pytest.raises(OSError,match='disk full'):writer.write_window(groups[1])
    with pytest.raises(RuntimeError):writer.write_window(groups[1])
    writer.close()
    assert json.loads((path/'manifest.json').read_text())['status']=='failed'
    restored=list(iter_recorded_windows(path,allow_partial=True))
    assert len(restored)==1
    assert restored[0][0].samples.tobytes()==groups[0][0].samples.tobytes()


def test_tcp_replay_to_unchanged_music_processing_matches_original(tmp_path):
    pytest.importorskip('doa_py')
    from airsim_rf.skills.music import MusicSkill
    path,groups=archive(tmp_path)
    direct=MusicSkill(path/'receiver-config.json');restored=MusicSkill(path/'receiver-config.json')
    for blocks in groups:direct.process({b.receiver:b for b in blocks})
    received=[];commits=[]
    with socket.socket() as server,ThreadPoolExecutor(1) as pool:
        server.bind(('127.0.0.1',0));server.listen();server.settimeout(10)
        def consumer():
            connection,_=server.accept()
            with connection:
                connection.settimeout(10);pending={}
                def commit():
                    assert not pending
                    commits.append(restored.state['complete_windows'])
                for block in iter_stream(connection,validate_window=commit):
                    received.append(block);pending[block.receiver]=block
                    if len(pending)==8:restored.process(pending);pending={}
        future=pool.submit(consumer)
        result=replay(path,port=server.getsockname()[1],timeout=10)
        future.result(timeout=10)
    assert result['windows']==3 and commits==[1,2,3]
    for original,restored_block in zip([b for g in groups for b in g],received):
        assert original.timestamp_ns==restored_block.timestamp_ns
        assert original.samples.tobytes()==restored_block.samples.tobytes()
    for a,b in zip(direct.frames,restored.frames):
        for key in ('bearings','music_db','phase_rad','receiver_spectra'):assert a[key]==b[key]


def test_replay_subset_restarts_stream_offset_but_preserves_acquisition_time(tmp_path):
    path,groups=archive(tmp_path);received=[]
    with socket.socket() as server,ThreadPoolExecutor(1) as pool:
        server.bind(('127.0.0.1',0));server.listen();server.settimeout(5)
        def consumer():
            connection,_=server.accept()
            with connection:
                connection.settimeout(5);received.extend(iter_stream(connection))
        future=pool.submit(consumer)
        result=replay(path,port=server.getsockname()[1],start_window=1,stop_window=2,speed=1,timeout=5)
        future.result(timeout=5)
    assert result['windows']==1 and received[0].sample_start==0
    assert received[0].timestamp_ns==groups[1][0].timestamp_ns
    np.testing.assert_array_equal(received[0].samples,groups[1][0].samples)


def test_pacing_uses_acquisition_time_without_resampling(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import airsim_rf.sample_recording as recording
    path,_=archive(tmp_path);clock=[0.];delays=[]
    def sleep(duration):delays.append(duration);clock[0]+=duration
    monkeypatch.setattr(recording,'time',SimpleNamespace(monotonic=lambda:clock[0],sleep=sleep))
    with socket.socket() as server,ThreadPoolExecutor(1) as pool:
        server.bind(('127.0.0.1',0));server.listen();server.settimeout(5)
        def consumer():
            connection,_=server.accept()
            with connection:
                connection.settimeout(5);return list(iter_stream(connection))
        future=pool.submit(consumer)
        replay(path,port=server.getsockname()[1],speed=.5,timeout=5)
        assert len(future.result(timeout=5))==24
    np.testing.assert_allclose(delays,[.004096,.004096],rtol=0,atol=1e-12)
