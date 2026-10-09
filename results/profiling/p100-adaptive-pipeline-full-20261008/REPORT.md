# Complete RF end-to-end profiling collection

### Wall time relative to simulated signal time

Each receiver covers the same simulated interval; receiver durations are not added together. Ratio = sum of fleet-update wall times / actual signal duration. Below 1 means throughput headroom for this measured scope; above 1 means slower than simulated signal time. Instrumented rows are diagnostic and do not establish unprofiled throughput.

| Configuration / raw captures | Mode | Updates | Signal ms/update (mean) | Total signal seconds | Total wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 11.405662 | 45.623 |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 11.169603 | 44.678 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 1.682882 | 6.732 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 1.608367 | 6.433 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-instrumented/measurements.json) | instrumented | 30 | 8.333333 | 0.250000 | 0.801219 | 3.205 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-unprofiled/measurements.json) | unprofiled | 30 | 8.333333 | 0.250000 | 0.763550 | 3.054 |

### End-to-end RF pipeline: median ± sample standard deviation

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Fleet-update wall service |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 37.918 ± 0.502 | 29.893 ± 1.380 | 220.965 ± 4.706 | 8.727 ± 1.039 | 66.255 ± 3.536 | 7.264 ± 0.568 | 371.859 ± 6.483 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 3.902 ± 0.225 | 10.705 ± 0.641 | 27.753 ± 0.538 | 2.893 ± 0.138 | 4.628 ± 0.241 | 3.189 ± 0.261 | 53.446 ± 1.281 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.001 ± 0.000 | 0.838 ± 0.118 | 8.814 ± 0.501 | 10.924 ± 0.348 | 1.371 ± 0.063 | 1.334 ± 0.097 | 1.800 ± 0.197 | 25.304 ± 0.841 |

### End-to-end RF pipeline: p95

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Fleet-update wall service |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 30 | 0.002 | 38.706 | 33.166 | 228.522 | 11.021 | 73.656 | 8.521 | 384.061 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 30 | 0.002 | 4.394 | 11.954 | 28.798 | 3.145 | 5.029 | 3.759 | 56.101 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 30 | 0.002 | 1.114 | 9.880 | 11.620 | 1.463 | 1.536 | 2.197 | 27.123 |

### Instrumented end-to-end wall timings: median ± sample standard deviation

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Fleet-update wall service |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.001 ± 0.001 | 38.071 ± 0.609 | 31.412 ± 1.563 | 224.449 ± 4.939 | 9.172 ± 0.657 | 68.524 ± 3.051 | 7.251 ± 0.535 | 379.638 ± 6.981 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 3.947 ± 0.162 | 11.256 ± 0.617 | 29.570 ± 0.522 | 2.989 ± 0.163 | 4.802 ± 0.374 | 3.240 ± 0.356 | 55.938 ± 1.172 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.001 ± 0.000 | 0.827 ± 0.072 | 9.136 ± 0.443 | 11.819 ± 0.370 | 1.426 ± 0.081 | 1.359 ± 0.083 | 1.902 ± 0.237 | 26.561 ± 0.769 |

### Instrumented end-to-end wall timings: p95

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Fleet-update wall service |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 0.002 | 39.199 | 34.627 | 232.773 | 9.947 | 73.073 | 8.173 | 391.475 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 0.002 | 4.265 | 12.196 | 30.131 | 3.296 | 5.328 | 3.934 | 58.370 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.002 | 0.971 | 10.016 | 12.442 | 1.555 | 1.533 | 2.303 | 28.048 |

### Repeated CUDA rendering event spans: median ± sample standard deviation

| Configuration / raw captures | n | Pack + upload | Delay map | Temporal coefficients | Path → filter projection | Private FFT filters | Reconstruction + sum | Output export |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 90.684 ± 4.552 | 20.067 ± 0.432 | 9.607 ± 0.110 | 42.503 ± 0.087 | 48.044 ± 0.061 | 6.998 ± 0.036 | 0.876 ± 0.081 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 3.621 ± 0.173 | 5.686 ± 0.226 | 2.852 ± 0.087 | 11.577 ± 0.100 | 3.268 ± 0.031 | 0.661 ± 0.039 | 0.337 ± 0.042 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.516 ± 0.034 | 2.572 ± 0.121 | 2.050 ± 0.132 | 4.232 ± 0.081 | 1.274 ± 0.035 | 0.290 ± 0.022 | 0.156 ± 0.034 |

### Repeated CUDA rendering event spans: p95

| Configuration / raw captures | n | Pack + upload | Delay map | Temporal coefficients | Path → filter projection | Private FFT filters | Reconstruction + sum | Output export |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-100tx-10rx-instrumented/measurements.json) | 30 | 99.003 | 20.980 | 9.782 | 42.621 | 48.160 | 7.040 | 1.010 |
| [10 → 4, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-10tx-4rx-instrumented/measurements.json) | 30 | 3.959 | 6.058 | 2.937 | 11.749 | 3.317 | 0.745 | 0.414 |
| [2 → 2, basis-cuda; Tesla P100-PCIE-16GB; Sionna RT CUDA/OptiX](profiles/cuda-2tx-2rx-instrumented/measurements.json) | 30 | 0.575 | 2.833 | 2.329 | 4.316 | 1.331 | 0.306 | 0.238 |

CUDA event spans sum each named stage across all blocks/batches and receivers **within each window**, then summarize those window totals. They include host dispatch gaps and are not pure kernel execution times. They come from separate instrumented RF fleet-update runs; do not mix them into unprofiled throughput or add their medians to wall-time medians.

Stage tables report ms per RF fleet update, with the simulation-time denominator and wall-seconds/signal-second ratio in the first table. Source generation, propagation, continuous receiver filtering/noise/ADC, loopback HTTP delivery and consumer file readback are included. The propagation backend is recorded per row: historical runs used LLVM CPU; explicit CUDA/OptiX runs use GPU ray tracing and fields. Receivers execute serially. The default truth source implements the AirSim contract; it does not run live AirSim physics/RPC or AMS-GRA distributed SDR workers. Startup/warmup are excluded from these tables, physical path counts and hardware/quota are in the linked JSON, and five-/ten-window historical runs do not qualify long-run tail latency.

Measurement units and scope: [timing definitions](../../../docs/timing.md); [wall cost per simulated signal second](../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
