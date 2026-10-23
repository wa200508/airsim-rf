"""Portable views and generic, epoch-correct replay for arbitrary RF skills."""
from copy import deepcopy
import json
from airsim_rf.skill_display import pointer,binding,legacy_display
from airsim_rf.dashboard_recording import RecordingWriter,RecordingStore


def description(revision='1'):
    return {'schema_version':1,'id':'packet-monitor','revision':revision,'title':'Packet monitor',
        'panels':[{'id':'quality','type':'metrics','title':'SNR','items':[{'label':'SNR','value':{'path':'/snr'},'unit':'dB'}]}],
        'histories':[{'key':'quality_history','limit':2,'row':{'timestamp_ns':{'path':'/timestamp_ns'},'snr':{'path':'/snr'}}}]}


def test_opaque_skill_schema_and_history_survive_restart_and_backward_seek(tmp_path):
    identifier='0123456789abcdef'
    writer=RecordingWriter(tmp_path,identifier,{'skill_kind':'custom'},1.,100_000_000,no_render=True)
    for index in range(4):
        epoch=index*100_000_000
        producer={'sim_time_ns':epoch,'origin_ns':0,'sim_elapsed_s':index*.1,'position_rf_m':[index,0,10]}
        # These unrelated scalar fields must never be interpreted as MUSIC/PSD.
        skill={'timestamp_ns':epoch,'display':description('1' if index<3 else '2'),
               'snr':10+index,'bearings':'opaque custom field','psd':'also opaque','quality_history':['do not duplicate']}
        writer.frame(producer,skill)
    writer.status('complete')
    saved=json.loads((writer.path/'results/100000000.json').read_text())
    assert 'quality_history' not in saved and saved['display']==description()
    store=RecordingStore(tmp_path)
    earlier=store.snapshot(identifier,.2)['skill']
    assert earlier['display']==description() and earlier['snr']==12
    assert earlier['quality_history']==[{'timestamp_ns':100_000_000,'snr':11},{'timestamp_ns':200_000_000,'snr':12}]
    assert earlier['bearings']=='opaque custom field' and earlier['psd']=='also opaque'
    latest=store.snapshot(identifier)['skill']
    assert latest['display']==description('2')
    assert latest['quality_history']==[{'timestamp_ns':300_000_000,'snr':13}]
    assert store.snapshot(identifier,0)['skill']['quality_history']==[{'timestamp_ns':0,'snr':10}]


def test_pointer_projection_and_legacy_receiver_data_are_preserved():
    assert pointer({'a/b':{'~key':4}},'/a~1b/~0key')==4
    assert binding({'rows':[{'value':1},{'value':3}]},{'path':'/rows','each':'/value'})==[1,3]
    old={'psd':{'frequency_khz':[0],'density_db_v2_hz':[-150]},'waterfall':[{'psd_db':[-150]}]}
    new=legacy_display(old,{'skill_kind':'direction-finding'})
    assert new['display']['id']=='direction-finding-rf-skill'
    assert len(new['receiver_spectra'])==1
    assert new['waterfall'][0]['site_psd_db']==[[-150]]
    assert 'receiver_spectra' not in old and 'display' not in old
    assert legacy_display({'other':1},{'skill_kind':'custom'})=={'other':1}


def test_bad_history_descriptions_cannot_overwrite_metadata():
    from airsim_rf.skill_display import history_specs,history_summaries
    manifest=description()
    manifest['histories'] += [None,{'key':'display','limit':2,'row':{}},
        {'key':'timestamp_ns','row':{}},{'key':'bad_limit','limit':'invalid','row':{}}]
    specs=history_specs(manifest)
    assert [spec['key'] for spec in specs]==['quality_history']
    _,rows=history_summaries({'display':manifest,'timestamp_ns':4,'snr':3})
    assert rows=={'quality_history':{'timestamp_ns':4,'snr':3}}


def test_independent_skill_descriptions_follow_published_schema():
    import pytest
    jsonschema=pytest.importorskip('jsonschema')
    df=pytest.importorskip('df_skill.display')
    radar=pytest.importorskip('radar_skill.display')
    from pathlib import Path
    schema=json.loads((Path(__file__).parents[1]/'docs/schemas/rf-skill-display-v1.schema.json').read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    arrays={'sites':[{'id':'Site 0'},{'id':'Site 1'}]}
    for module in (df,radar):jsonschema.validate(module.describe_display(arrays),schema)
