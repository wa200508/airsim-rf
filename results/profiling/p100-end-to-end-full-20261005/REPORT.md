# Complete RF end-to-end profiling collection

**Timing scope:** RF fleet-update wall service; serial receivers; trajectory source and loopback consumer. [Common measurement definitions](../../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
### End-to-end RF pipeline: median ± sample standard deviation

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics](profiles/cpu-100tx-10rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 37.668 ± 0.695 | 801.306 ± 31.740 | 6429.467 ± 79.604 | 7.503 ± 0.439 | 60.305 ± 1.845 | 7.182 ± 0.352 | 7348.740 ± 100.044 |
| [10 → 4, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics](profiles/cpu-10tx-4rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 3.934 ± 0.242 | 77.213 ± 4.135 | 283.479 ± 6.283 | 2.856 ± 0.105 | 4.485 ± 0.234 | 3.145 ± 0.303 | 375.551 ± 8.503 |
| [2 → 2, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics](profiles/cpu-2tx-2rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 0.862 ± 0.145 | 21.992 ± 9.157 | 43.427 ± 3.684 | 1.556 ± 0.217 | 1.433 ± 0.173 | 1.759 ± 0.259 | 72.217 ± 11.836 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 37.848 ± 0.607 | 330.469 ± 8.641 | 392.762 ± 6.549 | 8.556 ± 0.823 | 66.550 ± 2.936 | 7.410 ± 0.667 | 843.630 ± 11.426 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.001 | 3.932 ± 0.202 | 17.570 ± 1.007 | 32.257 ± 0.907 | 2.960 ± 0.198 | 4.840 ± 0.238 | 3.260 ± 0.299 | 65.192 ± 1.250 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.002 ± 0.000 | 0.820 ± 0.114 | 7.095 ± 0.486 | 11.518 ± 0.583 | 1.345 ± 0.071 | 1.298 ± 0.066 | 1.724 ± 0.283 | 24.045 ± 1.050 |

### End-to-end RF pipeline: p95

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics](profiles/cpu-100tx-10rx-unprofiled/measurements.json) | 30 | 0.002 | 38.536 | 874.184 | 6536.351 | 8.246 | 63.817 | 7.790 | 7476.706 |
| [10 → 4, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics](profiles/cpu-10tx-4rx-unprofiled/measurements.json) | 30 | 0.002 | 4.538 | 83.059 | 294.799 | 3.009 | 4.949 | 3.690 | 391.191 |
| [2 → 2, basis-cpu; AMD Ryzen 7 8700G w/ Radeon 780M Graphics](profiles/cpu-2tx-2rx-unprofiled/measurements.json) | 30 | 0.002 | 1.223 | 45.937 | 50.073 | 1.848 | 1.807 | 2.387 | 95.088 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.002 | 39.120 | 347.257 | 403.704 | 9.821 | 70.946 | 8.891 | 860.181 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.002 | 4.323 | 19.821 | 33.876 | 3.363 | 5.329 | 3.820 | 67.897 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.002 | 1.083 | 8.208 | 12.914 | 1.495 | 1.429 | 2.183 | 26.480 |

### Instrumented end-to-end wall timings: median ± sample standard deviation

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 38.013 ± 2.022 | 326.550 ± 4.506 | 396.208 ± 5.901 | 8.999 ± 1.039 | 66.090 ± 3.107 | 7.357 ± 0.507 | 843.886 ± 8.037 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 4.198 ± 0.283 | 17.648 ± 0.814 | 33.595 ± 0.846 | 3.018 ± 0.173 | 4.787 ± 0.246 | 3.157 ± 0.323 | 66.692 ± 1.383 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 0.853 ± 0.129 | 7.044 ± 3.262 | 12.985 ± 0.681 | 1.376 ± 0.125 | 1.329 ± 0.123 | 1.770 ± 0.177 | 25.587 ± 3.576 |

### Instrumented end-to-end wall timings: p95

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.002 | 39.317 | 334.466 | 403.764 | 11.107 | 70.559 | 8.091 | 857.864 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.002 | 4.774 | 19.167 | 35.298 | 3.344 | 5.232 | 4.098 | 69.070 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.002 | 1.171 | 8.286 | 14.482 | 1.657 | 1.605 | 2.141 | 27.776 |

### Repeated CUDA rendering event spans: median ± sample standard deviation

| Configuration / raw captures | n | Pack + upload | Delay map | Temporal coefficients | Path → filter projection | Private FFT filters | Reconstruction + sum | Output export |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 119.437 ± 5.722 | 19.790 ± 0.393 | 24.664 ± 0.764 | 57.101 ± 0.132 | 150.876 ± 0.103 | 16.780 ± 0.030 | 0.841 ± 0.101 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 4.699 ± 0.302 | 5.738 ± 0.210 | 3.425 ± 0.506 | 7.987 ± 0.076 | 8.567 ± 0.028 | 1.255 ± 0.022 | 0.326 ± 0.054 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.764 ± 0.097 | 2.648 ± 0.146 | 2.939 ± 0.345 | 3.456 ± 0.044 | 1.526 ± 0.052 | 0.431 ± 0.064 | 0.152 ± 0.037 |

### Repeated CUDA rendering event spans: p95

| Configuration / raw captures | n | Pack + upload | Delay map | Temporal coefficients | Path → filter projection | Private FFT filters | Reconstruction + sum | Output export |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 128.794 | 20.344 | 25.962 | 57.290 | 151.033 | 16.827 | 1.010 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 5.146 | 6.080 | 4.492 | 8.131 | 8.610 | 1.296 | 0.421 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.967 | 2.917 | 3.651 | 3.508 | 1.591 | 0.595 | 0.224 |

CUDA event spans sum each named stage across all blocks/batches and receivers **within each window**, then summarize those window totals. They include host dispatch gaps and are not pure kernel execution times. They come from separate instrumented RF fleet-update runs; do not mix them into unprofiled throughput or add their medians to wall-time medians.

All timings are ms per fleet update. Source generation, propagation, continuous receiver filtering/noise/ADC, loopback HTTP delivery and consumer file readback are included. Sionna propagation is LLVM CPU even with CuPy rendering. Receivers execute serially. The default truth source implements the AirSim contract; it does not run live AirSim physics/RPC or AMS-GRA distributed SDR workers. Startup/warmup are excluded from these tables, physical path counts and hardware/quota are in the linked JSON, and five-/ten-window historical runs do not qualify long-run tail latency.

Measurement units and scope: [timing definitions](../../../docs/timing.md); [wall cost per simulated signal second](../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
