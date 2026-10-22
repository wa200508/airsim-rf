"""Installed entry point for complete examples, preflight and recording consumption."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    example=sub.add_parser('example',help='Generate complete simulator, shared-geometry and waveform inputs')
    example.add_argument('--output',required=True,type=Path)
    example.add_argument('--address',default='127.0.0.1')
    example.add_argument('--geometry',choices=('shared','ground'),default='shared')
    example.add_argument('--propagation',choices=('direct','specular','diffuse-angular','diffuse-surface'),default='specular')
    preflight=sub.add_parser('preflight',help='Validate a capture plan without connecting to the simulator')
    preflight.add_argument('--config',required=True,type=Path)
    preflight.add_argument('--updates',type=int,default=10)
    preflight.add_argument('--advance-ns',type=int,default=10_000_000)
    preflight.add_argument('--max-samples',type=int,default=2_000_000)
    preflight.add_argument('--output',type=Path,help='Check a proposed new recording path and available disk space')
    preflight.add_argument('--gpu',action='store_true',help='Also run CUDA/OptiX and CuPy health checks; still no server contact')
    preflight.add_argument('--pascal-compat',action='store_true')
    demo=sub.add_parser('track-demo',help='Generate propagated QPSK array recordings and run MUSIC/emitter tracking (supplied trajectory)')
    demo.add_argument('--output',required=True,type=Path)
    demo.add_argument('--backend',choices=('cpu','cuda'),default='cpu')
    demo.add_argument('--windows',type=int,default=100)
    demo.add_argument('--reflection',action='store_true',help='Add first-order specular paths as a multipath stress case')
    demo.add_argument('--pascal-compat',action='store_true')
    tracker=sub.add_parser('track',help='Independent CPU MUSIC/track consumer for completed coherent array recordings')
    tracker.add_argument('recording',type=Path)
    tracker.add_argument('--arrays',required=True,type=Path)
    tracker.add_argument('--output',required=True,type=Path)
    plots=sub.add_parser('music-plots',help='Plot recorded I/Q frequency spectra and MUSIC processing diagnostics on CPU')
    plots.add_argument('recording',type=Path)
    plots.add_argument('--arrays',required=True,type=Path)
    plots.add_argument('--output',required=True,type=Path)
    for name,help_text in (('inspect','Validate completed recordings and summarize spectrum'),('process','Read blocks and report input-referred RMS volts')):
        tool=sub.add_parser(name,help=help_text)
        tool.add_argument('recording',type=Path)
        if name=='process':
            tool.add_argument('--receiver',default='rx0')
    args=parser.parse_args()
    try:
        if args.command=='example':
            from .example import prepare
            result={'status':'prepared','configuration':str(prepare(args.output,address=args.address,
                    propagation=args.propagation,geometry=args.geometry).resolve())}
        elif args.command=='track-demo':
            from .aoa_example import run
            result=run(args.output,backend=args.backend,windows=args.windows,reflection=args.reflection,pascal_compat=args.pascal_compat)
            print(json.dumps(result,indent=2))
            return 0 if result['status']=='passed' else 1
        elif args.command=='track':
            from .aoa_tracking import consume
            result=consume(args.recording,args.arrays)
            with args.output.open('x') as stream:stream.write(json.dumps(result,indent=2)+'\n')
            result={'status':result['status'],'estimates':str(args.output),'windows':len(result['rows'])}
        elif args.command=='music-plots':
            from .music_plots import plot_recording
            result=plot_recording(args.recording,args.arrays,args.output)
        elif args.command=='preflight':
            from .preflight import check
            result=check(args.config,updates=args.updates,advance_ns=args.advance_ns,
                         max_samples=args.max_samples,output=args.output,gpu=args.gpu,pascal_compat=args.pascal_compat)
        elif args.command=='inspect':
            from .inspection import inspect
            result=inspect(args.recording)
        else:
            import numpy as np
            from .recording import iter_iq_blocks
            count=0;energy=0.
            for block in iter_iq_blocks(args.recording,args.receiver):
                count+=len(block.samples)
                energy+=float(np.vdot(block.samples,block.samples).real)
            result={'receiver':args.receiver,'complex_samples':count,'sample_rate_hz':block.sample_rate_hz,
                    'signal_seconds':count/block.sample_rate_hz,'rms_complex_volts':float(np.sqrt(energy/count))}
        print(json.dumps(result,indent=2))
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,ImportError) as error:
        print(f'airsim-rf: {error}',file=sys.stderr)
        return 2
    return 0


if __name__=='__main__':
    raise SystemExit(main())
