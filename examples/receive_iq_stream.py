"""Receive one bounded TCP I/Q session and run your processing on every block."""
import argparse
import hashlib
import json
import socket
import numpy as np
from airsim_rf.sample_stream import iter_stream


def process(block):
    # Replace this function. Keep independent filter/overlap state per receiver.
    rms=float(np.sqrt(np.mean(abs(block.samples)**2)))
    print(f'{block.receiver}: {len(block.samples)} samples at {block.timestamp_ns} ns, {rms:g} RMS V',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--timeout',type=float,default=60)
    parser.add_argument('--summary',required=True)
    args=parser.parse_args();states={};frames=0
    try:
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            listener.settimeout(args.timeout);listener.bind((args.host,args.port));listener.listen(1)
            print(f'Listening on {args.host}:{args.port}',flush=True)
            connection,_=listener.accept()
            with connection:
                connection.settimeout(args.timeout)
                for block in iter_stream(connection):
                    process(block);frames+=1
                    state=states.setdefault(block.receiver,{'samples':0,'sample_rate_hz':block.sample_rate_hz,'hash':hashlib.sha256()})
                    state['samples']+=len(block.samples);state['hash'].update(block.samples.astype('<c8').tobytes())
        report={'status':'complete','frames':frames,'receivers':{name:{'samples':s['samples'],
            'signal_seconds':s['samples']/s['sample_rate_hz'],'complex64_sha256':s['hash'].hexdigest()} for name,s in states.items()}}
    except BaseException as error:
        report={'status':'failed','frames':frames,'error':str(error)}
        raise
    finally:
        from pathlib import Path
        Path(args.summary).write_text(json.dumps(report,indent=2)+'\n')
