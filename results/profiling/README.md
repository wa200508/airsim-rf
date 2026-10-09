# Profiling result bundles

**Timing scope:** Mixed scope or architecture/reference document; each workload/table retains its stated timed operation. [Common measurement definitions](../../TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [results/profiling/direct-renderer-cpu-validation/metrics/cpu_100tx_1rx.json](direct-renderer-cpu-validation/metrics/cpu_100tx_1rx.json) — Local RF service | unprofiled_benchmark | 2 | 2.048000 | 0.004096 | 22.390197 | 5466.357 |
| [results/profiling/direct-renderer-cpu-validation/metrics/cpu_100tx_1rx_direct.json](direct-renderer-cpu-validation/metrics/cpu_100tx_1rx_direct.json) — Local RF service | unprofiled_benchmark | 2 | 2.048000 | 0.004096 | 0.788182 | 192.427 |
| [results/profiling/direct-renderer-cpu-validation/metrics/cpu_2tx_1rx.json](direct-renderer-cpu-validation/metrics/cpu_2tx_1rx.json) — Local RF service | unprofiled_benchmark | 3 | 2.048000 | 0.006144 | 0.687552 | 111.906 |
| [results/profiling/direct-renderer-cpu-validation/metrics/cpu_2tx_1rx_direct.json](direct-renderer-cpu-validation/metrics/cpu_2tx_1rx_direct.json) — Local RF service | unprofiled_benchmark | 3 | 2.048000 | 0.006144 | 0.155916 | 25.377 |
| [results/profiling/direct-renderer-cpu-validation/profiles/cpu_100tx_1rx_direct_events.json](direct-renderer-cpu-validation/profiles/cpu_100tx_1rx_direct_events.json) — Local RF service | instrumented_profile | 2 | 2.048000 | 0.004096 | 0.847461 | 206.900 |
| [results/profiling/direct-renderer-cpu-validation/profiles/cpu_100tx_1rx_events.json](direct-renderer-cpu-validation/profiles/cpu_100tx_1rx_events.json) — Local RF service | instrumented_profile | 2 | 2.048000 | 0.004096 | 22.365961 | 5460.440 |
| [results/profiling/direct-renderer-cpu-validation/profiles/cpu_2tx_1rx_direct_events.json](direct-renderer-cpu-validation/profiles/cpu_2tx_1rx_direct_events.json) — Local RF service | instrumented_profile | 2 | 2.048000 | 0.004096 | 0.039127 | 9.553 |
| [results/profiling/direct-renderer-cpu-validation/profiles/cpu_2tx_1rx_events.json](direct-renderer-cpu-validation/profiles/cpu_2tx_1rx_events.json) — Local RF service | instrumented_profile | 2 | 2.048000 | 0.004096 | 0.454616 | 110.990 |
| [results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-instrumented/measurements.json](p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 11.405662 | 45.623 |
| [results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-unprofiled/measurements.json](p100-adaptive-pipeline-full-20261008/profiles/cuda-100tx-10rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 11.169603 | 44.678 |
| [results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-instrumented/measurements.json](p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 1.682882 | 6.732 |
| [results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-unprofiled/measurements.json](p100-adaptive-pipeline-full-20261008/profiles/cuda-10tx-4rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 1.608367 | 6.433 |
| [results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-instrumented/measurements.json](p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 0.801219 | 3.205 |
| [results/profiling/p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-unprofiled/measurements.json](p100-adaptive-pipeline-full-20261008/profiles/cuda-2tx-2rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 0.763550 | 3.054 |
| [results/profiling/p100-basis-full-20261004/profiles/basis_cpu_100tx_1rx.json](p100-basis-full-20261004/profiles/basis_cpu_100tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 47.930034 | 191.716 |
| [results/profiling/p100-basis-full-20261004/profiles/basis_cpu_1tx_1rx.json](p100-basis-full-20261004/profiles/basis_cpu_1tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 0.667671 | 2.671 |
| [results/profiling/p100-basis-full-20261004/profiles/basis_cpu_4tx_1rx.json](p100-basis-full-20261004/profiles/basis_cpu_4tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 2.287211 | 9.149 |
| [results/profiling/p100-basis-full-20261004/profiles/basis_cuda_100tx_1rx.json](p100-basis-full-20261004/profiles/basis_cuda_100tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 3.691511 | 14.766 |
| [results/profiling/p100-basis-full-20261004/profiles/basis_cuda_1tx_1rx.json](p100-basis-full-20261004/profiles/basis_cuda_1tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 0.166860 | 0.667 |
| [results/profiling/p100-basis-full-20261004/profiles/basis_cuda_4tx_1rx.json](p100-basis-full-20261004/profiles/basis_cuda_4tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 0.186514 | 0.746 |
| [results/profiling/p100-basis-investigation-20261004/batch100.json](p100-basis-investigation-20261004/batch100.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 1.387056 | 16.644 |
| [results/profiling/p100-basis-investigation-20261004/batch16.json](p100-basis-investigation-20261004/batch16.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 1.367415 | 16.409 |
| [results/profiling/p100-basis-investigation-20261004/batch32.json](p100-basis-investigation-20261004/batch32.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 1.360671 | 16.328 |
| [results/profiling/p100-basis-investigation-20261004/batch8.json](p100-basis-investigation-20261004/batch8.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 1.234937 | 14.819 |
| [results/profiling/p100-basis-investigation-20261004/kernel_capture.json](p100-basis-investigation-20261004/kernel_capture.json) — Renderer call | unprofiled_basis_benchmark | 3 | 8.333500 | 0.025000 | 0.370067 | 14.802 |
| [results/profiling/p100-basis-optimization-20261004/blocks_warp/block1024.json](p100-basis-optimization-20261004/blocks_warp/block1024.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.608107 | 7.297 |
| [results/profiling/p100-basis-optimization-20261004/blocks_warp/block2048.json](p100-basis-optimization-20261004/blocks_warp/block2048.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.557221 | 6.687 |
| [results/profiling/p100-basis-optimization-20261004/blocks_warp/block4096.json](p100-basis-optimization-20261004/blocks_warp/block4096.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.819051 | 9.828 |
| [results/profiling/p100-basis-optimization-20261004/blocks_warp/block512.json](p100-basis-optimization-20261004/blocks_warp/block512.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.786747 | 9.441 |
| [results/profiling/p100-basis-optimization-20261004/blocks_warp/block8192.json](p100-basis-optimization-20261004/blocks_warp/block8192.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.970506 | 11.646 |
| [results/profiling/p100-basis-optimization-20261004/filters_dense/sortdouble_inplace0.json](p100-basis-optimization-20261004/filters_dense/sortdouble_inplace0.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.568020 | 6.816 |
| [results/profiling/p100-basis-optimization-20261004/filters_dense/sortdouble_inplace1.json](p100-basis-optimization-20261004/filters_dense/sortdouble_inplace1.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.590035 | 7.080 |
| [results/profiling/p100-basis-optimization-20261004/filters_dense/sortsingle_inplace0.json](p100-basis-optimization-20261004/filters_dense/sortsingle_inplace0.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.562100 | 6.745 |
| [results/profiling/p100-basis-optimization-20261004/filters_dense/sortsingle_inplace1.json](p100-basis-optimization-20261004/filters_dense/sortsingle_inplace1.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.572059 | 6.865 |
| [results/profiling/p100-basis-optimization-20261004/filters_warp/sortdouble_inplace0.json](p100-basis-optimization-20261004/filters_warp/sortdouble_inplace0.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.552373 | 6.628 |
| [results/profiling/p100-basis-optimization-20261004/filters_warp/sortdouble_inplace1.json](p100-basis-optimization-20261004/filters_warp/sortdouble_inplace1.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.562983 | 6.756 |
| [results/profiling/p100-basis-optimization-20261004/filters_warp/sortsingle_inplace0.json](p100-basis-optimization-20261004/filters_warp/sortsingle_inplace0.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.562625 | 6.751 |
| [results/profiling/p100-basis-optimization-20261004/filters_warp/sortsingle_inplace1.json](p100-basis-optimization-20261004/filters_warp/sortsingle_inplace1.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.563073 | 6.757 |
| [results/profiling/p100-basis-optimization-20261004/projections/dense100.json](p100-basis-optimization-20261004/projections/dense100.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.582844 | 6.994 |
| [results/profiling/p100-basis-optimization-20261004/projections/dense32.json](p100-basis-optimization-20261004/projections/dense32.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.652564 | 7.831 |
| [results/profiling/p100-basis-optimization-20261004/projections/dense8.json](p100-basis-optimization-20261004/projections/dense8.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 1.041719 | 12.500 |
| [results/profiling/p100-basis-optimization-20261004/projections/gather8.json](p100-basis-optimization-20261004/projections/gather8.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 1.220950 | 14.651 |
| [results/profiling/p100-basis-optimization-20261004/projections/gather8_repeat.json](p100-basis-optimization-20261004/projections/gather8_repeat.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 1.227131 | 14.725 |
| [results/profiling/p100-basis-optimization-20261004/projections/warp100.json](p100-basis-optimization-20261004/projections/warp100.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.554015 | 6.648 |
| [results/profiling/p100-basis-optimization-20261004/projections/warp32.json](p100-basis-optimization-20261004/projections/warp32.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.596403 | 7.157 |
| [results/profiling/p100-basis-optimization-20261004/projections/warp8.json](p100-basis-optimization-20261004/projections/warp8.json) — Renderer call | unprofiled_basis_benchmark | 10 | 8.333500 | 0.083335 | 0.795587 | 9.547 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_100tx_1rx.json](p100-basis-optimized-full-20261004/profiles/basis_cpu_100tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 48.514551 | 194.054 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_1tx_1rx.json](p100-basis-optimized-full-20261004/profiles/basis_cpu_1tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 0.661153 | 2.645 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_4tx_1rx.json](p100-basis-optimized-full-20261004/profiles/basis_cpu_4tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 2.362246 | 9.449 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json](p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 1.700125 | 6.800 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json](p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 0.167198 | 0.669 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json](p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 0.171683 | 0.687 |
| [results/profiling/p100-call-trace-20261008/followup_trace/measurements.json](p100-call-trace-20261008/followup_trace/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 10 | 8.333300 | 0.083333 | 4.187018 | 50.244 |
| [results/profiling/p100-call-trace-20261008/trace/measurements.json](p100-call-trace-20261008/trace/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 10 | 8.333300 | 0.083333 | 5.920980 | 71.052 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cpu-100tx-10rx-unprofiled/measurements.json](p100-end-to-end-full-20261005/profiles/cpu-100tx-10rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 221.088237 | 884.353 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cpu-10tx-4rx-unprofiled/measurements.json](p100-end-to-end-full-20261005/profiles/cpu-10tx-4rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 11.309370 | 45.237 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cpu-2tx-2rx-unprofiled/measurements.json](p100-end-to-end-full-20261005/profiles/cpu-2tx-2rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 2.294724 | 9.179 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-instrumented/measurements.json](p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 25.339303 | 101.357 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-unprofiled/measurements.json](p100-end-to-end-full-20261005/profiles/cuda-100tx-10rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 25.358207 | 101.433 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-instrumented/measurements.json](p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 2.010833 | 8.043 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-unprofiled/measurements.json](p100-end-to-end-full-20261005/profiles/cuda-10tx-4rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 1.961289 | 7.845 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-instrumented/measurements.json](p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 0.790174 | 3.161 |
| [results/profiling/p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-unprofiled/measurements.json](p100-end-to-end-full-20261005/profiles/cuda-2tx-2rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 0.732656 | 2.931 |
| [results/profiling/p100-gpu-block-sweep-20261008/block1024/measurements.json](p100-gpu-block-sweep-20261008/block1024/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 17.800179 | 71.201 |
| [results/profiling/p100-gpu-block-sweep-20261008/block4096/measurements.json](p100-gpu-block-sweep-20261008/block4096/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 25.544428 | 102.178 |
| [results/profiling/p100-gpu-block-sweep-20261008/block512/measurements.json](p100-gpu-block-sweep-20261008/block512/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 21.850550 | 87.402 |
| [results/profiling/p100-gpu-block-sweep-20261008/block8192/measurements.json](p100-gpu-block-sweep-20261008/block8192/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 29.534887 | 118.140 |
| [results/profiling/p100-gpu-block-sweep-20261008/control_after/measurements.json](p100-gpu-block-sweep-20261008/control_after/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 16.645006 | 66.580 |
| [results/profiling/p100-gpu-block-sweep-20261008/control_before/measurements.json](p100-gpu-block-sweep-20261008/control_before/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 16.574220 | 66.297 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json](p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 17.325668 | 69.303 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json](p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 37.925993 | 151.704 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json](p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 1.961967 | 7.848 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json](p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 4.343547 | 17.374 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json](p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 0.841250 | 3.365 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json](p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 1.336400 | 5.346 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json](p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 16.872901 | 67.492 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json](p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 16.589912 | 66.360 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json](p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 1.921751 | 7.687 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json](p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 1.851779 | 7.407 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json](p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 0.855329 | 3.421 |
| [results/profiling/p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json](p100-gpu-pipeline-opaque-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 0.808956 | 3.236 |
| [results/profiling/p100-gpu-system-20261007/comparison/baseline_cuda/measurements.json](p100-gpu-system-20261007/comparison/baseline_cuda/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 14.166577 | 170.000 |
| [results/profiling/p100-gpu-system-20261007/comparison/baseline_cuda_repeat/measurements.json](p100-gpu-system-20261007/comparison/baseline_cuda_repeat/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 7.091646 | 85.100 |
| [results/profiling/p100-gpu-system-20261007/comparison/fused_cuda/measurements.json](p100-gpu-system-20261007/comparison/fused_cuda/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 5.575912 | 66.911 |
| [results/profiling/p100-gpu-system-20261007/comparison/persistent_cuda/measurements.json](p100-gpu-system-20261007/comparison/persistent_cuda/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 5.660356 | 67.925 |
| [results/profiling/p100-gpu-system-20261007/comparison_shapes/baseline_cuda/measurements.json](p100-gpu-system-20261007/comparison_shapes/baseline_cuda/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 13.972078 | 167.666 |
| [results/profiling/p100-gpu-system-20261007/comparison_shapes/baseline_cuda_repeat/measurements.json](p100-gpu-system-20261007/comparison_shapes/baseline_cuda_repeat/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 6.972281 | 83.668 |
| [results/profiling/p100-gpu-system-20261007/comparison_shapes/fused_cuda/measurements.json](p100-gpu-system-20261007/comparison_shapes/fused_cuda/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 5.610920 | 67.331 |
| [results/profiling/p100-gpu-system-20261007/comparison_shapes/persistent_cuda/measurements.json](p100-gpu-system-20261007/comparison_shapes/persistent_cuda/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 5.622231 | 67.467 |
| [results/profiling/p100-gpu-system-20261007/gpu_pipeline_smoke/measurements.json](p100-gpu-system-20261007/gpu_pipeline_smoke/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 2 | 8.333500 | 0.016667 | 0.126940 | 7.616 |
| [results/profiling/p100-kernel-sweep-20261008/adaptive_after/measurements.json](p100-kernel-sweep-20261008/adaptive_after/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 12.198137 | 48.793 |
| [results/profiling/p100-kernel-sweep-20261008/adaptive_before/measurements.json](p100-kernel-sweep-20261008/adaptive_before/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 12.138095 | 48.552 |
| [results/profiling/p100-kernel-sweep-20261008/auto/measurements.json](p100-kernel-sweep-20261008/auto/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 11.077463 | 44.310 |
| [results/profiling/p100-kernel-sweep-20261008/auto_radix23/measurements.json](p100-kernel-sweep-20261008/auto_radix23/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 11.137921 | 44.552 |
| [results/profiling/p100-kernel-sweep-20261008/auto_trim_power2/measurements.json](p100-kernel-sweep-20261008/auto_trim_power2/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 12.024273 | 48.097 |
| [results/profiling/p100-kernel-sweep-20261008/auto_trim_radix23/measurements.json](p100-kernel-sweep-20261008/auto_trim_radix23/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 11.035508 | 44.142 |
| [results/profiling/p100-legacy-full-20261003/metrics/cpu_100tx_1rx.json](p100-legacy-full-20261003/metrics/cpu_100tx_1rx.json) — Local RF service | unprofiled_benchmark | 30 | 2.048000 | 0.061440 | 284.141762 | 4624.703 |
| [results/profiling/p100-legacy-full-20261003/metrics/cpu_2tx_1rx.json](p100-legacy-full-20261003/metrics/cpu_2tx_1rx.json) — Local RF service | unprofiled_benchmark | 200 | 2.048000 | 0.409600 | 74.521771 | 181.938 |
| [results/profiling/p100-legacy-full-20261003/metrics/cuda_100tx_1rx.json](p100-legacy-full-20261003/metrics/cuda_100tx_1rx.json) — Local RF service | unprofiled_benchmark | 30 | 2.048000 | 0.061440 | 284.691005 | 4633.643 |
| [results/profiling/p100-legacy-full-20261003/metrics/cuda_2tx_1rx.json](p100-legacy-full-20261003/metrics/cuda_2tx_1rx.json) — Local RF service | unprofiled_benchmark | 200 | 2.048000 | 0.409600 | 97.838452 | 238.863 |
| [results/profiling/p100-legacy-full-20261003/profiles/cuda_100tx_1rx_events.json](p100-legacy-full-20261003/profiles/cuda_100tx_1rx_events.json) — Local RF service | instrumented_profile | 5 | 2.048000 | 0.010240 | 47.512632 | 4639.906 |
| [results/profiling/p100-legacy-full-20261003/profiles/cuda_2tx_1rx_events.json](p100-legacy-full-20261003/profiles/cuda_2tx_1rx_events.json) — Local RF service | instrumented_profile | 5 | 2.048000 | 0.010240 | 2.427662 | 237.076 |
| [results/profiling/p100-legacy-quick-20261003/metrics/cuda_100tx_1rx.json](p100-legacy-quick-20261003/metrics/cuda_100tx_1rx.json) — Local RF service | unprofiled_benchmark | 2 | 2.048000 | 0.004096 | 18.905048 | 4615.490 |
| [results/profiling/p100-legacy-quick-20261003/profiles/cuda_100tx_1rx_events.json](p100-legacy-quick-20261003/profiles/cuda_100tx_1rx_events.json) — Local RF service | instrumented_profile | 2 | 2.048000 | 0.004096 | 19.191318 | 4685.380 |
| [results/profiling/p100-support-sweep-20261008/adaptive/measurements.json](p100-support-sweep-20261008/adaptive/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 12.168287 | 48.673 |
| [results/profiling/p100-support-sweep-20261008/adaptive_fused/measurements.json](p100-support-sweep-20261008/adaptive_fused/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 12.153854 | 48.615 |
| [results/profiling/p100-support-sweep-20261008/adaptive_single/measurements.json](p100-support-sweep-20261008/adaptive_single/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 11.996262 | 47.985 |
| [results/profiling/p100-support-sweep-20261008/adaptive_trim/measurements.json](p100-support-sweep-20261008/adaptive_trim/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 13.304801 | 53.219 |
| [results/profiling/p100-support-sweep-20261008/fixed_after/measurements.json](p100-support-sweep-20261008/fixed_after/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 16.193799 | 64.775 |
| [results/profiling/p100-support-sweep-20261008/fixed_before/measurements.json](p100-support-sweep-20261008/fixed_before/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 16.197047 | 64.788 |
| [results/profiling/p100-support-sweep-20261008/fixed_single/measurements.json](p100-support-sweep-20261008/fixed_single/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 15.967329 | 63.869 |
| [results/profiling/p100-support-sweep-20261008/fixed_trim/measurements.json](p100-support-sweep-20261008/fixed_trim/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 20.714566 | 82.858 |
| [results/profiling/p100-temporal-sweep-20261008/adaptive/measurements.json](p100-temporal-sweep-20261008/adaptive/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 12.543056 | 50.172 |
| [results/profiling/p100-temporal-sweep-20261008/adaptive_fused/measurements.json](p100-temporal-sweep-20261008/adaptive_fused/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 12.563432 | 50.254 |
| [results/profiling/p100-temporal-sweep-20261008/adaptive_single/measurements.json](p100-temporal-sweep-20261008/adaptive_single/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 12.331932 | 49.328 |
| [results/profiling/p100-temporal-sweep-20261008/fixed_after/measurements.json](p100-temporal-sweep-20261008/fixed_after/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 16.594010 | 66.376 |
| [results/profiling/p100-temporal-sweep-20261008/fixed_before/measurements.json](p100-temporal-sweep-20261008/fixed_before/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 16.563137 | 66.253 |
| [results/profiling/p100-temporal-sweep-20261008/fixed_single/measurements.json](p100-temporal-sweep-20261008/fixed_single/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 16.395130 | 65.581 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->


Use [P100_PROFILING.md](../../P100_PROFILING.md) to collect measurements.
Each run has its own directory, Markdown report, environment and raw JSON.
Publish with `scripts/publish_gpu_results.py`; large `raw/` artifacts stay local.
CPU-only validation reports and GPU compatibility failures must remain labelled
as such. Do not turn a CUDA selection flag into a GPU-performance claim.

## P100 measurements collected on 2026-10-03/04

- [Pinned-stack compatibility failure](p100-quick-20261003-2005/REPORT.md)
- [Exploratory legacy smoke run, incomplete](p100-legacy-quick-20261003/REPORT.md)
- [Full legacy CPU/CUDA service collection](p100-legacy-full-20261003/REPORT.md)
- [Legacy propagation-only scaling](p100-legacy-scaling-20261003/REPORT.md)

The working P100 stack uses Sionna 0.19.2 native propagation; current Sionna
2.2/custom-solver performance cannot be inferred from it. See the
[legacy harness](../../scripts/p100_legacy/README.md). The full run identifies
the host I/Q bottleneck; scaling omits I/Q to measure simultaneous propagation
and memory boundaries. Read each report's scope before comparing results.

## Updated CuPy Doppler-basis renderer on 2026-10-04

- [Initial quick run and startup investigation](p100-basis-quick-20261004/INVESTIGATION.md)
- [Full 30-window CPU/P100 collection](p100-basis-full-20261004/REPORT.md)
- [Findings and failed correctness qualification](p100-basis-full-20261004/FINDINGS.md)

CuPy executes FP64/complex128 rendering directly on the P100. No legacy Sionna
or ray tracing is involved. All six capture-level reference checks passed,
but the required suite failed its split-capture/Unix-timestamp test (six passes,
one failure). The overall result is **failed qualification**. At 100 TX the
observed GPU median was 122.671 ms versus 1593.948 ms on CPU; this diagnostic
renderer result misses the 8.333 ms target. See the scope and logs before use.

The [follow-up investigation](p100-basis-investigation-20261004/REPORT.md)
confirms substantial projection-kernel cost, finds no benefit from larger
link groups, and isolates the Unix-timestamp failure to oscillator-phase
rounding. It retains all workload budgets and applies no numerical repair.
