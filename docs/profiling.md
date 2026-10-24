[Documentation](README.md) · [Scenarios](../scenarios/README.md) · [Run dashboard](dashboard.md)

# Profiling, update rate and latency

**Neither current dashboard scenario has a measured whole-flight real-time
qualification.** A configured 4 ms or 120 ms acquisition window describes
simulation/signal time, not the wall time needed to generate or display it.
This page is the timing entry point; the stage tables below are generated from
raw evidence rather than copied estimates.

| Current demo | Signal generated per update | Current live dashboard CPU/GPU latency |
| --- | --- | --- |
| [Direction finding](../scenarios/drone-orbit/README.md) | 120 ms, continuous 2 MS/s per antenna channel | Not characterized for the current low-terrain/noise settings |
| [FMCW radar](../scenarios/mmwave-radar/README.md) | 4 ms, 100 chirps; skill uses a 64-chirp CPI | Not characterized for the current low-terrain/noise settings |

## Read these numbers in context

The tables contain **different recorded workloads**, not a CPU-versus-GPU
comparison of the same current demo:

- **P100 one-way fleet:** 30 warmed updates, 2 MS/s, 1,028 diffuse attempts per
  directed link in an older low-relief benchmark scene. Ten RX jobs run serially
  on one GPU. Includes private source buffers, pose mapping, CUDA propagation,
  GPU I/Q rendering/transfers, receiver processing and loopback delivery/readback.
  Excludes live AirSim physics/RPC, camera, skill analysis, startup and WAN work.
  [Full collection, stack and qualification](../results/profiling/p100-adaptive-pipeline-full-20261008/REPORT.md).
- **CPU first-order radar:** ten warmed, instrumented 4 ms RF-only windows on
  an AMD EPYC 9V74 with a two-core quota. Includes per-chirp direct visibility,
  NumPy IF synthesis, noise/ADC and gate packing. Other includes geometry
  preparation, poses, metadata and receiver work not separated by this harness.
  Excludes AirSim, camera, skill FFT, transport and recording. The fixed viewpoints
  predate low-terrain flight. [Original report and scope](../results/reviews/first-order-radar-20261023/REPORT.md).
  The 1,024-valid-scatterer row is a point-cloud stress, not the terrain demo.

Sample SD uses n−1; p95 uses linear interpolation. Independently calculated stage
medians/p95 do not add to the total's statistic. Missing stages are not zero.
CPU radar has no separate Sionna CIR-export stage; visibility and closed-form
first-order echo construction replace that operation. IF rendering stays on the
host even if radar visibility uses CUDA; no GPU radar speedup is inferred here.

<!-- BEGIN PROFILING OVERVIEW -->

## Median ± sample SD

Milliseconds per named operation. **—** = unmeasured; **in other** = included in the Other column; **N/A** = no separate stage in this model.

| Configuration / raw data | Signal ms | n | Pose / truth | Private TX sources | Channel / visibility | I/Q / IF synthesis | RX filter / noise / ADC | Other | Delivery / storage | Total | Wall s / signal s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [P100 one-way 2 TX / 2 RX, 2026-10-08](../results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 8.333 | 30 | 0.001 ± 0.000 | 0.838 ± 0.118 | 8.814 ± 0.501 | 10.924 ± 0.348 | 1.371 ± 0.063 | 1.334 ± 0.097 | 1.800 ± 0.197 | 25.304 ± 0.841 | 3.054 |
| [P100 one-way 10 TX / 4 RX, 2026-10-08](../results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 8.333 | 30 | 0.001 ± 0.000 | 3.902 ± 0.225 | 10.705 ± 0.641 | 27.753 ± 0.538 | 2.893 ± 0.138 | 4.628 ± 0.241 | 3.189 ± 0.261 | 53.446 ± 1.281 | 6.433 |
| [P100 one-way 100 TX / 10 RX, 2026-10-08](../results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 8.333 | 30 | 0.001 ± 0.000 | 37.918 ± 0.502 | 29.893 ± 1.380 | 220.965 ± 4.706 | 8.727 ± 1.039 | 66.255 ± 3.536 | 7.264 ± 0.568 | 371.859 ± 6.483 | 44.678 |
| [CPU radar clear-targets, 2026-10-23](../results/reviews/first-order-radar-20261023/clear-targets.json) | 4.000 | 10 | in other | N/A | 9.111 ± 0.254 | 10.726 ± 0.591 | in other | 36.322 ± 1.698 | — | 55.992 ± 2.360 | 14.145 |
| [CPU radar masked-targets, 2026-10-23](../results/reviews/first-order-radar-20261023/masked-targets.json) | 4.000 | 10 | in other | N/A | 8.790 ± 0.520 | 5.968 ± 0.399 | in other | 34.772 ± 1.750 | — | 49.574 ± 2.370 | 12.501 |
| [CPU radar clear-clutter, 2026-10-23](../results/reviews/first-order-radar-20261023/clear-clutter.json) | 4.000 | 10 | in other | N/A | 14.008 ± 0.688 | 244.349 ± 6.231 | in other | 82.314 ± 3.270 | — | 340.865 ± 9.497 | 85.491 |
| [CPU radar masked-clutter, 2026-10-23](../results/reviews/first-order-radar-20261023/masked-clutter.json) | 4.000 | 10 | in other | N/A | 14.220 ± 0.338 | 207.716 ± 3.249 | in other | 77.556 ± 2.609 | — | 298.803 ± 5.372 | 74.463 |
| [CPU radar 1024-valid-scatterers-targets, 2026-10-23](../results/reviews/first-order-radar-20261023/1024-valid-scatterers-targets.json) | 4.000 | 10 | in other | N/A | 26.553 ± 1.993 | 655.727 ± 33.223 | in other | 1228.528 ± 75.710 | — | 1912.200 ± 104.753 | 481.071 |

## 95th percentile

Milliseconds per named operation. **—** = unmeasured; **in other** = included in the Other column; **N/A** = no separate stage in this model.

| Configuration / raw data | Signal ms | n | Pose / truth | Private TX sources | Channel / visibility | I/Q / IF synthesis | RX filter / noise / ADC | Other | Delivery / storage | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [P100 one-way 2 TX / 2 RX, 2026-10-08](../results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 8.333 | 30 | 0.002 | 1.114 | 9.880 | 11.620 | 1.463 | 1.536 | 2.197 | 27.123 |
| [P100 one-way 10 TX / 4 RX, 2026-10-08](../results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 8.333 | 30 | 0.002 | 4.394 | 11.954 | 28.798 | 3.145 | 5.029 | 3.759 | 56.101 |
| [P100 one-way 100 TX / 10 RX, 2026-10-08](../results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 8.333 | 30 | 0.002 | 38.706 | 33.166 | 228.522 | 11.021 | 73.656 | 8.521 | 384.061 |
| [CPU radar clear-targets, 2026-10-23](../results/reviews/first-order-radar-20261023/clear-targets.json) | 4.000 | 10 | in other | N/A | 9.499 | 11.623 | in other | 39.408 | — | 60.255 |
| [CPU radar masked-targets, 2026-10-23](../results/reviews/first-order-radar-20261023/masked-targets.json) | 4.000 | 10 | in other | N/A | 9.642 | 6.707 | in other | 37.774 | — | 53.732 |
| [CPU radar clear-clutter, 2026-10-23](../results/reviews/first-order-radar-20261023/clear-clutter.json) | 4.000 | 10 | in other | N/A | 15.180 | 255.884 | in other | 86.778 | — | 357.114 |
| [CPU radar masked-clutter, 2026-10-23](../results/reviews/first-order-radar-20261023/masked-clutter.json) | 4.000 | 10 | in other | N/A | 14.542 | 209.259 | in other | 81.017 | — | 304.198 |
| [CPU radar 1024-valid-scatterers-targets, 2026-10-23](../results/reviews/first-order-radar-20261023/1024-valid-scatterers-targets.json) | 4.000 | 10 | in other | N/A | 29.883 | 719.405 | in other | 1365.293 | — | 2097.545 |

<!-- END PROFILING OVERVIEW -->

## How close to real time?

A 120 Hz deadline is **8.333 ms per update**. The recorded P100 100-TX / 10-RX
fleet median is about **372 ms**, with **44.678 wall seconds per simulated signal
second** over the measured series. Every update in that series misses 120 Hz.
The 10-TX / 4-RX case costs 6.433 wall seconds per signal second in that workload.
These are RF-pipeline costs; a full simulator/skill/display loop adds work.
They are not estimates for the two current dashboard missions.

The final table column divides **summed wall time by summed signal duration per
concurrent receiver**, not by added receiver durations or a ratio of medians.
A value above 1 means slower than real time for that timer's scope. Use mean or
summed costs for any extrapolation and retain the workload assumptions.
Renderer-only microbenchmarks, short isolated sampling sweeps and older quadratic
radar results do not establish complete-flight speed.

**Latency** additionally includes sample accumulation, interpolation lookahead,
queueing, skill computation, recording and camera pairing outside the timer.
The live dashboard gates simulation advance on complete-window acknowledgement
and holds camera/plots at a coherent timestamp; smooth playback is not proof of
real-time generation. [Timing definitions](timing.md).

## Measure your machine

Run the dashboard and read its measured simulation/wall ratio and synchronized
latency. Preserve the scenario snapshot, image revisions, hardware, clocks,
window/sample counts and logs. A full mission measurement must include simulator,
source, transport, skill and observer/recording costs, plus startup separately.

For the repeated CPU radar RF-window benchmark:

```bash
python benchmarks/benchmark_first_order_radar.py --iterations 10 --output /work/radar-profile
```

For GPU/fleet collection, use the [supported setup and profiling commands](setup.md#complete-rf-benchmark),
`scripts/run_end_to_end_profile.py` and `scripts/aggregate_end_to_end_profile.py`.
The `profiling/p100` branch retains its dedicated run scripts; match the recorded
scene, model, samples, paths, private TX inputs and stack before comparing gains.
[Rendering implementation/optimization boundaries](rendering.md).

Regenerate and verify this page's tables with:

```bash
python scripts/update_profiling_overview.py
python scripts/update_profiling_overview.py --check
```

## Evidence beyond the main tables

- [All recorded normalized measurements](measurements.md): generated raw-data catalog, including historical and failed qualification.
- [Timing conventions](timing.md): clocks, statistics, scope and latency definitions.
- [P100 optimization limits](performance.md): dependency-specific controls and matched comparisons.
- [Clutter sampling sweep](../results/reviews/clutter-sampling-sweep-20261023/REPORT.md): single CPU captures across budgets, not repeated fleet latency.
- [Historical runtime studies](archive/runtime.md): dated experiments and earlier estimates.
