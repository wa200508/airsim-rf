# RF profiling results: p100-quick-20261003-2005

Status: **FAILED / INCOMPLETE**.

GPU status: `blocked`. Source: `720c4011522ad25c1e9c5c470bc20f4f34d480c5`; dirty: `false`.

Started: 2026-10-04T00:12:49.195248+00:00. Finished: 2026-10-04T00:20:07.981337+00:00.

This measures the existing hybrid implementation: propagation may use CUDA, but proposal draws and I/Q/receiver processing remain CPU work. GPU synthesis optimizations are not implemented by this branch.

## Environment

Host: `e345f07efb81`. Python: `3.12.14 (main, Sep 19 2026, 01:04:57) [GCC 14.2.0]`.
CPU quota: `max 100000`; memory limit: `max`. Detailed hardware, versions and source-file hashes: [environment.json](environment.json).

GPU inventory:

```text
index, uuid, name, driver_version, memory.total [MiB], compute_cap
0, GPU-0d70be84-560c-cf1e-8d49-c41015f45415, Tesla P100-PCIE-16GB, 580.178.04, 16384 MiB, 6.0
```

## Unprofiled latency and serial throughput

| Case | Epochs | Median service | p95 service | Max service | Updates/s | Median channel | Median CPU I/Q+receiver | Misses 120/200 Hz |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| No successful unprofiled measurements | — | — | — | — | — | — | — | — |

Service includes local pose writes, synchronized propagation/export, waveform synthesis, diagnostic filters, noise, receiver filtering and ADC. It excludes AirSim RPC, network, queueing, storage and RF skill processing. First capture/setup are stored separately; disk JIT caches are not purged. Small sample counts do not establish latency tails.

## Paired CPU/CUDA comparison

No complete CPU/CUDA pair is available.

## Separate instrumented profiles

These instrumented runs are excluded from the performance table. CUDA-event sums are recorded device operation time, not critical-path latency. Host ranges are inclusive and nested; do not add them together.

No completed instrumented profiles.
## GPU telemetry

One-second nvidia-smi samples; includes other processes and may miss peaks. Not allocated-byte or guaranteed peak VRAM measurement.

* `GPU-0d70be84-560c-cf1e-8d49-c41015f45415`: 430 samples; maximum sampled memory 519.0 MiB; utilization 0.0%; temperature 43.0 °C.

## Task outcomes and compatibility

| Task | Status | Required | Log |
|---|---|---|---|
| cuda_preflight | interrupted | True | [log](logs/cuda_preflight.log) |
| cuda_compatibility_diagnostic | failed | True | [log](logs/cuda_compatibility_diagnostic.log) |

Run error: `Dr.Jit 1.5.0 rejects P100 compute capability 6.0: requires >=7.5. Separate CUDA initialization diagnostic returned no compatible device. Original preflight interrupted after 7 minutes without completion.`.

## Artifacts and interpretation

* Benchmark JSON, profile summaries, environment, logs and checksums are intended for git publication.
* Large Nsight `.nsys-rep`/SQLite files, telemetry CSV and example I/Q/plots live in ignored `raw/`. Keep them locally or attach them to a release separately.
* Nsight timeline/statistics are optional. Missing tooling or profiler permissions are recorded; CUDA-event profiles remain useful.
* P100 lacks RT cores. RTX 4090 estimates in the architecture report are not predictions for this GPU.
* This is one receiver worker. Ten GPUs increase fleet parallelism, not one receiver’s speed.
* For a serial worker, a requested rate f needs f × mean service seconds < 1 for queue stability. Actual delivery latency also includes dispatch, transport and queueing.
* No numerical CPU/GPU equivalence claim follows from matching path counts; this bundle measures performance and basic smoke validity.

[Manifest](manifest.json) · [Device profile summaries](profile_summary.json) · [Telemetry summary](telemetry_summary.json) · [Checksums](checksums.json)
