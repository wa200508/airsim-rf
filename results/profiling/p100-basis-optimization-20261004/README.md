# P100 phase fix and projection experiments

Measured implementation: `316c1200cc76068e8412ae4bb4b6dab1355e6ae6`.
Projection, delay-map/FFT ablations, and block-size experiments are complete. Projection results identify revision `316c120`; filter results identify `4b76412`; block results identify `3985b4f`.

The absolute oscillator phase fix preserves integer nanoseconds through rational modular arithmetic. The CUDA renderer now offers original gather, warp-cooperative gather, and dense FP64 cuBLAS projection. All retain all paths and complex128 output. The default projection remains gather.

Qualification: 63 CPU tests passed, 22 skipped; 6 profiling harness tests passed; final CUDA projection suite: 22 passed. The earlier CUDA logs record provisional failures from an unavailable CuPy API and missing cuBLAS library; both were corrected before qualification and timing. `cuda_projection_qualified.log` is the final projection qualification result.

Each comparison uses 100 independent transmitters, one receiver, 1,028 paths per link, 16,667 output samples, three warmup windows and ten timed windows. GPU throughput runs were sequential. All eight final-window accuracy checks passed. Median is synchronized wall time for the whole renderer call, including packing, upload, delay/basis construction, projection, private FFT convolution, coherent sum and download. It excludes propagation, startup, reference checks and downstream receiver processing.

| Projection | Link batch | Median ms |
|---|---:|---:|
| Gather | 8 | 122.130 |
| Warp | 8 | 79.462 |
| Dense FP64 | 8 | 103.982 |
| Warp | 32 | 59.470 |
| Dense FP64 | 32 | 65.240 |
| Warp | 100 | 55.048 |
| Dense FP64 | 100 | 56.950 |
| Gather repeat | 8 | 122.661 |

Best measured configuration is approximately 2.22 times faster than the original gather control. It still misses the 8.333 ms deadline for 120 Hz. Warp/100 final full-window CPU-basis normalized RMS error is 1.934e-12. These results concern the CuPy signal renderer on the P100 compatibility environment; they do not establish modern Sionna/DrJit CUDA propagation compatibility.

The environment used `airsim-rf:p100-optimization-env`, a layer over the existing profiling image adding `nvidia-cublas-cu12==12.2.5.6`. Current source was mounted read-only and launched through its updated `basis_launch.py`. DrJit CUDA was disabled while CuPy CUDA remained enabled. Commands and implementation revision are recorded in `projections/manifest.json`; individual JSON files contain timing, accuracy and source metadata.

## Filter and block-size experiments

All 76 CUDA qualification tests passed across three projections and four delay-map/FFT combinations, including high basis ranks, fresh private jobs, cancellation, Unix-epoch split windows and finite signal boundaries. Another 15 profiling-harness and SDR tests passed. A read-only pytest-cache warning does not affect qualification.

Ten-window medians with 100 links per batch:

| Delay sorting | FFT overwrite | Warp ms | Dense FP64 ms |
|---|---|---:|---:|
| Double | Off | 54.647 | 56.368 |
| Single | Off | 55.958 | 55.592 |
| Double | On | 56.489 | 59.496 |
| Single | On | 56.331 | 57.724 |

Every final-window reference comparison passed. These small differences do not establish a gain from reduced sorting; in-place FFT offers no demonstrated latency benefit. Retain double sorting and ordinary FFT for the recommended warp configuration.

| Warp block samples | Median ms |
|---:|---:|
| 512 | 77.610 |
| 1024 | 59.947 |
| 2048 | 54.660 |
| 4096 | 81.142 |
| 8192 | 96.213 |

All five block cases passed their reference checks. Block size changes temporal basis rank and FFT size while retaining the same requested tolerance and complete path set. The best tested block size remains 2,048. These are short comparisons, followed by a separate full collection with 30 timed windows per CPU/GPU case. A live snapshot during the block sweep showed 82% GPU utilization and 1,401 MiB resident device memory; it is an instantaneous observation, not peak memory or a suite-wide utilization average.

The renderer remains slower than the 120 Hz deadline. Reducing redundant sorting or allocations alone does not account for the remaining cost. Further gains require improving the actual FP64 projection/filter workload or amortizing repeated work under explicit channel/source reuse assumptions; this benchmark rebuilds changing channels and private source processing each capture.
