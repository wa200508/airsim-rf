# Current runtime: measured results, estimates and excluded work

**Timing scope:** Mixed scope or architecture/reference document; each workload/table retains its stated timed operation. [Common measurement definitions](TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.



Updated **2026-10-08**. Timings follow [one measurement convention](TIMING_CONVENTIONS.md); historical results remain labeled by their operation and configuration.

The latest qualified **100-TX × 10-RX RF fleet update** takes **371.859 ms median wall service time** (p95 recorded in the linked report) to produce ~8.333 ms of signal per receiver. Receivers execute sequentially on one P100. CUDA/OptiX propagation and CUDA rendering are included, together with host source preparation, receiver processing and loopback HTTP/file readback. This is a trajectory-source RF benchmark, excluding live AirSim physics/RPC, WAN workers and startup; thirty measured updates cover **0.250 simulated seconds**, consuming **11.1696 wall seconds**, or **44.68 wall seconds per simulated signal second**. All thirty miss the 120-Hz deadline. See [measurement definitions](TIMING_CONVENTIONS.md) and [the measured configuration](results/profiling/p100-adaptive-pipeline-full-20261008/FINDINGS.md).

The older 843.630 ms result used LLVM CPU propagation and another dependency stack. Treat it as a cross-configuration comparison, not an isolated optimization gain. The synthetic renderer-only results below have a different scope and path workload.

## Comparable continuous-I/Q renderer measurements

Each call produces **16,667 complex samples at 2 MS/s** into one receiver,
approximately 8.3335 ms of signal. The scene-update target is **120 Hz**, giving
an 8.3333 ms service budget and 72,000 calls for ten simulated minutes. The
extra fractional sample per window is negligible for these conversions; the fleet-update scheduler now alternates sample counts to account for them exactly.

Every link contains **1,028 valid paths**. Inputs are arbitrary sampled I/Q,
with private buffers and transforms per directed link. All cases use FP64 /
complex128, 32-tap finite interpolation, a declared 100-microsecond delay bound,
physical Doppler bounds of ±2,500 Hz and temporal tolerance 1e-10. Doppler
phase evolves per output sample; source clocks are equal.

These measurements qualify only the declared delay/Doppler support. Wider
support, more paths or unequal sample clocks require separate measurements;
basis rank and filter costs can grow substantially. They do not establish a
uniform runtime for every arbitrary waveform and scene.

<!-- BEGIN MEASURED RUNTIME TABLE -->

| Backend / TX → RX | Renderer-call wall median (n=30) | p95 | Wall seconds / signal second | Estimated wall time for 600 signal seconds |
| --- | ---: | ---: | ---: | ---: |
| [CPU, 100 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_100tx_1rx.json) | 1610.09 ms | 1700.36 ms | 194.05× | 32.34 h |
| [P100 CUDA, 100 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json) | 56.17 ms | 59.65 ms | 6.80× | 68.00 min |
| [CPU, 4 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_4tx_1rx.json) | 78.49 ms | 84.62 ms | 9.45× | 94.49 min |
| [P100 CUDA, 4 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json) | 5.68 ms | 6.05 ms | 0.69× | 6.87 min |
| [CPU, 1 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_1tx_1rx.json) | 21.87 ms | 23.05 ms | 2.64× | 26.45 min |
| [P100 CUDA, 1 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json) | 5.51 ms | 6.14 ms | 0.67× | 6.69 min |

<!-- END MEASURED RUNTIME TABLE -->

Median/p95 describe one warmed, synchronized, preloaded-window renderer call.
**Wall seconds / signal second = mean call milliseconds / 8.3335 ms.** A ratio of
6.80× means 6.80 wall-clock seconds of rendering work per simulated second;
0.69× means renderer throughput has headroom, not that the complete simulation
has achieved real time. Ten-minute costs multiply the mean of 30 timed windows
by 72,000; they are extrapolations, not ten-minute flight measurements.

Evidence: [qualified collection](results/profiling/p100-basis-optimized-full-20261004/REPORT.md),
[findings](results/profiling/p100-basis-optimized-full-20261004/FINDINGS.md),
[hardware record](results/profiling/p100-basis-optimized-full-20261004/environment.json).
The CPU host was **AMD Ryzen 7 8700G with Radeon 780M graphics**, with 16 logical
CPUs visible and no cgroup CPU quota. The CPU renderer requested **two FFT
workers**; this is not a two-core quota or an all-core Ryzen benchmark. The
GPU was a **Tesla P100-PCIE-16GB**. The integrated Radeon was not used. CuPy
CUDA rendering does not run on that AMD GPU.

The selected GPU configuration is warp-cooperative projection, 100 links per
batch, 2,048-sample blocks, double-sort delay mapping and ordinary FFTs. The
mandatory CUDA suite passed 76 tests. Each timing case's final window passed
the reference comparisons; the suite did not compare every timed window.

## Processing steps by scenario and configuration

All stage timings below are **milliseconds per measured call**. The first table
shows **median ± sample standard deviation**, calculated from the individual
warmed captures (n−1 denominator). The ± value describes observed variability;
it is not a confidence interval, accuracy tolerance or deadline guarantee.
The second table uses the same captures and columns for **p95**, with linear
percentile interpolation. Startup and warmup captures are excluded.

**— means unavailable or outside the measured scope, never zero.** The historical renderer-only GPU totals have 30 captures and one separate
instrumented capture per case. The later RF fleet-update tables have separate
repeated instrumented series, with n recorded for each row.

Read the columns from left to right:

- **Pose update:** write moving-platform positions into the propagation scene.
- **Scene propagation:** trace/evaluate paths and export the channel to NumPy.
- **Render preparation:** validate inputs, construct fractional-delay maps and apply link gains.
- **Basis/filter construction:** compute temporal coefficients, evolve path phase and project paths into delay filters.
- **FFT + reconstruction:** private source/filter transforms, convolution, per-sample basis reconstruction and oscillator phase.
- **Other rendering work:** same-capture residual outside those three CPU timers, including basis setup, bookkeeping, error bounds and wrapper summation.
- **Signal rendering subtotal:** complete timed renderer call, including its internal steps. **Do not add this subtotal to those steps again.**
- **Receiver processing:** noise, receiver filters, diagnostics and ADC conversion. Historical direct-SDR rows include rendering in this column because those captures did not time rendering separately.
- **Measured call total:** outer synchronized wall timer. For basis tests this is renderer-only; for historical SDR/LLVM tests it includes poses, propagation and receiver processing.

Stage medians and p95 values need not sum to the call median or p95: each column
is summarized independently. AirSim physics/RPC, transport, queueing, storage and
RF-skill processing were not measured in any of these rows.

The six basis rows use the qualified Ryzen 7 8700G/P100 setup and 1,028 valid
paths per link described above. Historical SDR/LLVM rows use an earlier CPU
container with a two-core quota, tones, independent receiver clocks and an
800-triangle terrain scene; surviving path counts vary with capture. Their
4,096 samples represent **2.048 ms**, plus 256 filter-warmup samples, rather
than the basis workload’s 8.3335 ms. They provide historical pipeline context,
not a matched speed comparison or a full simulation runtime prediction.

<!-- BEGIN STAGE TIMING TABLES -->

### Median ± sample standard deviation

| Configuration / raw captures | n | Signal ms/call | Wall s / signal s (mean) | Pose update | Scene propagation | Render preparation | Basis/filter construction | FFT + reconstruction | Other rendering work | Signal rendering subtotal | Receiver processing | Measured call total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [CPU basis, 100 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_100tx_1rx.json) | 30 | 8.333500 | 194.054 | — | — | 90.54 ± 5.73 | 1106.72 ± 16.29 | 397.92 ± 16.77 | 12.31 ± 1.76 | 1610.09 ± 36.60 | — | 1610.09 ± 36.60 |
| [P100 basis, 100 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json) | 30 | 8.333500 | 6.800 | — | — | — | — | — | — | 56.17 ± 2.13 | — | 56.17 ± 2.13 |
| [CPU basis, 4 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_4tx_1rx.json) | 30 | 8.333500 | 9.449 | — | — | 4.54 ± 0.27 | 45.69 ± 1.11 | 25.57 ± 2.41 | 2.61 ± 0.29 | 78.49 ± 3.38 | — | 78.49 ± 3.38 |
| [P100 basis, 4 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json) | 30 | 8.333500 | 0.687 | — | — | — | — | — | — | 5.68 ± 0.18 | — | 5.68 ± 0.18 |
| [CPU basis, 1 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_1tx_1rx.json) | 30 | 8.333500 | 2.645 | — | — | 1.01 ± 0.05 | 11.96 ± 0.15 | 7.64 ± 0.34 | 1.30 ± 0.10 | 21.87 ± 0.51 | — | 21.87 ± 0.51 |
| [P100 basis, 1 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json) | 30 | 8.333500 | 0.669 | — | — | — | — | — | — | 5.51 ± 0.29 | — | 5.51 ± 0.29 |
| [CPU direct SDR, 2 → 1; 4,096 samples (historical)](benchmarks/results/sdr_cpu_2tx_1rx.json) | 30 | 2.048000 | 119.698 | 0.04 ± 0.01 | 23.11 ± 2.16 | — | — | — | — | — | 217.74 ± 13.78 | 240.86 ± 14.10 |
| [CPU direct SDR, 2 → 2; 4,096 samples (historical)](benchmarks/results/sdr_cpu_2tx_2rx.json) | 30 | 2.048000 | 201.354 | 0.05 ± 0.01 | 19.59 ± 1.55 | — | — | — | — | — | 389.74 ± 18.89 | 410.42 ± 19.08 |
| [CPU direct SDR, 100 → 1; 4,096 samples (historical)](benchmarks/results/sdr_cpu_100tx_1rx.json) | 10 | 2.048000 | 5639.169 | 0.32 ± 0.04 | 681.65 ± 25.46 | — | — | — | — | — | 10846.50 ± 121.42 | 11522.77 ± 131.40 |
| [CPU LLVM per-link, 100 → 1; 4,096 samples (historical)](research_results/batched_renderer_cpu/per_link_local.json) | 10 | 2.048000 | 135.654 | 0.25 ± 0.04 | 65.20 ± 7.19 | — | — | — | — | 189.40 ± 10.82 | 16.04 ± 1.51 | 274.03 ± 16.89 |
| [CPU LLVM tile 32, 100 → 1; 4,096 samples (historical)](research_results/batched_renderer_cpu/batched_32.json) | 10 | 2.048000 | 120.973 | 0.29 ± 0.02 | 60.71 ± 3.23 | — | — | — | — | 170.32 ± 7.00 | 11.00 ± 0.47 | 247.32 ± 7.65 |
| [CPU LLVM tile 128, 100 → 1; 4,096 samples (historical)](research_results/batched_renderer_cpu/batched_128.json) | 10 | 2.048000 | 121.101 | 0.29 ± 0.01 | 61.25 ± 2.53 | — | — | — | — | 169.87 ± 11.05 | 10.50 ± 0.54 | 243.25 ± 12.94 |

### 95th percentile

| Configuration / raw captures | n | Signal ms/call | Wall s / signal s (mean) | Pose update | Scene propagation | Render preparation | Basis/filter construction | FFT + reconstruction | Other rendering work | Signal rendering subtotal | Receiver processing | Measured call total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [CPU basis, 100 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_100tx_1rx.json) | 30 | 8.333500 | 194.054 | — | — | 99.11 | 1143.81 | 439.91 | 16.47 | 1700.36 | — | 1700.36 |
| [P100 basis, 100 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json) | 30 | 8.333500 | 6.800 | — | — | — | — | — | — | 59.65 | — | 59.65 |
| [CPU basis, 4 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_4tx_1rx.json) | 30 | 8.333500 | 9.449 | — | — | 4.84 | 48.20 | 29.37 | 3.12 | 84.62 | — | 84.62 |
| [P100 basis, 4 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json) | 30 | 8.333500 | 0.687 | — | — | — | — | — | — | 6.05 | — | 6.05 |
| [CPU basis, 1 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_1tx_1rx.json) | 30 | 8.333500 | 2.645 | — | — | 1.12 | 12.23 | 8.37 | 1.42 | 23.05 | — | 23.05 |
| [P100 basis, 1 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json) | 30 | 8.333500 | 0.669 | — | — | — | — | — | — | 6.14 | — | 6.14 |
| [CPU direct SDR, 2 → 1; 4,096 samples (historical)](benchmarks/results/sdr_cpu_2tx_1rx.json) | 30 | 2.048000 | 119.698 | 0.05 | 25.16 | — | — | — | — | — | 237.02 | 259.32 |
| [CPU direct SDR, 2 → 2; 4,096 samples (historical)](benchmarks/results/sdr_cpu_2tx_2rx.json) | 30 | 2.048000 | 201.354 | 0.07 | 23.02 | — | — | — | — | — | 427.63 | 446.71 |
| [CPU direct SDR, 100 → 1; 4,096 samples (historical)](benchmarks/results/sdr_cpu_100tx_1rx.json) | 10 | 2.048000 | 5639.169 | 0.39 | 733.15 | — | — | — | — | — | 11017.94 | 11729.99 |
| [CPU LLVM per-link, 100 → 1; 4,096 samples (historical)](research_results/batched_renderer_cpu/per_link_local.json) | 10 | 2.048000 | 135.654 | 0.32 | 78.09 | — | — | — | — | 211.45 | 18.89 | 302.43 |
| [CPU LLVM tile 32, 100 → 1; 4,096 samples (historical)](research_results/batched_renderer_cpu/batched_32.json) | 10 | 2.048000 | 120.973 | 0.31 | 67.66 | — | — | — | — | 183.58 | 11.82 | 256.45 |
| [CPU LLVM tile 128, 100 → 1; 4,096 samples (historical)](research_results/batched_renderer_cpu/batched_128.json) | 10 | 2.048000 | 121.101 | 0.31 | 66.05 | — | — | — | — | 196.07 | 11.09 | 272.31 |

### GPU stage observations: one instrumented capture per configuration

These are CUDA-event spans, in ms, from a separate capture. **n = 1; no standard deviation or p95 is available.** They include dispatch gaps and profiling overhead, and must not be added to the unprofiled median above.

| Configuration | Pack + upload | Delay map | Temporal coefficients | Path → filter projection | Private FFT filters | Reconstruction + sum | Output export | Instrumented wall total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [P100 basis, 100 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json) | 23.73 | 5.11 | 5.51 | 17.67 | 15.08 | 1.69 | 0.11 | 69.36 |
| [P100 basis, 4 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json) | 1.19 | 1.78 | 2.06 | 1.29 | 1.17 | 0.28 | 0.28 | 8.94 |
| [P100 basis, 1 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json) | 0.38 | 1.71 | 2.09 | 1.17 | 3.81 | 3.65 | 0.18 | 14.15 |

### Wall time relative to simulated signal time

Each receiver covers the same simulated interval; receiver durations are not added together. Ratio = sum of fleet-update wall times / actual signal duration. Below 1 means throughput headroom for this measured scope; above 1 means slower than simulated signal time. Instrumented rows are diagnostic and do not establish unprofiled throughput.

| Configuration / raw captures | Mode | Updates | Signal ms/update (mean) | Total signal seconds | Total wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cpu; AMD EPYC 9V74 80-Core Processor; Sionna RT LLVM CPU](results/end_to_end/cpu-100tx-10rx-20261005/measurements.json) | unprofiled | 5 | 8.333400 | 0.041667 | 60.158310 | 1443.788 |
| [10 → 4, basis-cpu; AMD EPYC 9V74 80-Core Processor; Sionna RT LLVM CPU](results/end_to_end/cpu-10tx-4rx-20261005/measurements.json) | unprofiled | 10 | 8.333350 | 0.083334 | 6.153073 | 73.837 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 11.405662 | 45.623 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 11.169603 | 44.678 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 1.682882 | 6.732 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 1.608367 | 6.433 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 0.801219 | 3.205 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 0.763550 | 3.054 |
| [100 → 10, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cpu-100tx-10rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 221.088237 | 884.353 |
| [10 → 4, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cpu-10tx-4rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 11.309370 | 45.237 |
| [2 → 2, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cpu-2tx-2rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 2.294724 | 9.179 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 25.339303 | 101.357 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 25.358207 | 101.433 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 2.010833 | 8.043 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 1.961289 | 7.845 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 0.790174 | 3.161 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 0.732656 | 2.931 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 17.325668 | 69.303 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 37.925993 | 151.704 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 1.961967 | 7.848 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 4.343547 | 17.374 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 0.841250 | 3.365 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 1.336400 | 5.346 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 16.872901 | 67.492 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 16.589912 | 66.360 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 1.921751 | 7.687 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 1.851779 | 7.407 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 0.855329 | 3.421 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 0.808956 | 3.236 |

### End-to-end RF pipeline: median ± sample standard deviation

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Fleet-update wall service |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cpu; AMD EPYC 9V74 80-Core Processor; Sionna RT LLVM CPU](results/end_to_end/cpu-100tx-10rx-20261005/measurements.json) | 5 | 0.002 ± 0.000 | 54.178 ± 2.301 | 1186.283 ± 108.425 | 10615.410 ± 429.415 | 12.070 ± 0.255 | 88.654 ± 1.960 | 15.093 ± 3.193 | 11986.071 ± 499.771 |
| [10 → 4, basis-cpu; AMD EPYC 9V74 80-Core Processor; Sionna RT LLVM CPU](results/end_to_end/cpu-10tx-4rx-20261005/measurements.json) | 10 | 0.003 ± 0.000 | 6.085 ± 0.594 | 105.786 ± 32.761 | 493.207 ± 18.241 | 4.571 ± 1.246 | 7.243 ± 0.778 | 6.468 ± 1.211 | 620.592 ± 32.685 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 37.918 ± 0.502 | 29.893 ± 1.380 | 220.965 ± 4.706 | 8.727 ± 1.039 | 66.255 ± 3.536 | 7.264 ± 0.568 | 371.859 ± 6.483 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 3.902 ± 0.225 | 10.705 ± 0.641 | 27.753 ± 0.538 | 2.893 ± 0.138 | 4.628 ± 0.241 | 3.189 ± 0.261 | 53.446 ± 1.281 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 0.838 ± 0.118 | 8.814 ± 0.501 | 10.924 ± 0.348 | 1.371 ± 0.063 | 1.334 ± 0.097 | 1.800 ± 0.197 | 25.304 ± 0.841 |
| [100 → 10, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cpu-100tx-10rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 37.668 ± 0.695 | 801.306 ± 31.740 | 6429.467 ± 79.604 | 7.503 ± 0.439 | 60.305 ± 1.845 | 7.182 ± 0.352 | 7348.740 ± 100.044 |
| [10 → 4, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cpu-10tx-4rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 3.934 ± 0.242 | 77.213 ± 4.135 | 283.479 ± 6.283 | 2.856 ± 0.105 | 4.485 ± 0.234 | 3.145 ± 0.303 | 375.551 ± 8.503 |
| [2 → 2, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cpu-2tx-2rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 0.862 ± 0.145 | 21.992 ± 9.157 | 43.427 ± 3.684 | 1.556 ± 0.217 | 1.433 ± 0.173 | 1.759 ± 0.259 | 72.217 ± 11.836 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 37.848 ± 0.607 | 330.469 ± 8.641 | 392.762 ± 6.549 | 8.556 ± 0.823 | 66.550 ± 2.936 | 7.410 ± 0.667 | 843.630 ± 11.426 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.001 | 3.932 ± 0.202 | 17.570 ± 1.007 | 32.257 ± 0.907 | 2.960 ± 0.198 | 4.840 ± 0.238 | 3.260 ± 0.299 | 65.192 ± 1.250 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.002 ± 0.000 | 0.820 ± 0.114 | 7.095 ± 0.486 | 11.518 ± 0.583 | 1.345 ± 0.071 | 1.298 ± 0.066 | 1.724 ± 0.283 | 24.045 ± 1.050 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 37.917 ± 0.534 | 740.885 ± 28.566 | 395.659 ± 5.841 | 9.114 ± 1.053 | 67.371 ± 3.631 | 6.945 ± 0.502 | 1259.170 ± 29.525 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 3.903 ± 0.298 | 91.393 ± 3.386 | 36.951 ± 0.702 | 3.078 ± 0.239 | 5.139 ± 0.390 | 3.231 ± 0.344 | 143.698 ± 4.045 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 0.835 ± 0.182 | 26.622 ± 1.162 | 11.880 ± 0.352 | 1.379 ± 0.118 | 1.411 ± 0.093 | 1.821 ± 0.276 | 44.419 ± 1.152 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 37.878 ± 0.526 | 31.222 ± 1.628 | 398.267 ± 5.120 | 9.654 ± 1.032 | 69.410 ± 3.700 | 7.244 ± 0.639 | 553.685 ± 7.645 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.001 | 3.901 ± 0.265 | 10.670 ± 0.701 | 35.264 ± 0.500 | 3.052 ± 0.259 | 5.016 ± 0.339 | 3.190 ± 0.477 | 61.692 ± 1.512 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.001 | 0.819 ± 0.142 | 9.363 ± 0.485 | 11.861 ± 0.359 | 1.383 ± 0.081 | 1.390 ± 0.107 | 1.681 ± 0.318 | 26.772 ± 0.798 |

### End-to-end RF pipeline: p95

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Fleet-update wall service |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cpu; AMD EPYC 9V74 80-Core Processor; Sionna RT LLVM CPU](results/end_to_end/cpu-100tx-10rx-20261005/measurements.json) | 5 | 0.002 | 57.731 | 1353.061 | 11108.158 | 12.203 | 89.477 | 20.940 | 12571.095 |
| [10 → 4, basis-cpu; AMD EPYC 9V74 80-Core Processor; Sionna RT LLVM CPU](results/end_to_end/cpu-10tx-4rx-20261005/measurements.json) | 10 | 0.003 | 7.042 | 126.508 | 520.594 | 6.852 | 8.558 | 8.899 | 654.255 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.002 | 38.706 | 33.166 | 228.522 | 11.021 | 73.656 | 8.521 | 384.061 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.002 | 4.394 | 11.954 | 28.798 | 3.145 | 5.029 | 3.759 | 56.101 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.002 | 1.114 | 9.880 | 11.620 | 1.463 | 1.536 | 2.197 | 27.123 |
| [100 → 10, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cpu-100tx-10rx-unprofiled/measurements.json) | 30 | 0.002 | 38.536 | 874.184 | 6536.351 | 8.246 | 63.817 | 7.790 | 7476.706 |
| [10 → 4, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cpu-10tx-4rx-unprofiled/measurements.json) | 30 | 0.002 | 4.538 | 83.059 | 294.799 | 3.009 | 4.949 | 3.690 | 391.191 |
| [2 → 2, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cpu-2tx-2rx-unprofiled/measurements.json) | 30 | 0.002 | 1.223 | 45.937 | 50.073 | 1.848 | 1.807 | 2.387 | 95.088 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.002 | 39.120 | 347.257 | 403.704 | 9.821 | 70.946 | 8.891 | 860.181 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.002 | 4.323 | 19.821 | 33.876 | 3.363 | 5.329 | 3.820 | 67.897 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.002 | 1.083 | 8.208 | 12.914 | 1.495 | 1.429 | 2.183 | 26.480 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.002 | 39.052 | 806.429 | 407.104 | 11.332 | 73.497 | 7.894 | 1319.833 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.002 | 4.702 | 98.284 | 38.191 | 3.617 | 5.828 | 3.976 | 152.499 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.002 | 1.380 | 29.194 | 12.600 | 1.663 | 1.597 | 2.326 | 46.304 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.002 | 38.742 | 33.553 | 404.798 | 11.570 | 73.685 | 8.892 | 563.363 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.002 | 4.540 | 12.137 | 36.125 | 3.660 | 5.585 | 4.244 | 64.455 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.002 | 1.213 | 10.480 | 12.550 | 1.562 | 1.533 | 2.480 | 28.206 |

### Instrumented end-to-end wall timings: median ± sample standard deviation

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Fleet-update wall service |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.001 ± 0.001 | 38.071 ± 0.609 | 31.412 ± 1.563 | 224.449 ± 4.939 | 9.172 ± 0.657 | 68.524 ± 3.051 | 7.251 ± 0.535 | 379.638 ± 6.981 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 3.947 ± 0.162 | 11.256 ± 0.617 | 29.570 ± 0.522 | 2.989 ± 0.163 | 4.802 ± 0.374 | 3.240 ± 0.356 | 55.938 ± 1.172 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 0.827 ± 0.072 | 9.136 ± 0.443 | 11.819 ± 0.370 | 1.426 ± 0.081 | 1.359 ± 0.083 | 1.902 ± 0.237 | 26.561 ± 0.769 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 38.013 ± 2.022 | 326.550 ± 4.506 | 396.208 ± 5.901 | 8.999 ± 1.039 | 66.090 ± 3.107 | 7.357 ± 0.507 | 843.886 ± 8.037 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 4.198 ± 0.283 | 17.648 ± 0.814 | 33.595 ± 0.846 | 3.018 ± 0.173 | 4.787 ± 0.246 | 3.157 ± 0.323 | 66.692 ± 1.383 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 0.853 ± 0.129 | 7.044 ± 3.262 | 12.985 ± 0.681 | 1.376 ± 0.125 | 1.329 ± 0.123 | 1.770 ± 0.177 | 25.587 ± 3.576 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.002 ± 0.000 | 38.231 ± 1.873 | 51.531 ± 1.737 | 401.013 ± 4.933 | 8.789 ± 0.956 | 68.282 ± 3.277 | 7.323 ± 0.693 | 575.804 ± 8.679 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 4.292 ± 0.296 | 13.014 ± 0.728 | 36.644 ± 0.579 | 3.146 ± 0.163 | 4.869 ± 0.252 | 3.120 ± 0.273 | 65.258 ± 1.026 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.001 ± 0.001 | 0.837 ± 0.094 | 9.559 ± 0.596 | 12.558 ± 0.358 | 1.436 ± 0.097 | 1.403 ± 0.123 | 1.767 ± 0.290 | 27.979 ± 1.029 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.002 ± 0.001 | 38.089 ± 0.641 | 31.490 ± 1.290 | 404.252 ± 5.837 | 9.973 ± 0.989 | 69.411 ± 3.240 | 7.395 ± 0.706 | 561.520 ± 7.641 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 3.989 ± 0.239 | 11.174 ± 0.667 | 37.062 ± 0.611 | 3.150 ± 0.146 | 5.003 ± 0.229 | 3.367 ± 0.534 | 64.268 ± 1.190 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 0.854 ± 0.151 | 9.560 ± 0.578 | 13.191 ± 0.485 | 1.436 ± 0.115 | 1.439 ± 0.129 | 1.772 ± 0.172 | 28.396 ± 1.018 |

### Instrumented end-to-end wall timings: p95

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Fleet-update wall service |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.002 | 39.199 | 34.627 | 232.773 | 9.947 | 73.073 | 8.173 | 391.475 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.002 | 4.265 | 12.196 | 30.131 | 3.296 | 5.328 | 3.934 | 58.370 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.002 | 0.971 | 10.016 | 12.442 | 1.555 | 1.533 | 2.303 | 28.048 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.002 | 39.317 | 334.466 | 403.764 | 11.107 | 70.559 | 8.091 | 857.864 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.002 | 4.774 | 19.167 | 35.298 | 3.344 | 5.232 | 4.098 | 69.070 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.002 | 1.171 | 8.286 | 14.482 | 1.657 | 1.605 | 2.141 | 27.776 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.002 | 42.550 | 54.654 | 406.993 | 10.952 | 73.134 | 8.710 | 591.278 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.002 | 4.804 | 14.233 | 37.441 | 3.442 | 5.270 | 3.694 | 66.990 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.002 | 1.020 | 10.713 | 13.440 | 1.613 | 1.649 | 2.389 | 30.131 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.004 | 39.433 | 33.869 | 411.506 | 11.476 | 74.854 | 8.910 | 571.316 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.002 | 4.420 | 12.596 | 37.990 | 3.344 | 5.403 | 4.364 | 65.483 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.002 | 1.149 | 10.473 | 14.194 | 1.633 | 1.628 | 2.130 | 30.207 |

### Repeated CUDA rendering event spans: median ± sample standard deviation

| Configuration / raw captures | n | Pack + upload | Delay map | Temporal coefficients | Path → filter projection | Private FFT filters | Reconstruction + sum | Output export |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 90.684 ± 4.552 | 20.067 ± 0.432 | 9.607 ± 0.110 | 42.503 ± 0.087 | 48.044 ± 0.061 | 6.998 ± 0.036 | 0.876 ± 0.081 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 3.621 ± 0.173 | 5.686 ± 0.226 | 2.852 ± 0.087 | 11.577 ± 0.100 | 3.268 ± 0.031 | 0.661 ± 0.039 | 0.337 ± 0.042 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.516 ± 0.034 | 2.572 ± 0.121 | 2.050 ± 0.132 | 4.232 ± 0.081 | 1.274 ± 0.035 | 0.290 ± 0.022 | 0.156 ± 0.034 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 119.437 ± 5.722 | 19.790 ± 0.393 | 24.664 ± 0.764 | 57.101 ± 0.132 | 150.876 ± 0.103 | 16.780 ± 0.030 | 0.841 ± 0.101 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 4.699 ± 0.302 | 5.738 ± 0.210 | 3.425 ± 0.506 | 7.987 ± 0.076 | 8.567 ± 0.028 | 1.255 ± 0.022 | 0.326 ± 0.054 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.764 ± 0.097 | 2.648 ± 0.146 | 2.939 ± 0.345 | 3.456 ± 0.044 | 1.526 ± 0.052 | 0.431 ± 0.064 | 0.152 ± 0.037 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 98.280 ± 4.388 | 20.125 ± 0.824 | 21.348 ± 0.135 | 86.232 ± 0.097 | 150.817 ± 0.097 | 16.774 ± 0.046 | 1.126 ± 0.222 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 3.843 ± 0.191 | 5.559 ± 0.263 | 2.955 ± 0.103 | 12.965 ± 0.051 | 8.096 ± 0.065 | 1.210 ± 0.028 | 0.322 ± 0.033 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.498 ± 0.042 | 2.478 ± 0.149 | 1.502 ± 0.079 | 5.284 ± 0.049 | 1.514 ± 0.053 | 0.419 ± 0.020 | 0.152 ± 0.059 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 100.858 ± 5.792 | 20.337 ± 0.313 | 21.328 ± 0.131 | 86.223 ± 0.069 | 150.679 ± 0.090 | 16.771 ± 0.030 | 1.033 ± 0.126 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 4.043 ± 0.318 | 5.606 ± 0.297 | 2.993 ± 0.071 | 12.968 ± 0.052 | 8.096 ± 0.055 | 1.218 ± 0.023 | 0.365 ± 0.049 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.526 ± 0.041 | 2.625 ± 0.236 | 1.718 ± 0.228 | 5.377 ± 0.101 | 1.485 ± 0.039 | 0.412 ± 0.018 | 0.154 ± 0.027 |

### Repeated CUDA rendering event spans: p95

| Configuration / raw captures | n | Pack + upload | Delay map | Temporal coefficients | Path → filter projection | Private FFT filters | Reconstruction + sum | Output export |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 99.003 | 20.980 | 9.782 | 42.621 | 48.160 | 7.040 | 1.010 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 3.959 | 6.058 | 2.937 | 11.749 | 3.317 | 0.745 | 0.414 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.575 | 2.833 | 2.329 | 4.316 | 1.331 | 0.306 | 0.238 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 128.794 | 20.344 | 25.962 | 57.290 | 151.033 | 16.827 | 1.010 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 5.146 | 6.080 | 4.492 | 8.131 | 8.610 | 1.296 | 0.421 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT LLVM CPU](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.967 | 2.917 | 3.651 | 3.508 | 1.591 | 0.595 | 0.224 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 104.837 | 22.119 | 21.506 | 86.315 | 150.989 | 16.865 | 1.546 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 4.096 | 6.019 | 3.052 | 13.036 | 8.188 | 1.261 | 0.384 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.602 | 2.825 | 1.648 | 5.353 | 1.558 | 0.449 | 0.263 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 109.234 | 20.757 | 21.537 | 86.353 | 150.828 | 16.802 | 1.278 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 4.611 | 6.238 | 3.086 | 13.046 | 8.184 | 1.252 | 0.401 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.598 | 3.117 | 2.161 | 5.538 | 1.531 | 0.442 | 0.210 |

CUDA event spans sum each named stage across all blocks/batches and receivers **within each window**, then summarize those window totals. They include host dispatch gaps and are not pure kernel execution times. They come from separate instrumented RF fleet-update runs; do not mix them into unprofiled throughput or add their medians to wall-time medians.

Stage tables report ms per RF fleet update, with the simulation-time denominator and wall-seconds/signal-second ratio in the first table. Source generation, propagation, continuous receiver filtering/noise/ADC, loopback HTTP delivery and consumer file readback are included. The propagation backend is recorded per row: historical runs used LLVM CPU; explicit CUDA/OptiX runs use GPU ray tracing and fields. Receivers execute serially. The default truth source implements the AirSim contract; it does not run live AirSim physics/RPC or AMS-GRA distributed SDR workers. Startup/warmup are excluded from these tables, physical path counts and hardware/quota are in the linked JSON, and five-/ten-window historical runs do not qualify long-run tail latency.

<!-- END STAGE TIMING TABLES -->

The raw-capture links are the sources for every number. On `profiling/p100`,
regenerate these tables with `python scripts/update_profiling_breakdown.py`,
or verify them with `python scripts/update_profiling_breakdown.py --check`.
The historical renderer-only GPU captures above have just one instrumented
observation. For repeated RF fleet-update wall timings and CUDA stage distributions,
use the [P100 end-to-end collector](P100_BASIS_PROFILING.md#complete-rf-pipeline-fill-every-stage-row).
It imports only validated complete bundles and keeps instrumented GPU event
statistics separate from unprofiled latency. The published hybrid and CUDA/OptiX fleet-update bundles below are distinct
from the historical renderer-only captures.

## Your ten-minute flight: 10 moving TX and four moving RX

This is **40 independent directed links**, rather than the 100-link case in
each measured receiver row. There is no measured 10-TX/four-RX moving-scene
run on the requested home processor. The exact processor referred to as
"Ryzen 7100" remains unidentified; do not silently substitute the recorded
8700G for it.

A CPU-only, serial cost extrapolation divides the measured mean by the number
of links and multiplies by 40. The four-link case gives approximately
0.787 s/update (94.49× slower); the 100-link case gives approximately
0.647 s/update (77.62× slower). At 72,000 updates, that is **12.94–15.75 hours
of rendering work**, reasonably rounded to **13–16 hours**. The earlier
14–16-hour conversation estimate was a rough planning range, not a Ryzen
measurement. "About 100× slower" is an order-of-magnitude description of this
particular CPU extrapolation, not a benchmark or a project-wide result.

This range is not a confidence interval or a guarantee. It assumes similar
per-link CPU costs and serial processing. The CPU renderer handles links
separately; job count, cache behavior, thread choices and the actual host still
matter. Four receiver outputs are not four links: each receives ten transmitters.
No receiver-parallel speedup is credited without measurement. Do not linearly
extrapolate P100's 100-link latency to this small case: its measured 1-/4-link
latencies show substantial fixed/batching costs.

Random flight paths require channel/visibility updates. Those solves, AirSim,
DSP, recording and queues are excluded from the extrapolation. **The complete
flight's wall-clock completion time remains unknown.** A measured advancing
clock run is needed; reserving a day is a scheduling allowance, not a validated
upper bound. Offline simulation must advance every requested epoch and retain
all samples; skipping late frames or dropping I/Q is not equivalent work.

At four receivers and 2 MS/s, ten minutes contains 4.8 billion complex samples:
**38.4 GB as complex64 or 76.8 GB as complex128**, before compression/container
overheads (decimal GB). The earlier conversation's 48-billion/384–768 GB
estimate was ten times too large. On-disk ADC formats can be smaller; conversion
and writing costs still require measurement.

## The original 100-TX/10-RX deployment

The measured P100 row is **100 TX into one RX**, not the whole fleet. A serial
ten-receiver extrapolation on one P100 is approximately **68× slower than real
time**, or **11.33 hours of renderer work per ten simulated minutes**. Ten
identical, independent P100 workers could ideally run those receivers in
parallel at the one-worker **6.80×** rate, about **68 minutes**, if no additional
contention or dispatch costs arose. Neither deployment has been measured.
Ten GPUs do not make an individual receiver's 56.67 ms mean fit into 8.33 ms.

The measured CPU's serial ten-receiver extrapolation is approximately 1,941×
slower, or **323 hours** for ten simulated minutes. Do not apply that number to
the smaller 10-TX/four-RX example. Full service adds other stages in every case.

## What the renderer timer includes and excludes

Included: host validation/packing, private uploads, fresh channel-dependent
delay maps and coefficient/filter construction, path projection, private FFT
filtering, sample reconstruction, coherent receiver summation and synchronized
output download. First-use/JIT and reference calculations are outside timing.

Excluded: waveform generation, physical scene/ray tracing, moving meshes,
receiver noise/filter/ADC, unequal-clock resampling, AirSim physics/Unreal,
transport, queueing and recording. The channels change each capture but are
synthetic arrays; they are not derived from a moving AirSim flight. Current
Sionna RT/Dr.Jit CUDA propagation remains unsupported on the P100; the working
CuPy renderer does not resolve that compatibility issue.

End-to-end **delivery latency** also includes input availability, interpolation
lookahead, queue waits and transport. Renderer service time, achievable output
throughput, simulation update frequency and live delivery latency are different
quantities. A simulation clock configured to 120 Hz does not demonstrate
120 wall-clock updates/s. Event spans from a separate instrumented capture
must not be summed into the unprofiled mean or median.

## Why earlier reports can appear faster

| Earlier result / report | Actual scope | Why it cannot size the current continuous workload |
| --- | --- | --- |
| 7.51 ms radar update, [PERFORMANCE](PERFORMANCE.md) | Eight point targets, direct-only empty scene, one chirp | Small scheduled radar capture; no full environmental multipath or independent continuous streams |
| 162.85 ms / 80 ms frame, [PERFORMANCE](PERFORMANCE.md) | Sixteen-chirp radar frame | About 2.04× renderer/service work per frame interval, not a 120 Hz continuous network result |
| 144 retained paths, [single bounce](OPTIMIZATION.md), [per pulse](PER_PULSE_RUNTIME.md) | Small scene's LoS/specular channel; many links but very few paths | Channel-only timing excludes sample rendering and diffuse ground return |
| 48.6 ms channel, [GPU planning](GPU_RUNTIME.md) | CPU channel/poses/export | No waveform processing; sub-millisecond GPU ray entries elsewhere are hypothetical query-rate arithmetic |
| 243.25 ms service, [batched renderer](BATCHED_RENDERING.md) | Tone inputs, about 42,500 surviving paths total, 4,096 samples per RX | Only 2.048 ms of output, versus the new 8.3335 ms window; scene-dependent survival reduces path work |
| 22× CPU speedup, [basis experiment](DOPPLER_BASIS_FFT.md) | Ratio of two algorithms on one/four-link synthetic jobs | Faster than a baseline does not mean faster than real time; original host differs from the P100 collection |
| 122.67 ms P100, [original run](results/profiling/p100-basis-full-20261004/REPORT.md) | Older gather projection; failed timestamp qualification | Historical diagnostic result; superseded by the qualified 56.17 ms median configuration |
| Legacy Sionna P100 [results](results/profiling/README.md) | Older propagation stack and CPU signal rendering | Separate compatibility experiment, not current CuPy renderer or supported current-stack propagation |

Rays attempted, retained physical paths, filter taps and basis terms are
different counts. A request for 1,028 ray attempts does not guarantee 1,028
valid paths; the latest renderer stress test supplies all of them explicitly.
Short bursts also cannot be compared with continuous output solely by updates/s.
Historical GPU forecasts are sensitivity calculations, not measured capacity.

## Keep the summary reproducible

Run `python3 scripts/update_runtime_docs.py` after selecting a new qualified
collection in that script, or `python3 scripts/update_runtime_docs.py --check`
to verify both published tables against the JSON. Preserve historical reports;
new measurements must state hardware, backend, links, valid paths, sample count,
signal duration, precision, interpolation, delay/Doppler bounds, included work,
accuracy status, warmups and timing distribution. Publish full-service flight
measurements separately from renderer-only results.

## End-to-end RF pipeline tests

See [END_TO_END.md](END_TO_END.md) for the real-terrain scene-to-consumer test,
the direct-renderer integration oracle, and CPU/P100 collection commands.
The default trajectory source exercises the AirSim bridge contract; it does
not execute AirSim physics/RPC. Full distributed continuous-SDR coverage is
still outstanding. New RF fleet-update results are distinct from renderer-only
results and do not replace the qualified synthetic stress workload.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [results/end_to_end/cpu-100tx-10rx-20261005/measurements.json](results/end_to_end/cpu-100tx-10rx-20261005/measurements.json) — RF fleet update | historical | 5 | 8.333400 | 0.041667 | 60.158310 | 1443.788 |
| [results/end_to_end/cpu-10tx-4rx-20261005/measurements.json](results/end_to_end/cpu-10tx-4rx-20261005/measurements.json) — RF fleet update | historical | 10 | 8.333350 | 0.083334 | 6.153073 | 73.837 |
| [results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-instrumented/measurements.json](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 11.405662 | 45.623 |
| [results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-unprofiled/measurements.json](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 11.169603 | 44.678 |
| [results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-instrumented/measurements.json](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 1.682882 | 6.732 |
| [results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-unprofiled/measurements.json](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 1.608367 | 6.433 |
| [results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-instrumented/measurements.json](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 0.801219 | 3.205 |
| [results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-unprofiled/measurements.json](results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 0.763550 | 3.054 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_100tx_1rx.json](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_100tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 48.514551 | 194.054 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_1tx_1rx.json](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_1tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 0.661153 | 2.645 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_4tx_1rx.json](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_4tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 2.362246 | 9.449 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 1.700125 | 6.800 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 0.167198 | 0.669 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 0.171683 | 0.687 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cpu-100tx-10rx-unprofiled/measurements.json](results/profiling/p100-end-to-end-full-20261005/profiles/cpu-100tx-10rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 221.088237 | 884.353 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cpu-10tx-4rx-unprofiled/measurements.json](results/profiling/p100-end-to-end-full-20261005/profiles/cpu-10tx-4rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 11.309370 | 45.237 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cpu-2tx-2rx-unprofiled/measurements.json](results/profiling/p100-end-to-end-full-20261005/profiles/cpu-2tx-2rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 2.294724 | 9.179 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-instrumented/measurements.json](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 25.339303 | 101.357 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-unprofiled/measurements.json](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 25.358207 | 101.433 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-instrumented/measurements.json](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 2.010833 | 8.043 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-unprofiled/measurements.json](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 1.961289 | 7.845 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-instrumented/measurements.json](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 0.790174 | 3.161 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-unprofiled/measurements.json](results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 0.732656 | 2.931 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 17.325668 | 69.303 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 37.925993 | 151.704 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 1.961967 | 7.848 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 4.343547 | 17.374 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 0.841250 | 3.365 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json](results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 1.336400 | 5.346 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 16.872901 | 67.492 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 16.589912 | 66.360 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 1.921751 | 7.687 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 1.851779 | 7.407 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 0.855329 | 3.421 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json](results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 0.808956 | 3.236 |
| [research_results/batched_renderer_cpu/batched_128.json](research_results/batched_renderer_cpu/batched_128.json) — Local RF service | unprofiled_benchmark | 10 | 2.048000 | 0.020480 | 2.480152 | 121.101 |
| [research_results/batched_renderer_cpu/batched_32.json](research_results/batched_renderer_cpu/batched_32.json) — Local RF service | unprofiled_benchmark | 10 | 2.048000 | 0.020480 | 2.477535 | 120.973 |
| [research_results/batched_renderer_cpu/per_link_local.json](research_results/batched_renderer_cpu/per_link_local.json) — Local RF service | unprofiled_benchmark | 10 | 2.048000 | 0.020480 | 2.778200 | 135.654 |
| [benchmarks/results/sdr_cpu_100tx_1rx.json](benchmarks/results/sdr_cpu_100tx_1rx.json) — Local RF service | historical | 10 | 2.048000 | 0.020480 | 115.490185 | 5639.169 |
| [benchmarks/results/sdr_cpu_2tx_1rx.json](benchmarks/results/sdr_cpu_2tx_1rx.json) — Local RF service | historical | 30 | 2.048000 | 0.061440 | 7.354236 | 119.698 |
| [benchmarks/results/sdr_cpu_2tx_2rx.json](benchmarks/results/sdr_cpu_2tx_2rx.json) — Local RF service | historical | 30 | 2.048000 | 0.061440 | 12.371171 | 201.354 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->
