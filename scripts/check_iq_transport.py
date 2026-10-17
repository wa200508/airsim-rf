"""Compare a completed independent TCP consumer with retained I/Q recordings."""
import argparse
import hashlib
import json
from pathlib import Path
from airsim_rf.recording import iter_iq_blocks


def check(recording,consumer):
    received=json.loads(Path(consumer).read_text());manifest=json.loads((Path(recording)/'manifest.json').read_text())
    if received['status']!='complete' or manifest['status']!='complete':raise ValueError('Both sides must complete')
    names={p.name.removesuffix('.sigmf-meta') for p in Path(recording).glob('*.sigmf-meta')}
    if names!=set(received['receivers']):raise ValueError('Receiver sets differ')
    frames=0
    for name,expected in received['receivers'].items():
        digest=hashlib.sha256();count=0;rate=None
        for block in iter_iq_blocks(recording,name):
            digest.update(block.samples.astype('<c8').tobytes());count+=len(block.samples);rate=block.sample_rate_hz;frames+=1
        if count!=expected['samples'] or count/rate!=expected['signal_seconds'] or digest.hexdigest()!=expected['complex64_sha256']:
            raise ValueError(f'{name}: transported samples differ from recording')
    if frames!=received['frames']:raise ValueError('Frame count differs')
    return {'status':'passed','scope':'independent TCP consumer and saved post-ADC complex64 samples match exactly',**{k:v for k,v in received.items() if k!='status'}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('recording',type=Path);parser.add_argument('consumer',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=check(args.recording,args.consumer)
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
