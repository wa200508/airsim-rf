# P100 Doppler-basis renderer findings

**Collection completed; correctness qualification failed.** Source: `b4d48f5e432b5610eb3fedfa854bf9d5347cd2cb`, including the launcher workaround over pulled commit `2a33cd2`.

The required CUDA suite returned **6 passed, 1 failed** in 2.10 s. `test_real_cuda_split_unix_epoch_cancellation_and_boundaries` failed when concatenating split captures at epoch 1790000000000000000 ns. Maximum absolute disagreement was approximately 0.101475, maximum relative disagreement 0.013941. See [test log](logs/basis_cuda_correctness.log). The CPU and GPU basis implementations both form oscillator phase from an absolute timestamp converted to floating-point seconds; loss of phase precision is a candidate cause, not a repaired or fully isolated diagnosis.

All six 30-window CPU/GPU benchmarks completed and passed their own whole-output and direct-reference checks at their configured timestamps. Those local checks do not supersede the failed suite. Timings describe this renderer/workload and must not be presented as fully qualified 120 Hz service.

| Independent TX / 1 RX | CPU median | GPU median | CPU/GPU ratio | GPU 120 Hz misses |
|---:|---:|---:|---:|---:|
| 1 | 22.149 ms | 5.510 ms | 4.02x | 0/30 |
| 4 | 75.140 ms | 6.157 ms | 12.20x | 0/30 |
| 100 | 1593.948 ms | 122.671 ms | 12.99x | 30/30 |

100 TX achieved 8.127 windows/s and needs about 14.77x lower mean latency to reach 120 Hz. Each window contains 16,667 complex outputs at 2 MS/s and 1,028 valid paths per independent link. Private input uploads, fresh channel construction and FFTs are included; ray tracing and receiver DSP are excluded. This CuPy renderer does not use legacy Sionna, nor establish current Sionna propagation compatibility.

The separate instrumented 100-TX capture's largest CUDA-event stage span was path projection (64.74 ms), followed by private FFT filters (23.45 ms) and delay mapping (19.88 ms). These event spans can include host submission gaps and are not kernel-only or throughput timings. Nsight was unavailable.

One-second telemetry sampled up to 625 MiB whole-GPU memory and 88% busy, including other processes. GPU allocation pressure was not the observed limit in these default renderer cases. This is a different workload from the earlier legacy propagation-only scaling experiment. No larger scaling cases were run.

`DRJIT_LIBCUDA_PATH=/tmp/disabled-drjit-cuda.so` intentionally disables Dr.Jit's unsupported CUDA backend for CPU references; CuPy still executes on the P100. `DRJIT_CACHE_DIR=/tmp/drjit-cache` makes LLVM caching writable. Exact image metadata, source hashes, packages and synchronized profiles are included. The only source adjustment was to the Docker profiling launcher and its documentation; numerical implementation and qualification tolerances were unchanged.

Telemetry samples are archived in `telemetry/gpu_telemetry.csv.gz`. Large raw artifacts stay local. See [report](REPORT.md), [manifest](manifest.json), [checksums](checksums.json), and [initial investigation](../p100-basis-quick-20261004/INVESTIGATION.md).
