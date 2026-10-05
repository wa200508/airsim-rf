"""Prevent incomplete or instrumented P100 data from becoming qualified latency rows."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('e2e_aggregation',ROOT/'scripts/aggregate_end_to_end_profile.py')
metrics=importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


def capture(profile=False):
    data=dict(scope='rf_pipeline_end_to_end',measurement_mode=metrics.PROFILE if profile else metrics.NORMAL,
        sample_rate_hz=2_000_000,update_hz=120,rendering_backend='basis-cuda',
        hardware=dict(gpu=dict(name='Test GPU')),
        arguments=dict(tx=2,rx=2,iterations=2,samples_per_link=1028),summary={},samples=[])
    for index,value in enumerate((10.,14.)):
        row=dict(sequence=index,sim_time_ns=index*8333500,samples=16667 if index==0 else 16666,
                 retained_paths={'rx0':{'tx0':10,'tx1':12},'rx1':{'tx0':11,'tx1':14}})
        row.update({key: value for key in metrics.PIPELINE})
        if profile:
            row['total_ms']=1000*(index+1)
            receiver=dict(profile=True,backend='cuda_cupy',events=[])
            # Repeated stage labels from multiple blocks must be summed, not overwritten.
            for name in metrics.EVENTS:
                receiver['events'].extend([dict(name=name,cuda_ms=value*.4),dict(name=name,cuda_ms=value*.6)])
            row['receiver_render_metrics']=[deepcopy(receiver),deepcopy(receiver)]
        data['samples'].append(row)
    return data


def test_repeated_gpu_stages_and_unprofiled_latency_stay_separate(tmp_path):
    records=[]
    for name,profile in [('normal',False),('instrumented',True)]:
        path=tmp_path/name/'measurements.json';path.parent.mkdir()
        data=capture(profile);path.write_text(json.dumps(data))
        records.append((path,metrics.validate(data)))
    text=metrics.tables(records,link_root=tmp_path)
    normal=text.split('### Instrumented end-to-end wall timings')[0]
    assert '12.000 ± 2.828' in normal and '13.800' in normal
    assert '1500.000' not in normal
    gpu=text.split('### Repeated CUDA rendering event spans')[1]
    assert '24.000 ± 5.657' in gpu
    assert metrics.event_totals(records[1][1]['samples'][0],2)['basis.path_projection']==20


@pytest.mark.parametrize('change', ['stage','receiver','negative','gap','mode','count'])
def test_incomplete_stage_or_window_is_rejected(change):
    data=capture(True)
    if change=='stage':
        data['samples'][0]['receiver_render_metrics'][0]['events']=[]
    elif change=='receiver':
        data['samples'][0]['receiver_render_metrics'].pop()
    elif change=='negative':
        data['samples'][0]['channel_ms']=-1
    elif change=='gap':
        data['samples'][1]['sim_time_ns']+=500
    elif change=='mode':
        data['measurement_mode']='unknown'
    elif change=='count':
        data['samples'].pop()
    with pytest.raises(ValueError):
        metrics.validate(data)


def test_collection_requires_every_scenario_and_mode_and_excludes_iq_checksums(tmp_path):
    manifest=dict(complete=True,backends=['cuda'],scenarios=[[2,2]],iterations=2,tasks=[dict(status='ok')])
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    normal=tmp_path/'profiles/normal/measurements.json';normal.parent.mkdir(parents=True)
    normal.write_text(json.dumps(capture()))
    with pytest.raises(ValueError,match='Missing or duplicated'):
        metrics.aggregate(tmp_path)
    profile=tmp_path/'profiles/instrumented/measurements.json';profile.parent.mkdir()
    profile.write_text(json.dumps(capture(True)))
    raw=profile.parent/'captures';raw.mkdir();(raw/'iq.sc16').write_bytes(b'large IQ')
    metrics.aggregate(tmp_path)
    checks=json.loads((tmp_path/'checksums.json').read_text())
    assert 'profiles/instrumented/measurements.json' in checks
    assert not any('captures/' in name for name in checks)
    assert 'Repeated CUDA rendering event spans' in (tmp_path/'REPORT.md').read_text()


@pytest.mark.parametrize('cpu_only',[False,True])
def test_docker_wrapper_routes_end_to_end_and_passthrough(tmp_path,cpu_only):
    scripts=tmp_path/'scripts';scripts.mkdir()
    (scripts/'run_p100_docker.sh').write_text((ROOT/'scripts/run_p100_docker.sh').read_text())
    fake=tmp_path/'bin';fake.mkdir()
    executable=fake/'docker'
    executable.write_text(f'#!{sys.executable}\nimport json,os,sys\nwith open(os.environ["DOCKER_CALLS"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n')
    executable.chmod(0o755)
    for command in (['git','init','-q'],['git','config','user.email','test@example.invalid'],
                    ['git','config','user.name','Test'],['git','add','scripts'],['git','commit','-qm','wrapper']):
        subprocess.run(command,cwd=tmp_path,check=True)
    calls=tmp_path/'docker.jsonl'
    env=dict(os.environ,PATH=str(fake)+os.pathsep+os.environ['PATH'],DOCKER_CALLS=str(calls))
    args=['bash',str(scripts/'run_p100_docker.sh'),'--end-to-end','--run-id','test-e2e']
    if cpu_only:
        args.append('--cpu-only')
    subprocess.run(args,env=env,check=True,capture_output=True)
    build,run=[json.loads(line) for line in calls.read_text().splitlines()]
    assert 'PROFILE_BASIS_CUDA=1' in build
    assert '/opt/airsim-rf/scripts/run_end_to_end_profile.py' in run
    assert ('--gpus' in run) is not cpu_only
    assert 'DRJIT_LIBCUDA_PATH=/tmp/disabled-drjit-cuda.so' in run


def test_publisher_keeps_nested_measurements_and_omits_sc16(tmp_path):
    scripts=tmp_path/'scripts';scripts.mkdir()
    for name in ('publish_gpu_results.py','aggregate_gpu_profile.py','aggregate_end_to_end_profile.py'):
        (scripts/name).write_text((ROOT/'scripts'/name).read_text())
    bundle=tmp_path/'results/profiling/e2e-publish';bundle.mkdir(parents=True)
    manifest=dict(run_id=bundle.name,scope='rf_pipeline_end_to_end_collection',complete=True,
        backends=['cuda'],scenarios=[[2,2]],iterations=2,tasks=[dict(status='ok')])
    (bundle/'manifest.json').write_text(json.dumps(manifest))
    (bundle/'environment.json').write_text('{}')
    for name,profile in [('normal',False),('instrumented',True)]:
        path=bundle/'profiles'/name/'measurements.json';path.parent.mkdir(parents=True)
        path.write_text(json.dumps(capture(profile)))
        (path.parent/'REPORT.md').write_text('per-case report')
        raw=path.parent/'captures';raw.mkdir();(raw/'iq.sc16').write_bytes(b'keep local')
    for command in (['git','init','-q'],['git','config','user.email','test@example.invalid'],
                    ['git','config','user.name','Test'],['git','add','scripts'],['git','commit','-qm','tools']):
        subprocess.run(command,cwd=tmp_path,check=True)
    subprocess.run([sys.executable,str(scripts/'publish_gpu_results.py'),str(bundle)],check=True,capture_output=True)
    tracked=subprocess.check_output(['git','ls-files'],cwd=tmp_path,text=True)
    assert 'profiles/instrumented/measurements.json' in tracked
    assert 'profile_summary.json' in tracked and 'checksums.json' in tracked
    assert '.sc16' not in tracked


def test_instrumented_receiver_metrics_cannot_be_labeled_unprofiled():
    data=capture(True)
    data['measurement_mode']=metrics.NORMAL
    with pytest.raises(ValueError,match='unprofiled throughput'):
        metrics.validate(data)
