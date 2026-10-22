"""Audit the held-out AoA example and its separately installed CPU consumer."""
import argparse
import json
from pathlib import Path
import re
import zipfile

import numpy as np

from airsim_rf.aoa_tracking import score
from airsim_rf.geometry import file_digest, read_bundle
from airsim_rf.recording import iter_iq_blocks


def audit(root):
    import sigmf
    read=lambda name:json.loads((root/name).read_text())
    baseline=read('qualified/metrics.json')
    estimates=read('qualified/estimates.json')
    isolated=read('isolated-consumer/estimates.json')
    cpu=read('isolated-consumer/installed-demo/metrics.json')
    negative=read('qualified/reversed-array-control.json')
    stress=read('specular/metrics.json')
    arrays=read('qualified/arrays.json')
    manifest=read('qualified/capture/manifest.json')
    scenario=read('qualified/scenario.json')
    _,bundle,_=read_bundle(root/'qualified/inputs/bundle')
    checks={
        'fixed_baseline_gates_pass':baseline['status']=='passed' and all(baseline['checks'].values()),
        'separate_evaluator_reproduces_metrics':score(estimates,root/'qualified/truth.json')['metrics']==baseline['metrics'],
        'isolated_installed_cpu_replay_identical':isolated==estimates,
        'consumer_reports_no_truth_or_paths':isolated['truth_or_paths_used'] is False,
        'installed_cpu_demo_passes':cpu['status']=='passed' and all(cpu['checks'].values()),
        'reversed_wiring_fails_accuracy':negative['status']=='passed' and negative['evaluation']['status']=='failed',
        'multipath_failure_retained_at_same_gate':stress['status']=='failed' and stress['checks']['bearing_rmse_below_1deg'] is False,
        'source_is_modulated_qpsk':scenario['symbol_rate_hz']==25000 and 'QPSK' in scenario['waveform'],
        'complete_supplied_trajectory_scope':manifest['status']=='complete' and manifest['scope']=='supplied_trajectory_rf_recording' and len(manifest['rows'])==100,
        'no_emitter_truth_in_capture_manifest':all(key not in json.dumps(manifest) for key in ('emitter_position','emitter_velocity','position_rf_m','velocity_rf_m_s')),
        'geometry_identity_every_window':all(row['geometry']['geometry_sha256']==bundle['scene_sha256'] and row['geometry']['sim_time_ns']==row['sim_time_ns'] for row in manifest['rows']),
        'focused_consumer_tests':bool(re.search(r'9 passed',(root/'aoa-tests-final.log').read_text())),
        'complete_cpu_suite_with_gc_boundary_fixture':bool(re.search(r'262 passed, 158 skipped',(root/'full-cpu-tests-qualified.log').read_text())),
    }
    waveform_path=root/'qualified/inputs/tx0.npy'
    waveform=np.load(waveform_path)
    checks['finite_non_tone_unit_power_source']=bool(np.isfinite(waveform).all() and abs(np.mean(abs(waveform)**2)-1)<1e-6 and np.std(abs(waveform))>.1)
    checks['source_hash_matches_recording']=file_digest(waveform_path)==scenario['waveform_sha256']==manifest['provenance']['waveform_sha256']
    channel_reports={}
    for site in arrays['sites']:
        for name in site['channels']:
            external=sigmf.fromfile(str(root/f'qualified/capture/{name}.sigmf-meta'),autoscale=False)
            external.validate()
            count=0;equal=True;clipped=False
            for index,block in enumerate(iter_iq_blocks(root/'qualified/capture',name)):
                raw=external.read_samples_in_capture(index)
                scale=external.get_capture_info(block.sample_start)['airsim_rf:volts_per_count']
                equal &= len(raw)==len(block.samples) and np.allclose(raw*scale,block.samples,rtol=2e-7,atol=0)
                clipped |= block.clipped_component_fraction!=0
                count+=len(block.samples)
            path=root/f'qualified/capture/{name}.sigmf-data'
            channel_reports[name]={'complex_samples':count,'bytes':path.stat().st_size,'sha256':file_digest(path),
                                   'official_sigmf_equal':bool(equal),'clipped':clipped}
    checks['eight_complete_unclipped_sigmf_channels']=len(channel_reports)==8 and all(c['complex_samples']==2400000 and c['bytes']==9600000 and c['official_sigmf_equal'] and not c['clipped'] for c in channel_reports.values())
    direct=read('qualified/channels.json');specular=read('specular/channels.json')
    checks['direct_paths_retained']=all(v['tx0']==1 for row in direct for v in row['retained_paths'].values())
    checks['stress_actually_retained_multiple_paths']=any(v['tx0']>1 for row in specular for v in row['retained_paths'].values())
    wheel=root/'local-build/airsim_rf-0.2.0-py3-none-any.whl'
    with zipfile.ZipFile(wheel) as archive:
        checks['wheel_matches_production_consumer_and_demo']=all(archive.read(f'airsim_rf/{name}.py')==(Path(__file__).resolve().parents[1]/f'src/airsim_rf/{name}.py').read_bytes() for name in ('aoa_tracking','aoa_example','cli'))
    checks['isolated_installed_import_confirmed']='/tmp/independent-tracker/lib/python3.12/site-packages/airsim_rf/' in (root/'isolated-consumer.log').read_text()
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,
        'scope':'single-emitter calibrated LOS supplied RF trajectory; expected multipath bearing failure is retained, not qualified as passing',
        'baseline':baseline,'specular_stress':stress,'installed_cpu_demo':cpu,
        'consumer_versions':{key:isolated[key] for key in ('doa_py','filterpy')},
        'channels':channel_reports,'waveform_sha256':file_digest(waveform_path),'wheel_sha256':file_digest(wheel),
        'arrays_sha256':file_digest(root/'qualified/arrays.json'),
        'tests_note':'262 CPU passes, 158 hardware skips with test-boundary cyclic GC. Prior native aborts and the test isolation workaround are retained in REPORT.md.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.root)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],'checks':result['checks']},indent=2))
    raise SystemExit(0 if result['status']=='passed' else 1)
