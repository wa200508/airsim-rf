"""Record a live scenario and forward post-ADC volts to a separate processor."""
import argparse
import json
from pathlib import Path
import socket
from airsim_rf.iq_stream import IQStreamWriter
from airsim_rf.live import run


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--timeout',type=float,default=60);parser.add_argument('--updates',type=int,default=10)
    parser.add_argument('--pascal-compat',action='store_true')
    args=parser.parse_args();config=json.loads(args.config.read_text())
    with socket.create_connection((args.host,args.port),timeout=args.timeout) as connection:
        stream=IQStreamWriter(connection,carrier_hz=config['receiver_profile']['carrier_hz'])
        run(args.config,args.output,updates=args.updates,pascal_compat=args.pascal_compat,on_capture=stream.send_capture)
        totals=stream.finish()
        print(json.dumps({'transport':'consumer acknowledged completion','sample_totals':totals}))
