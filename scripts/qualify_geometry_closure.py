"""Audit saved priority-1 evidence and read real captures with official SigMF.

CPU only; does not launch a simulator, generate RF samples or modify bundles.
Requires the optional geometry and SigMF dependencies used by qualification.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from airsim_rf.geometry import file_digest, geometry_digest, read_bundle
from airsim_rf.recording import iter_iq_blocks


def audit(root):
    import sigmf
    checks, captures = {}, {}
    def report(relative):
        value=json.loads((root/relative).read_text())
        checks[relative]=value['status']=='passed' and all(value.get('checks',{}).values())
        return value
    probes={name:report(name+'/report.json') for name in ('mesh-probe','final-mesh-probe','combined-mesh-probe')}
    for name,probe in (('turning','mesh-probe'),('obstruction','final-mesh-probe'),('combined','combined-mesh-probe')):
        report(name+'/motion.json');iq=report(name+'/diffuse-iq.json')
        manifest=json.loads((root/name/'capture/manifest.json').read_text())
        document,bundle,_=read_bundle(root/name/'bundle')
        identity=geometry_digest(document)
        checks[name+'_same_collision_and_capture_geometry']=(
            identity==bundle['scene_sha256']==probes[probe]['initial_guard']['geometry_sha256']
            ==manifest['provenance']['geometry_sha256'])
        checks[name+'_per_window_geometry_and_contiguous_samples']=(manifest['status']=='complete'
            and all(row['geometry']['geometry_sha256']==identity
                    and row['geometry']['sim_time_ns']==row['sim_time_ns'] for row in manifest['rows']))
        external=sigmf.fromfile(str(root/name/'capture/rx0.sigmf-meta'),autoscale=False)
        external.validate()
        matched=True;count=0
        for index,block in enumerate(iter_iq_blocks(root/name/'capture')):
            codes=external.read_samples_in_capture(index)
            scale=external.get_capture_info(block.sample_start)['airsim_rf:volts_per_count']
            matched &= len(codes)==len(block.samples) and np.allclose(codes*scale,block.samples,rtol=2e-7,atol=0)
            count+=len(block.samples)
        checks[name+'_official_sigmf_roundtrip']=bool(matched and count==iq['complex_samples'])
        captures[name]={'geometry_sha256':identity,'complex_samples':count,
                        'data_sha256':file_digest(root/name/'capture/rx0.sigmf-data'),
                        'whole_iq_nrmse':iq['whole_iq_nrmse'],'boundary_iq_nrmse':iq['boundary_iq_nrmse'],
                        'path_count_transitions':iq['path_count_transitions']}
    report('turning/turning-mounts.json')
    report('combined/diffuse-negative-control.json')
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,'captures':captures,
            'sigmf_version':sigmf.__version__, 'script_sha256':file_digest(__file__),
            'scope':'Saved shared-mesh geometry and moving-radio integration evidence; static revision boundaries, pinned stack; no physical calibration or arbitrary-world export'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    result=audit(args.directory)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if result['status']!='passed':
        raise SystemExit(1)
