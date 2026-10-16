"""Check core SigMF validation and independent raw/scaled sample readback."""
import argparse
import json
from pathlib import Path
import numpy as np
import sigmf
from airsim_rf.recording import iter_iq_blocks


def qualify(directory,receiver):
    directory=Path(directory)
    standard=sigmf.fromfile(str(directory/f'{receiver}.sigmf-meta'),autoscale=False)
    standard.validate()
    captures=standard.get_captures();count=0
    for index,block in enumerate(iter_iq_blocks(directory,receiver)):
        raw=standard.read_samples_in_capture(index)
        own_raw=block.samples/captures[index]['airsim_rf:volts_per_count']
        np.testing.assert_allclose(raw,own_raw,rtol=2e-7,atol=2e-4)
        np.testing.assert_allclose(raw*captures[index]['airsim_rf:volts_per_count'],block.samples,rtol=2e-7,atol=1e-12)
        assert captures[index]['airsim_rf:sim_time_ns']==block.sim_time_ns
        count+=len(raw)
    assert index+1==len(captures)
    return {'status':'passed','sigmf_version':sigmf.__version__,'receiver':receiver,
        'windows':len(captures),'complex_samples':count,
        'signal_seconds':count/standard.get_global_field('core:sample_rate'),
        'scope':'official SigMF core validation and raw-code/voltage/timestamp comparison; no external SDR application'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    parser.add_argument('--receiver',default='rx0');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=qualify(args.directory,args.receiver)
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
