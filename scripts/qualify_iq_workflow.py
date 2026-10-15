"""Exercise all scenario modes through the real recorder and user-facing reader."""
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np

from airsim_rf.live import run, validate_inputs
from airsim_rf.recording import iter_iq_blocks


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--pascal-compat',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('prepare_live',root/'examples/prepare_live_example.py')
    example=importlib.util.module_from_spec(spec);spec.loader.exec_module(example)
    reports=[]
    for mode in ('direct','specular','diffuse-angular','diffuse-surface'):
        config=example.prepare(args.output/(mode+'-inputs'),propagation=mode)
        inputs=validate_inputs(config);received=[]
        def process(name,capture):
            received.append((name,capture.sim_time_ns,capture.adc_iq_volts.copy(),dict(capture.retained_paths)))
        destination=args.output/mode
        result=run(config,destination,updates=3,pascal_compat=args.pascal_compat,on_capture=process)
        blocks=list(iter_iq_blocks(destination,'rx0'))
        if len(blocks)!=len(received):raise AssertionError('Callback/reader block counts differ')
        for block,(name,epoch,samples,_) in zip(blocks,received):
            assert name=='rx0' and epoch==block.sim_time_ns
            np.testing.assert_allclose(block.samples,samples,rtol=2e-7,atol=1e-12)
        report={'mode':mode,'status':'passed','callback_blocks':len(received),
            'complex_samples':sum(len(b.samples) for b in blocks),
            'signal_seconds':result['signal_seconds_per_receiver'],
            'wall_seconds_per_signal_second':result['wall_seconds_per_signal_second'],
            'retained_paths':[r[3] for r in received], 'propagation_options':inputs['propagation_options'],
            'scope':'real stationary Runtime to GPU SDR, synchronous processing callback, saved data and CPU reader round trip'}
        reports.append(report)
        (args.output/'workflow.json').write_text(json.dumps(reports,indent=2)+'\n')
        print(json.dumps(report),flush=True)


if __name__=='__main__':main()
