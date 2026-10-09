# Measured GPU performance and optimization limits

The current qualification uses Sionna RT 2.2.0 with an **explicit P100-compatible
Mitsuba 3.8.0 / Dr.Jit 1.3.1 stack**, CuPy 13.6 and CUDA 12.2. This differs from
both the production dependency pins and the earlier legacy-Sionna experiments.
CUDA/OptiX traces propagation; CuPy renders I/Q. Receivers run serially on one GPU.

Each row is 30 warmed RF fleet updates at 2 MS/s, totaling **0.250 signal seconds
per receiver**. Concurrent receiver durations are counted once. Wall/signal is
summed measured wall service divided by summed output duration, not a median
ratio. [Definitions](timing.md).

| TX × RX | Update median wall ms | Mean wall ms | Wall s / signal s |
| --- | ---: | ---: | ---: |
| 2 × 2 | 25.304 | 25.452 | 3.054 |
| 10 × 4 | 53.446 | 53.612 | 6.433 |
| 100 × 10 | 371.859 | 372.320 | 44.678 |

[Qualified collection, validation and raw cases](../results/profiling/p100-adaptive-pipeline-full-20261008/REPORT.md).
The timed operation includes source generation/copies, pose mapping, path
solving/export, all-path rendering and transfers, receiver noise/filter/ADC,
SC16 serialization, localhost HTTP acknowledgement and file write/readback.
Writes are not fsync-ed. Startup, warmup, live AirSim physics/RPC, WAN transport
and unequal-clock resampling are excluded. All measured updates miss 120 Hz.
The terrain has 800 triangles and 1,028 diffuse attempts per directed link;
physical returns vary. This is not 1,028 valid paths per link.

## What the optimizations guarantee

The production GPU path selects temporal rank using the maximum absolute Doppler
of **every** current path and the existing interpolation error bound. It still
rejects paths outside the declared range; zero-gain paths participate in range
checks. Higher Doppler requires higher rank, so the measured speedup is not a
promise for every scene. Warp groups select 8, 16 or 32 lanes from that rank;
all paths remain included. Reused source staging overwrites valid regions and
clears uncovered history/padding. Declared history/lookahead remains required.

Qualification covered changing delays, zero-gain paths, high Doppler/high rank,
boundaries, split captures, Unix epochs, subgroup widths and private inputs.
These tests establish agreement with the declared finite interpolation operator;
they do not establish calibrated RF accuracy or live simulator interoperability.
The matched previous GPU workload averaged 552.997 ms/update (66.360 wall s/signal s).
The current 372.320 ms/update costs 32.7% less under that configuration.

Delay-support trimming, alternate FFT lengths, single-precision delay mapping and
fused projection remain **disabled experimental controls**. Trimming was slower
in the support sweep; alternate FFT shapes produced small platform-dependent
gains. They are not required by the live workflow. No further scenario tuning is
being promoted as a general optimization.

[Call traces](../results/profiling/p100-call-trace-20261008/README.md),
[temporal controls](../results/profiling/p100-temporal-sweep-20261008/README.md),
[support controls](../results/profiling/p100-support-sweep-20261008/README.md) and
[warp/FFT controls](../results/profiling/p100-kernel-sweep-20261008/README.md)
preserve the evidence. GPU event spans are diagnostic and can include dispatch
gaps; synchronizing download calls can absorb earlier queued GPU work. Neither
is an independent end-to-end throughput measurement.

Remaining costs include host source copies, serial receiver dispatch and private
input transfers. GPU-resident ingestion or overlapping independent work may help,
but each would need representative workloads and explicit traffic accounting.
The next product priority is live timestamp continuity and usable recordings.
