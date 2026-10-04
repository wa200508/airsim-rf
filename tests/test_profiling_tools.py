"""Preserve profiling provenance and publish only the intended artifacts."""
from enum import IntEnum
import json
from pathlib import Path
import subprocess
import sys
import pytest
from airsim_rf.profiling import CaptureProfiler, profile_range, summarize_kernel_history
ROOT=Path(__file__).resolve().parents[1]


def test_ranges_restore_after_exception():
    profiler=CaptureProfiler();profiler.nvtx=None
    with pytest.raises(RuntimeError), profiler.activate(), profile_range('outer'):
        with profile_range('inner'): raise RuntimeError('test')
    assert [r['name'] for r in profiler.take_host_ranges()]==['inner','outer']
    with profile_range('inactive'): pass
    assert profiler.take_host_ranges()==[]


def test_event_metadata_preserves_cuda_enum_and_omits_ir():
    class Backend(IntEnum): CUDA=2
    summary=summarize_kernel_history([{'backend':Backend.CUDA,'type':'JIT','execution_time':1.25,
        'uses_optix':True,'ir':'large kernel text','cache_hit':False,'backend_time':2.}])
    assert summary['cuda_operation_count']==1
    assert summary['optix_kernel_count']==1
    assert summary['cuda_event_time_sum_ms']==1.25
    assert 'ir' not in summary['records'][0]
    json.dumps(summary)


def write_bundle(root):
    bundle=root/'results/profiling/test-run'
    for directory in ('metrics','profiles','logs','raw'): (bundle/directory).mkdir(parents=True,exist_ok=True)
    (bundle/'manifest.json').write_text(json.dumps(dict(run_id='test-run',complete=True,
        required_tasks_passed=False,gpu_status='blocked',started_utc='test',tasks=[])))
    (bundle/'environment.json').write_text(json.dumps(dict(hostname='test',python='3.12',gpu={})))
    (bundle/'profiles/cuda_preflight.json').write_text(json.dumps(dict(status='blocked',error='CUDA unavailable')))
    (bundle/'raw/large.nsys-rep').write_text('excluded raw trace')
    return bundle


def test_failed_report_and_selective_publication(tmp_path):
    scripts=tmp_path/'scripts';scripts.mkdir()
    for name in ('aggregate_gpu_profile.py','publish_gpu_results.py'):
        (scripts/name).write_text((ROOT/'scripts'/name).read_text())
    def git(*args): return subprocess.check_output(['git','-C',str(tmp_path),*args],text=True).strip()
    git('init','-q');git('config','user.name','Test');git('config','user.email','test@example.invalid')
    git('add','scripts');git('commit','-qm','Initial tools')
    bundle=write_bundle(tmp_path)
    subprocess.run([sys.executable,scripts/'publish_gpu_results.py',bundle],check=True,capture_output=True)
    report=(bundle/'REPORT.md').read_text()
    assert 'FAILED / INCOMPLETE' in report and 'CUDA unavailable' in report
    assert 'No complete CPU/CUDA pair' in report
    assert git('branch','--show-current')=='profiling/results/test-run'
    tracked=git('ls-files')
    assert 'REPORT.md' in tracked and 'large.nsys-rep' not in tracked
    assert not any('raw/' in name for name in json.loads((bundle/'checksums.json').read_text()))


def test_profiled_metrics_rejected(tmp_path):
    bundle=write_bundle(tmp_path)
    (bundle/'metrics/bad.json').write_text(json.dumps(dict(measurement_mode='instrumented_profile')))
    result=subprocess.run([sys.executable,ROOT/'scripts/aggregate_gpu_profile.py',bundle],capture_output=True,text=True)
    assert result.returncode!=0
    assert 'instrumented run cannot enter performance table' in result.stderr


def test_basis_report_excludes_instrumented_runs_and_marks_invalid_accuracy(tmp_path):
    bundle=write_bundle(tmp_path)
    manifest=json.loads((bundle/'manifest.json').read_text())
    manifest.update(scope='doppler_basis_renderer',required_tasks_passed=True,gpu_status='verified_cuda_cupy')
    (bundle/'manifest.json').write_text(json.dumps(manifest))
    # Create realistic small renderer-only records without running a benchmark.
    data=dict(scope='doppler_basis_receiver_rendering',measurement_mode='unprofiled_basis_benchmark',
        backend='cuda',arguments=dict(tx=100,rx=1,paths=1028,samples=16667),
        summary=dict(p50_ms=10.,p95_ms=11.,p99_ms=12.,max_ms=12.),captures_per_second=100.,
        misses_120hz=2,rows=[{},{}],accuracy=dict(passed=False),profile_receivers=[])
    (bundle/'profiles/basis.json').write_text(json.dumps(data))
    data.update(measurement_mode='instrumented_basis_profile',summary=dict(p50_ms=999.,p95_ms=999.,p99_ms=999.,max_ms=999.))
    (bundle/'profiles/basis_nsys.json').write_text(json.dumps(data))
    subprocess.run([sys.executable,ROOT/'scripts/aggregate_gpu_profile.py',bundle],check=True,capture_output=True)
    report=(bundle/'REPORT.md').read_text()
    assert 'FAILED / INCOMPLETE' in report and 'INVALID' in report
    assert '10.000 ms' in report and '999.000 ms' not in report
    assert 'not a ten-GPU fleet measurement' in report


def test_basis_cuda_failure_writes_a_blocked_preflight(tmp_path):
    artifact=tmp_path/'preflight.json'
    result=subprocess.run([sys.executable,ROOT/'scripts/basis_cuda_preflight.py','--output',artifact],capture_output=True,text=True)
    data=json.loads(artifact.read_text())
    if result.returncode==0:
        assert data['status']=='verified_cuda_cupy'
    else:
        assert data['status']=='blocked' and data['error']
        assert result.returncode==20
