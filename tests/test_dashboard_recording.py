"""Durable recording and replay without simulation, a GPU, or browser polling."""
import importlib.util
import json
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('recording_stdlib',Path(__file__).resolve().parents[1]/'src/airsim_rf/dashboard_recording.py')
recording=importlib.util.module_from_spec(spec);spec.loader.exec_module(recording)
ID='0123456789abcdef'


def make_writer(tmp_path,identifier=ID,no_render=False):
    return recording.RecordingWriter(tmp_path/'replays',identifier,{'terrain':'shared DEM'},20.,120000000,no_render=no_render)


def write_frame(writer,index,with_camera=True):
    epoch=index*120000000;key=ID+'-'+str(epoch)
    p={'sim_time_ns':epoch,'origin_ns':0,'sim_elapsed_s':index*.12,'position_rf_m':[index,0,200],
        'geometry_sha256':'scene','presentation_session':writer.manifest['id'],'windows':index+1,'history':['exclude duplicated history']}
    s={'sim_time_ns':epoch,'complete_windows':index+1,'payload_bytes':(index+1)*15360000,'sample_start':index*240000,
        'bearings':[{'angle_deg':index,'detected':True}], 'psd':{'frequency_khz':[0,1],'density_db_v2_hz':[index,index+1]},
        'music_db':[[index,0]],'history':['exclude history'],'waterfall':['exclude waterfall']}
    writer.frame(p,s)
    if with_camera:writer.camera({'key':key,'sim_time_ns':epoch,'geometry_sha256':'scene'},b'camera '+str(index).encode())
    return p,s


def test_record_without_a_browser_and_replay_after_restart_with_backward_seek(tmp_path):
    writer=make_writer(tmp_path)
    for index in range(4):write_frame(writer,index)
    writer.status('complete')
    # A completely new reader; no producer, skill, simulator or browser exists.
    store=recording.RecordingStore(tmp_path/'replays')
    last=store.snapshot(ID)
    assert last['producer']['position_rf_m']==[3,0,200]
    assert last['playback']['computed_s']==pytest.approx(.48)
    earlier=store.snapshot(ID,.12)
    assert earlier['skill']['complete_windows']==earlier['producer']['windows']==2
    assert earlier['skill']['payload_bytes']==30720000
    assert earlier['skill']['psd']['density_db_v2_hz']==[1,2]
    assert [row['sim_time_ns'] for row in earlier['skill']['waterfall']]==[0,120000000]
    assert len(earlier['producer']['history'])==len(earlier['skill']['history'])==2
    assert 'recording='+ID in earlier['camera']['url']
    assert store.snapshot(ID,0)['producer']['position_rf_m']==[0,0,200]
    assert store.snapshot(ID,999)['producer']['position_rf_m']==[3,0,200]
    assert store.snapshot(ID,-999)['producer']['position_rf_m']==[0,0,200]
    saved=json.loads((writer.path/'frames/120000000.json').read_text())
    assert 'history' not in saved['producer'] and 'skill' not in saved
    result=json.loads((writer.path/'results/120000000.json').read_text())
    assert 'history' not in result and 'waterfall' not in result and result['timestamp_ns']==120000000


def test_full_recording_outlives_live_128_frame_retention_and_bounds_reader_cache(tmp_path):
    writer=make_writer(tmp_path)
    for index in range(140):write_frame(writer,index)
    store=recording.RecordingStore(tmp_path/'replays')
    assert store.snapshot(ID,0)['camera']['available']
    assert store.snapshot(ID)['playback']['playable_frames']==140
    for index in range(40):store.snapshot(ID,index*.12)
    assert len(store.frames)==32
    assert len(list((writer.path/'camera').glob('*.jpg')))==140


def test_late_camera_creates_pair_and_temporary_or_orphan_files_are_ignored(tmp_path):
    writer=make_writer(tmp_path);write_frame(writer,0,False)
    (writer.path/'frames/120000000.json.tmp').write_text('interrupted')
    (writer.path/'camera'/f'{ID}-240000000.jpg').write_bytes(b'orphan image')
    store=recording.RecordingStore(tmp_path/'replays')
    assert store.snapshot(ID)['playback']['playable_frames']==0
    writer.camera({'key':ID+'-0','sim_time_ns':0,'geometry_sha256':'scene'},b'late camera')
    paired=store.snapshot(ID)
    assert paired['synchronization']['offset_ms']==0
    assert paired['playback']['playable_frames']==1
    # Simulate death after publishing a frame but before publishing its count.
    manifest=json.loads((writer.path/'manifest.json').read_text());manifest.update(frame_count=0,computed_s=0)
    recording.atomic_json(writer.path/'manifest.json',manifest)
    assert store.snapshot(ID)['playback']['computed_s']==pytest.approx(.12)


def test_scene_or_clock_mismatch_is_not_playable_and_epochs_must_agree(tmp_path):
    writer=make_writer(tmp_path);p,s=write_frame(writer,0,False)
    writer.camera({'key':ID+'-0','sim_time_ns':0,'geometry_sha256':'different'},b'wrong scene')
    writer.camera({'key':ID+'-120000000','sim_time_ns':120000000,'geometry_sha256':'scene'},b'too far ahead')
    assert recording.RecordingStore(tmp_path/'replays').snapshot(ID)['playback']['playable_frames']==0
    with pytest.raises(ValueError,match='epochs'):writer.frame(p,{**s,'sim_time_ns':1})


def test_partial_runs_and_previous_missions_remain_playable(tmp_path):
    first=make_writer(tmp_path);write_frame(first,0);first.status('stopped')
    second=make_writer(tmp_path,'fedcba9876543210',True);write_frame(second,1,False);second.status('failed',error='interrupted')
    store=recording.RecordingStore(tmp_path/'replays')
    assert len(store.list())==2
    assert store.snapshot(ID)['playback']['status']=='stopped'
    replay=store.snapshot('fedcba9876543210')
    assert replay['no_render'] and not replay['camera']['available']
    assert replay['skill']['complete_windows']==2
    for value in ('../frames','../../etc','',ID+'/..'):
        with pytest.raises(ValueError):store.snapshot(value)


def test_seek_uses_integer_epochs_despite_floating_point_elapsed_time(tmp_path):
    writer=make_writer(tmp_path,no_render=True)
    for epoch in (0,120000000,240000000):
        writer.frame({'sim_time_ns':epoch,'origin_ns':0,'sim_elapsed_s':epoch*1e-9,'position_rf_m':[epoch,0,200]},
            {'sim_time_ns':epoch,'complete_windows':epoch//120000000+1})
    assert recording.RecordingStore(tmp_path/'replays').snapshot(ID,.24)['skill']['complete_windows']==3


def test_independent_source_progress_precedes_late_application_result(tmp_path):
    writer=make_writer(tmp_path,no_render=True)
    writer.source_frame({'sim_time_ns':0,'origin_ns':0,'sim_elapsed_s':0.,'position_rf_m':[0,0,200]})
    store=recording.RecordingStore(tmp_path/'replays')
    pending=store.snapshot(ID)['playback']
    assert pending['computed_s']==pytest.approx(.12)
    assert pending['frame_count']==1 and pending['playable_frames']==0
    recording.atomic_json(writer.path/'results/0.json',{'timestamp_ns':0,'complete_windows':1})
    assert store.snapshot(ID)['playback']['playable_frames']==1


def test_existing_version_one_archive_remains_playable(tmp_path):
    writer=make_writer(tmp_path,no_render=True);p,s=write_frame(writer,0,False)
    recording.atomic_json(writer.path/'frames/0.json',{'producer':p,'skill':s})
    manifest=json.loads((writer.path/'manifest.json').read_text());manifest['schema_version']=1
    recording.atomic_json(writer.path/'manifest.json',manifest)
    for path in (writer.path/'results').iterdir():path.unlink()
    (writer.path/'results').rmdir()
    replay=recording.RecordingStore(tmp_path/'replays').snapshot(ID)
    assert replay['skill']['complete_windows']==1
    assert replay['playback']['playable_frames']==1


def test_replay_keeps_each_receiver_spectrum_and_its_own_waterfall(tmp_path):
    writer=make_writer(tmp_path,no_render=True)
    for index in range(2):
        p,s=write_frame(writer,index,False)
        s['receiver_spectra']=[{'site_id':f'site{i}','receiver':f'site{i}_e0','element':0,
            'psd':{'frequency_khz':[0,1],'density_db_v2_hz':[index-20*i,index+1-20*i]}} for i in range(2)]
        writer.frame(p,s)
    store=recording.RecordingStore(tmp_path/'replays')
    replay=store.snapshot(ID)
    assert replay['skill']['receiver_spectra'][1]['psd']['density_db_v2_hz']==[-19,-18]
    assert [row['site_psd_db'][1] for row in replay['skill']['waterfall']]==[[-20,-19],[-19,-18]]
    earlier=store.snapshot(ID,0)
    assert earlier['skill']['receiver_spectra'][1]['psd']['density_db_v2_hz']==[-20,-19]
