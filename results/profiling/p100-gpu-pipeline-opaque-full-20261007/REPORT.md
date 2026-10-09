# Complete RF end-to-end profiling collection

**Timing scope:** RF fleet-update wall service; serial receivers; trajectory source and loopback consumer. [Common measurement definitions](../../../TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json](profiles/cuda-100tx-10rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 16.872901 | 67.492 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json](profiles/cuda-100tx-10rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 16.589912 | 66.360 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json](profiles/cuda-10tx-4rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 1.921751 | 7.687 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json](profiles/cuda-10tx-4rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 1.851779 | 7.407 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json](profiles/cuda-2tx-2rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 0.855329 | 3.421 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json](profiles/cuda-2tx-2rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 0.808956 | 3.236 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->


### End-to-end RF pipeline: median ± sample standard deviation

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 37.878 ± 0.526 | 31.222 ± 1.628 | 398.267 ± 5.120 | 9.654 ± 1.032 | 69.410 ± 3.700 | 7.244 ± 0.639 | 553.685 ± 7.645 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.001 | 3.901 ± 0.265 | 10.670 ± 0.701 | 35.264 ± 0.500 | 3.052 ± 0.259 | 5.016 ± 0.339 | 3.190 ± 0.477 | 61.692 ± 1.512 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.001 | 0.819 ± 0.142 | 9.363 ± 0.485 | 11.861 ± 0.359 | 1.383 ± 0.081 | 1.390 ± 0.107 | 1.681 ± 0.318 | 26.772 ± 0.798 |

### End-to-end RF pipeline: p95

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.002 | 38.742 | 33.553 | 404.798 | 11.570 | 73.685 | 8.892 | 563.363 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.002 | 4.540 | 12.137 | 36.125 | 3.660 | 5.585 | 4.244 | 64.455 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.002 | 1.213 | 10.480 | 12.550 | 1.562 | 1.533 | 2.480 | 28.206 |

### Instrumented end-to-end wall timings: median ± sample standard deviation

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.002 ± 0.001 | 38.089 ± 0.641 | 31.490 ± 1.290 | 404.252 ± 5.837 | 9.973 ± 0.989 | 69.411 ± 3.240 | 7.395 ± 0.706 | 561.520 ± 7.641 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 3.989 ± 0.239 | 11.174 ± 0.667 | 37.062 ± 0.611 | 3.150 ± 0.146 | 5.003 ± 0.229 | 3.367 ± 0.534 | 64.268 ± 1.190 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 0.854 ± 0.151 | 9.560 ± 0.578 | 13.191 ± 0.485 | 1.436 ± 0.115 | 1.439 ± 0.129 | 1.772 ± 0.172 | 28.396 ± 1.018 |

### Instrumented end-to-end wall timings: p95

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.004 | 39.433 | 33.869 | 411.506 | 11.476 | 74.854 | 8.910 | 571.316 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.002 | 4.420 | 12.596 | 37.990 | 3.344 | 5.403 | 4.364 | 65.483 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.002 | 1.149 | 10.473 | 14.194 | 1.633 | 1.628 | 2.130 | 30.207 |

### Repeated CUDA rendering event spans: median ± sample standard deviation

| Configuration / raw captures | n | Pack + upload | Delay map | Temporal coefficients | Path → filter projection | Private FFT filters | Reconstruction + sum | Output export |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 100.858 ± 5.792 | 20.337 ± 0.313 | 21.328 ± 0.131 | 86.223 ± 0.069 | 150.679 ± 0.090 | 16.771 ± 0.030 | 1.033 ± 0.126 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 4.043 ± 0.318 | 5.606 ± 0.297 | 2.993 ± 0.071 | 12.968 ± 0.052 | 8.096 ± 0.055 | 1.218 ± 0.023 | 0.365 ± 0.049 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.526 ± 0.041 | 2.625 ± 0.236 | 1.718 ± 0.228 | 5.377 ± 0.101 | 1.485 ± 0.039 | 0.412 ± 0.018 | 0.154 ± 0.027 |

### Repeated CUDA rendering event spans: p95

| Configuration / raw captures | n | Pack + upload | Delay map | Temporal coefficients | Path → filter projection | Private FFT filters | Reconstruction + sum | Output export |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 109.234 | 20.757 | 21.537 | 86.353 | 150.828 | 16.802 | 1.278 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 4.611 | 6.238 | 3.086 | 13.046 | 8.184 | 1.252 | 0.401 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.598 | 3.117 | 2.161 | 5.538 | 1.531 | 0.442 | 0.210 |

CUDA event spans sum each named stage across all blocks/batches and receivers **within each window**, then summarize those window totals. They include host dispatch gaps and are not pure kernel execution times. They come from separate instrumented RF fleet-update runs; do not mix them into unprofiled throughput or add their medians to wall-time medians.

All timings are ms per fleet update. Source generation, propagation, continuous receiver filtering/noise/ADC, loopback HTTP delivery and consumer file readback are included. The propagation backend is recorded per row: historical runs used LLVM CPU; explicit CUDA/OptiX runs use GPU ray tracing and fields. Receivers execute serially. The default truth source implements the AirSim contract; it does not run live AirSim physics/RPC or AMS-GRA distributed SDR workers. Startup/warmup are excluded from these tables, physical path counts and hardware/quota are in the linked JSON, and five-/ten-window historical runs do not qualify long-run tail latency.
