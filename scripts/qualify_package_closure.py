"""Audit local package acceptance artifacts and independently read live I/Q."""
import argparse
import json
from pathlib import Path
import re
import zipfile

import numpy as np

from airsim_rf.geometry import file_digest, read_bundle
from airsim_rf.recording import iter_iq_blocks


def audit(root):
    import sigmf
    read=lambda name:json.loads((root/name).read_text())
    fresh=read('clean-install-final/report.json')
    image=read('container-wheel/report.json')
    preflight=read('live-preflight.json')
    manifest=read('live-capture/manifest.json')
    inspection=read('live-inspection.json')
    processed=read('live-processing.json')
    checks={'fresh_dependency_install_and_wheel_commands':fresh['status']=='passed' and all(fresh['checks'].values()),
            'documented_container_wheel_commands':image['status']=='passed' and all(image['checks'].values()),
            'full_standard_cpu_suite':bool(re.search(r'253 passed, 158 skipped', (root/'full-standard-cpu-tests.log').read_text())),
            'focused_gpu_suite':bool(re.search(r'3 passed, 132 deselected',(root/'focused-gpu-tests.log').read_text())),
            'cuda_optix_and_cupy_preflight':preflight['backend']['status']=='passed',
            'preflight_did_not_contact_server':preflight['server_contacted'] is False,
            'live_recording_complete':manifest['status']=='complete' and len(manifest['rows'])==10,
            'live_inspection_passed':inspection['status']=='passed',
            'planned_and_actual_sample_counts_match':inspection['receivers']['rx0']['complex_samples']==preflight['plan']['complex_samples_per_receiver']==240000,
            'both_consumers_read_expected_duration':processed['complex_samples']==240000 and processed['signal_seconds']==.12,
            'expected_data_bytes':inspection['receivers']['rx0']['data_bytes']==960000}
    observed=inspection['receivers']['rx0']
    checks['tone_peak_within_one_fft_bin']=abs(observed['final_window_peak_baseband_hz']-150000)<=observed['frequency_bin_spacing_hz']
    _,bundle,_=read_bundle(root/'live-inputs/bundle')
    checks['geometry_identity_and_epoch_per_window']=all(row['geometry']['geometry_sha256']==bundle['scene_sha256']
        and row['geometry']['sim_time_ns']==row['sim_time_ns'] for row in manifest['rows'])
    external=sigmf.fromfile(str(root/'live-capture/rx0.sigmf-meta'),autoscale=False)
    external.validate()
    equal=True;count=0
    for index,block in enumerate(iter_iq_blocks(root/'live-capture')):
        codes=external.read_samples_in_capture(index)
        scale=external.get_capture_info(block.sample_start)['airsim_rf:volts_per_count']
        equal &= len(codes)==len(block.samples) and np.allclose(codes*scale,block.samples,rtol=2e-7,atol=0)
        count+=len(block.samples)
    checks['official_sigmf_reads_actual_capture']=bool(equal and count==240000)
    meta=read('live-capture/rx0.sigmf-meta')
    checks['no_adc_clipping']=all(c['airsim_rf:clipped_component_fraction']==0 for c in meta['captures'])
    wheel=root/'local-build/airsim_rf-0.2.0-py3-none-any.whl'
    with zipfile.ZipFile(wheel) as archive:
        names=archive.namelist()
        checks['wheel_includes_all_example_assets']=all('airsim_rf/assets/'+name in names for name in
            ('ground.xml','ground.ply','shared-mesh-world.usda','shared-mesh-world.rf.json'))
        checks['wheel_includes_license_and_notices']=any(name.endswith('/licenses/LICENSE') for name in names) and any(name.endswith('/licenses/THIRD_PARTY_NOTICES.md') for name in names)
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,
            'wheel_sha256':file_digest(wheel),'live_iq_sha256':file_digest(root/'live-capture/rx0.sigmf-data'),
            'cpu_suite':{'passed':253,'skipped':158,'skip_scope':'CUDA/hardware cases in CPU-only environment'},
            'gpu_suite':{'passed':3,'deselected':132,'scope':'bounded selected P100 compatibility and renderer checks'},
            'scope':'Local Linux/Python 3.12 package usability and installed-wheel integration; no publication/delivery, downstream modulated consumer or new physical calibration',
            'script_sha256':file_digest(__file__)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    result=audit(args.directory)
    with args.output.open('x') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if result['status']!='passed':raise SystemExit(1)
