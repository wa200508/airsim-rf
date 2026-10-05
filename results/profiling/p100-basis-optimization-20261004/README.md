# P100 phase fix and projection experiments

Measured implementation: `316c1200cc76068e8412ae4bb4b6dab1355e6ae6`.
This is a completed projection comparison; FFT/filter and block-size experiments are still pending.

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
