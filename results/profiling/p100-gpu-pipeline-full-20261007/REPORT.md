# Complete RF end-to-end profiling collection

**Timing scope:** RF fleet-update wall service; serial receivers; trajectory source and loopback consumer. [Common measurement definitions](../../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
### End-to-end RF pipeline: median ± sample standard deviation

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 37.917 ± 0.534 | 740.885 ± 28.566 | 395.659 ± 5.841 | 9.114 ± 1.053 | 67.371 ± 3.631 | 6.945 ± 0.502 | 1259.170 ± 29.525 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 3.903 ± 0.298 | 91.393 ± 3.386 | 36.951 ± 0.702 | 3.078 ± 0.239 | 5.139 ± 0.390 | 3.231 ± 0.344 | 143.698 ± 4.045 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 0.835 ± 0.182 | 26.622 ± 1.162 | 11.880 ± 0.352 | 1.379 ± 0.118 | 1.411 ± 0.093 | 1.821 ± 0.276 | 44.419 ± 1.152 |

### End-to-end RF pipeline: p95

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.002 | 39.052 | 806.429 | 407.104 | 11.332 | 73.497 | 7.894 | 1319.833 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.002 | 4.702 | 98.284 | 38.191 | 3.617 | 5.828 | 3.976 | 152.499 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.002 | 1.380 | 29.194 | 12.600 | 1.663 | 1.597 | 2.326 | 46.304 |

### Instrumented end-to-end wall timings: median ± sample standard deviation

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.002 ± 0.000 | 38.231 ± 1.873 | 51.531 ± 1.737 | 401.013 ± 4.933 | 8.789 ± 0.956 | 68.282 ± 3.277 | 7.323 ± 0.693 | 575.804 ± 8.679 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 4.292 ± 0.296 | 13.014 ± 0.728 | 36.644 ± 0.579 | 3.146 ± 0.163 | 4.869 ± 0.252 | 3.120 ± 0.273 | 65.258 ± 1.026 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.001 ± 0.001 | 0.837 ± 0.094 | 9.559 ± 0.596 | 12.558 ± 0.358 | 1.436 ± 0.097 | 1.403 ± 0.123 | 1.767 ± 0.290 | 27.979 ± 1.029 |

### Instrumented end-to-end wall timings: p95

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.002 | 42.550 | 54.654 | 406.993 | 10.952 | 73.134 | 8.710 | 591.278 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.002 | 4.804 | 14.233 | 37.441 | 3.442 | 5.270 | 3.694 | 66.990 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.002 | 1.020 | 10.713 | 13.440 | 1.613 | 1.649 | 2.389 | 30.131 |

### Repeated CUDA rendering event spans: median ± sample standard deviation

| Configuration / raw captures | n | Pack + upload | Delay map | Temporal coefficients | Path → filter projection | Private FFT filters | Reconstruction + sum | Output export |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 98.280 ± 4.388 | 20.125 ± 0.824 | 21.348 ± 0.135 | 86.232 ± 0.097 | 150.817 ± 0.097 | 16.774 ± 0.046 | 1.126 ± 0.222 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 3.843 ± 0.191 | 5.559 ± 0.263 | 2.955 ± 0.103 | 12.965 ± 0.051 | 8.096 ± 0.065 | 1.210 ± 0.028 | 0.322 ± 0.033 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.498 ± 0.042 | 2.478 ± 0.149 | 1.502 ± 0.079 | 5.284 ± 0.049 | 1.514 ± 0.053 | 0.419 ± 0.020 | 0.152 ± 0.059 |

### Repeated CUDA rendering event spans: p95

| Configuration / raw captures | n | Pack + upload | Delay map | Temporal coefficients | Path → filter projection | Private FFT filters | Reconstruction + sum | Output export |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 104.837 | 22.119 | 21.506 | 86.315 | 150.989 | 16.865 | 1.546 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 4.096 | 6.019 | 3.052 | 13.036 | 8.188 | 1.261 | 0.384 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.602 | 2.825 | 1.648 | 5.353 | 1.558 | 0.449 | 0.263 |

CUDA event spans sum each named stage across all blocks/batches and receivers **within each window**, then summarize those window totals. They include host dispatch gaps and are not pure kernel execution times. They come from separate instrumented RF fleet-update runs; do not mix them into unprofiled throughput or add their medians to wall-time medians.

All timings are ms per fleet update. Source generation, propagation, continuous receiver filtering/noise/ADC, loopback HTTP delivery and consumer file readback are included. The propagation backend is recorded per row: historical runs used LLVM CPU; explicit CUDA/OptiX runs use GPU ray tracing and fields. Receivers execute serially. The default truth source implements the AirSim contract; it does not run live AirSim physics/RPC or AMS-GRA distributed SDR workers. Startup/warmup are excluded from these tables, physical path counts and hardware/quota are in the linked JSON, and five-/ten-window historical runs do not qualify long-run tail latency.

Measurement units and scope: [timing definitions](../../../docs/timing.md); [wall cost per simulated signal second](../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
