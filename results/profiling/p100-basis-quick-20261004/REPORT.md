# Doppler-basis renderer profiling: p100-basis-quick-20261004

**Timing scope:** Renderer-call wall service or separately labeled projection/kernel-call experiment; excludes propagation and receiver processing. [Common measurement definitions](../../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
Status: **FAILED / INCOMPLETE**.

**Interrupted diagnostic run:** no completed performance cases. See [startup investigation](INVESTIGATION.md) and the subsequent [full collection](../p100-basis-full-20261004/REPORT.md).

Renderer GPU status: `verified_cuda_cupy`. Source: `2a33cd27055ecf16f464f857e0af19e034637cf5`; dirty: `false`.

**Renderer-only:** synthetic changing channels, equal sample clocks, FP64/complex128, private source data and FFTs. All configured paths are valid. No ray tracing, source generation, clock resampling, noise/filter/ADC, AirSim or network/queueing is included.

Propagation: excluded; current pinned Dr.Jit does not support P100; legacy results retained separately. A successful renderer run does not establish current Sionna compatibility or complete RF service at 120 Hz.

## Unprofiled renderer-call wall service and serial throughput

| Backend | TX × RX | Valid paths/link | Samples | Median | p95 | p99 | Max | Windows/s | Misses 120 Hz | Accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| No successful measurements | — | — | — | — | — | — | — | — | — | — |

Timing includes fresh path-dependent setup, host validation/packing, private input uploads, GPU coefficient construction/projection, private FFTs, receiver summation and synchronized final output export. First-use/JIT time is recorded separately. Instrumented Nsight runs are excluded from this table.

The scene deadline is 8.333 ms. Default windows contain 16,667 samples at 2 MS/s (8.3335 ms of signal). Live input accumulation, interpolation lookahead and transport add delivery latency. This API exports a complete window; it is not yet a persistent continuous streaming receiver.

## Paired CPU/GPU renderer measurements

No qualified CPU/CUDA pair.

## Separate GPU stage spans and memory

One extra instrumented capture supplies CUDA-event spans and NVTX ranges. Event spans can include host submission/idle gaps, especially packing; they are not pure kernel execution times. Do not add these spans to wall latency. Use Nsight kernel/API statistics for execution-level attribution.


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
    "samples": 703,
    "index": "0",
    "max_sampled_memory_mib": 791.0,
    "max_sampled_utilization_percent": 6.0,
    "max_sampled_power_w": 32.08,
    "max_sampled_temperature_c": 43.0
  }
}

## Task outcomes

| Task | Status | Required | Log |
|---|---|---|---|
| basis_cuda_preflight | ok | True | [log](logs/basis_cuda_preflight.log) |
| basis_cuda_correctness | failed | True | [log](logs/basis_cuda_correctness.log) |
| basis_cpu_1tx_1rx | interrupted | True | [log](logs/basis_cpu_1tx_1rx.log) |

Run error: KeyboardInterrupt:

One P100 normally tests one receiver with 100 private TX inputs. `--rx 10` measures ten receivers sequentially on this GPU; it is not a ten-GPU fleet measurement. A renderer meeting the deadline still leaves propagation and mandatory receiver processing to qualify.

Large Nsight traces remain in ignored raw/. Small reports/JSON/logs can be published with scripts/publish_gpu_results.py.

Measurement units and scope: [timing definitions](../../../docs/timing.md); [wall cost per simulated signal second](../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
