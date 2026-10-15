"""Process each simulated receiver block while also saving a reusable recording."""
import argparse
import numpy as np
from airsim_rf.live import run


def process(receiver_id, capture):
    # Replace this body with your own algorithm. Keep a separate state/filter
    # for each receiver_id. These are post-ADC complex I+jQ volts, not RF watts.
    samples = capture.adc_iq_volts
    rms_volts = float(np.sqrt(np.mean(abs(samples)**2)))
    print(f'{receiver_id}: epoch={capture.sim_time_ns} ns, '
          f'N={len(samples)}, fs={capture.actual_sample_rate_hz:g} Hz, '
          f'RMS={rms_volts:.6g} V', flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--pascal-compat',action='store_true')
    args=parser.parse_args()
    run(args.config,args.output,pascal_compat=args.pascal_compat,on_capture=process)
