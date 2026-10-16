"""Read airsim-rf I/Q using only NumPy and the official SigMF package.

Install numpy and sigmf==1.13.0; no airsim_rf, simulator or CUDA imports required.
Input must be a completed, immutable receiver .sigmf-meta/.sigmf-data pair.
"""
import argparse
import numpy as np
import sigmf


def blocks(metadata_path):
    recording=sigmf.fromfile(str(metadata_path),autoscale=False)
    recording.validate()
    fs=recording.get_global_field('core:sample_rate')
    for index,capture in enumerate(recording.get_captures()):
        codes=recording.read_samples_in_capture(index)
        volts=codes*capture['airsim_rf:volts_per_count']
        yield volts,fs,capture['airsim_rf:sim_time_ns']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('metadata')
    args=parser.parse_args()
    count=0;energy=0.;rate=None
    for iq,rate,epoch in blocks(args.metadata):
        # Replace this accumulation with your signal-processing algorithm.
        count+=len(iq);energy+=float(np.vdot(iq,iq).real)
    print(f'{count} complex samples, {count/rate:g} signal seconds, '
          f'{np.sqrt(energy/count):.9g} RMS complex volts')
