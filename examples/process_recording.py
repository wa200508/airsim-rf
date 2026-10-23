"""Read recorded I/Q on any CPU and pass it to your own signal processor."""
import argparse
import json
import numpy as np

from airsim_rf.recording import iter_sample_blocks


def process(samples, sample_rate_hz):
    # Replace this function with your demodulator, correlator, detector, etc.
    # samples is complex64, I+jQ, reconstructed ADC input-referred volts.
    return float(np.vdot(samples, samples).real)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    parser.add_argument('--receiver', default='rx0')
    args = parser.parse_args()
    count = 0; energy = 0.; first_time = None; fs = None
    for block in iter_sample_blocks(args.recording, args.receiver):
        first_time = block.timestamp_ns if first_time is None else first_time
        fs = block.sample_rate_hz
        energy += process(block.samples, fs)
        count += len(block.samples)
    print(json.dumps({'receiver':args.receiver, 'complex_samples':count,
        'sample_rate_hz':fs, 'signal_seconds':count/fs,
        'first_timestamp_ns':first_time, 'rms_complex_volts':float(np.sqrt(energy/count))}, indent=2))


if __name__ == '__main__':
    main()
