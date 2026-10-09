"""Isolated cuFFT filtering chain; diagnostics, not fleet throughput."""
import argparse
import json
from pathlib import Path
from time import perf_counter
import cupy as cp
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args=p.parse_args()
    base=cp.ones((100,17152),dtype=cp.complex128)
    rows=[]
    for rank,support in ((8,35),(8,233),(27,35),(27,233)):
        kernels=cp.ones((100,rank,support),dtype=cp.complex128)
        source=base[:,:2048+support-1]
        for size in (2100,2112,2160,2240,2250,2304,2400,2430,2500,2560,3072,4096):
            if size < source.shape[-1]:continue
            wall=[];device=[]
            for i in range(23):
                begin,end=cp.cuda.Event(),cp.cuda.Event()
                started=perf_counter();begin.record()
                private=cp.fft.fft(source,size,axis=-1)
                filtered=cp.fft.ifft(cp.fft.fft(kernels,size,axis=-1)*private[:,None,:],axis=-1)
                end.record();end.synchronize()
                elapsed=(perf_counter()-started)*1000
                if i>=3:wall.append(elapsed);device.append(float(cp.cuda.get_elapsed_time(begin,end)))
            row=dict(rank=rank,support=support,fft_size=size,n=20,wall_mean_ms=float(np.mean(wall)),
                     event_mean_ms=float(np.mean(device)),wall_median_ms=float(np.median(wall)))
            rows.append(row);print(row,flush=True)
    result=dict(scope='isolated_private_fft_filter_chain',samples_per_nominal_block=2048,sample_rate_hz=2_000_000,
        tx=100,rx=1,precision='complex128',warmup=3,iterations=20,rows=rows,
        note='Synthetic coefficients only; three cuFFT operations plus multiplication. No propagation/projection/source generation/receiver/delivery. CUDA event spans include dispatch gaps. Not an RF capture or fleet throughput.')
    args.output.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
