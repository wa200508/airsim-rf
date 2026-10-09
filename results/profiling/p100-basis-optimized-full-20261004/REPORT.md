# Doppler-basis renderer profiling: p100-basis-optimized-full-20261004

**Timing scope:** Renderer-call wall service or separately labeled projection/kernel-call experiment; excludes propagation and receiver processing. [Common measurement definitions](../../../TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_100tx_1rx.json](profiles/basis_cpu_100tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 48.514551 | 194.054 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_1tx_1rx.json](profiles/basis_cpu_1tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 0.661153 | 2.645 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_4tx_1rx.json](profiles/basis_cpu_4tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 2.362246 | 9.449 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json](profiles/basis_cuda_100tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 1.700125 | 6.800 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json](profiles/basis_cuda_1tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 0.167198 | 0.669 |
| [results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json](profiles/basis_cuda_4tx_1rx.json) — Renderer call | unprofiled_basis_benchmark | 30 | 8.333500 | 0.250005 | 0.171683 | 0.687 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->


Status: **COMPLETE**.

Renderer GPU status: `verified_cuda_cupy`. Source: `3985b4f02f4e20e48cd1890d9c493317f5e76efc`; dirty: `false`.

**Renderer-only:** synthetic changing channels, equal sample clocks, FP64/complex128, private source data and FFTs. All configured paths are valid. No ray tracing, source generation, clock resampling, noise/filter/ADC, AirSim or network/queueing is included.

Propagation: excluded; current pinned Dr.Jit does not support P100; legacy results retained separately. A successful renderer run does not establish current Sionna compatibility or complete RF service at 120 Hz.

## Unprofiled renderer-call wall service and serial throughput

| Backend | TX × RX | Valid paths/link | Samples | Median | p95 | p99 | Max | Windows/s | Misses 120 Hz | Accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| [cpu](profiles/basis_cpu_100tx_1rx.json) | 100 × 1 | 1028 | 16667 | 1610.094 ms | 1700.364 ms | 1723.704 ms | 1732.190 ms | 0.618 | 30/30 | PASS |
| [cpu](profiles/basis_cpu_1tx_1rx.json) | 1 × 1 | 1028 | 16667 | 21.871 ms | 23.054 ms | 23.332 ms | 23.355 ms | 45.375 | 30/30 | PASS |
| [cpu](profiles/basis_cpu_4tx_1rx.json) | 4 × 1 | 1028 | 16667 | 78.495 ms | 84.624 ms | 84.926 ms | 85.007 ms | 12.700 | 30/30 | PASS |
| [cuda](profiles/basis_cuda_100tx_1rx.json) | 100 × 1 | 1028 | 16667 | 56.167 ms | 59.645 ms | 59.880 ms | 59.909 ms | 17.646 | 30/30 | PASS |
| [cuda](profiles/basis_cuda_1tx_1rx.json) | 1 × 1 | 1028 | 16667 | 5.508 ms | 6.139 ms | 6.192 ms | 6.209 ms | 179.428 | 0/30 | PASS |
| [cuda](profiles/basis_cuda_4tx_1rx.json) | 4 × 1 | 1028 | 16667 | 5.676 ms | 6.053 ms | 6.273 ms | 6.325 ms | 174.741 | 0/30 | PASS |

Timing includes fresh path-dependent setup, host validation/packing, private input uploads, GPU coefficient construction/projection, private FFTs, receiver summation and synchronized final output export. First-use/JIT time is recorded separately. Instrumented Nsight runs are excluded from this table.

The scene deadline is 8.333 ms. Default windows contain 16,667 samples at 2 MS/s (8.3335 ms of signal). Live input accumulation, interpolation lookahead and transport add delivery latency. This API exports a complete window; it is not yet a persistent continuous streaming receiver.

## Paired CPU/GPU renderer measurements

* 100 TX × 1 RX: observed CPU/CUDA median ratio **28.67×**; CUDA output rate **294102 samples/s per receiver**; remaining mean-latency factor to 120 Hz **6.80×**.
* 1 TX × 1 RX: observed CPU/CUDA median ratio **3.97×**; CUDA output rate **2990527 samples/s per receiver**; remaining mean-latency factor to 120 Hz **1.00×**.
* 4 TX × 1 RX: observed CPU/CUDA median ratio **13.83×**; CUDA output rate **2912401 samples/s per receiver**; remaining mean-latency factor to 120 Hz **1.00×**.

## Separate GPU stage spans and memory

One extra instrumented capture supplies CUDA-event spans and NVTX ranges. Event spans can include host submission/idle gaps, especially packing; they are not pure kernel execution times. Do not add these spans to wall latency. Use Nsight kernel/API statistics for execution-level attribution.

* [basis_cuda_100tx_1rx.json](profiles/basis_cuda_100tx_1rx.json), receiver 0: stage spans {'basis.host_pack_and_upload': 23.72870445251465, 'basis.delay_map': 5.111328125, 'basis.temporal_coefficients': 5.513888001441956, 'basis.path_projection': 17.667743921279907, 'basis.private_fft_filters': 15.082112163305283, 'basis.reconstruction_and_sum': 1.6864960081875324, 'basis.final_output_export': 0.10735999792814255}. Pool used/reserved 217302016/901671936 bytes; largest sampled pool-use checkpoint 322951168 bytes. Allocator snapshots include plans/cache and are not exact process peak VRAM.
* [basis_cuda_1tx_1rx.json](profiles/basis_cuda_1tx_1rx.json), receiver 0: stage spans {'basis.host_pack_and_upload': 0.3802559971809387, 'basis.delay_map': 1.7111680507659912, 'basis.temporal_coefficients': 2.0912640392780304, 'basis.path_projection': 1.166655994951725, 'basis.private_fft_filters': 3.807423949241638, 'basis.reconstruction_and_sum': 3.650624096393585, 'basis.final_output_export': 0.18038399517536163}. Pool used/reserved 2446336/9288192 bytes; largest sampled pool-use checkpoint 3502080 bytes. Allocator snapshots include plans/cache and are not exact process peak VRAM.
* [basis_cuda_4tx_1rx.json](profiles/basis_cuda_4tx_1rx.json), receiver 0: stage spans {'basis.host_pack_and_upload': 1.1867519617080688, 'basis.delay_map': 1.7798080444335938, 'basis.temporal_coefficients': 2.063423991203308, 'basis.path_projection': 1.2861439883708954, 'basis.private_fft_filters': 1.1749440133571625, 'basis.reconstruction_and_sum': 0.27692800387740135, 'basis.final_output_export': 0.284960001707077}. Pool used/reserved 8990208/36327936 bytes; largest sampled pool-use checkpoint 13215744 bytes. Allocator snapshots include plans/cache and are not exact process peak VRAM.

## Accuracy and hardware

Every benchmark compares all receiver output samples against CPU basis reconstruction, checks all paths of all links in initial/final sample prefixes against direct rendering, and checks complete direct output for the first/last transmitter of each receiver. Tests cover cancellation, changed channels, split captures, finite boundaries and Unix timestamps. Error is relative to the finite interpolation operator; ideal-sinc/noise-floor qualification remains separate.

CPU quota: `max 100000`. Hardware, pinned packages and source hashes: [environment.json](environment.json) and [installed_packages.json](installed_packages.json).

```text
index, uuid, name, driver_version, memory.total [MiB], compute_cap
0, GPU-0d70be84-560c-cf1e-8d49-c41015f45415, Tesla P100-PCIE-16GB, 580.178.04, 16384 MiB, 6.0
```

One-second nvidia-smi samples; includes other processes and may miss peaks. Not allocated-byte or guaranteed peak VRAM measurement.

{
  "GPU-0d70be84-560c-cf1e-8d49-c41015f45415": {
    "samples": 89,
    "index": "0",
    "max_sampled_memory_mib": 1401.0,
    "max_sampled_utilization_percent": 83.0,
    "max_sampled_power_w": 146.51,
    "max_sampled_temperature_c": 45.0
  }
}

## Task outcomes

| Task | Status | Required | Log |
|---|---|---|---|
| basis_cuda_preflight | ok | True | [log](logs/basis_cuda_preflight.log) |
| basis_cuda_correctness | ok | True | [log](logs/basis_cuda_correctness.log) |
| basis_cpu_1tx_1rx | ok | True | [log](logs/basis_cpu_1tx_1rx.log) |
| basis_cuda_1tx_1rx | ok | True | [log](logs/basis_cuda_1tx_1rx.log) |
| basis_cpu_4tx_1rx | ok | True | [log](logs/basis_cpu_4tx_1rx.log) |
| basis_cuda_4tx_1rx | ok | True | [log](logs/basis_cuda_4tx_1rx.log) |
| basis_cpu_100tx_1rx | ok | True | [log](logs/basis_cpu_100tx_1rx.log) |
| basis_cuda_100tx_1rx | ok | True | [log](logs/basis_cuda_100tx_1rx.log) |
| nsys_basis_cuda_100tx_1rx | unavailable | False | Nsight absent; separate CUDA-event stage spans still collected |

One P100 normally tests one receiver with 100 private TX inputs. `--rx 10` measures ten receivers sequentially on this GPU; it is not a ten-GPU fleet measurement. A renderer meeting the deadline still leaves propagation and mandatory receiver processing to qualify.

Large Nsight traces remain in ignored raw/. Small reports/JSON/logs can be published with scripts/publish_gpu_results.py.

