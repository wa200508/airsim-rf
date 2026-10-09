# RF profiling results: direct-renderer-cpu-validation

**Timing scope:** Historical local RF service; model/backend and timed region are specified below. [Common measurement definitions](../../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
Status: **COMPLETE — CPU-only harness validation; no GPU result**.

GPU status: `not_requested`. Source: `720c4011522ad25c1e9c5c470bc20f4f34d480c5`; dirty: `True`.

Started: 2026-10-04T03:00:09.718954+00:00. Finished: 2026-10-04T03:02:02.456240+00:00.

Renderer and propagation backend are selected independently. Direct recurrence uses LLVM or CUDA; NumPy is the original renderer. Proposal draws, channel export and receiver filters/ADC remain CPU work. Direct CUDA timing includes per-link transfers and reduction.

## Environment

Host: `657a23c8c53a`. Python: `3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]`.
CPU quota: `200000 100000`; memory limit: `8589934592`. Detailed hardware, versions and source-file hashes: [environment.json](environment.json).

GPU inventory:

```text
[Errno 2] No such file or directory: 'nvidia-smi'
```

## Unprofiled latency and serial throughput

| Case | Epochs | Median service | p95 service | Max service | Updates/s | Median channel | Median I/Q+receiver | Misses 120/200 Hz |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| [cpu_100tx_1rx](metrics/cpu_100tx_1rx.json) | 2 | 11195.10 ms | 11283.25 ms | 11293.05 ms | 0.089 | 89.74 ms | 11105.04 ms | 2/2 |
| [cpu_100tx_1rx_direct](metrics/cpu_100tx_1rx_direct.json) | 2 | 394.09 ms | 397.23 ms | 397.58 ms | 2.537 | 64.24 ms | 329.51 ms | 2/2 |
| [cpu_2tx_1rx](metrics/cpu_2tx_1rx.json) | 3 | 230.23 ms | 230.23 ms | 230.24 ms | 4.363 | 11.77 ms | 217.18 ms | 3/3 |
| [cpu_2tx_1rx_direct](metrics/cpu_2tx_1rx_direct.json) | 3 | 32.31 ms | 85.95 ms | 91.91 ms | 19.235 | 8.64 ms | 23.16 ms | 3/3 |

Service includes local pose writes, synchronized propagation/export, waveform synthesis, diagnostic filters, noise, receiver filtering and ADC. It excludes AirSim RPC, network, queueing, storage and RF skill processing. First capture/setup are stored separately; disk JIT caches are not purged. Small sample counts do not establish latency tails.

## Paired CPU/CUDA comparison

No complete CPU/CUDA pair is available.

## Renderer comparison

| Case | Renderer | Median rendering including transfers | Median service |
|---|---|---:|---:|
| cpu_100tx_1rx | numpy | 11069.467 ms | 11195.098 ms |
| cpu_100tx_1rx_direct | direct-llvm | 310.161 ms | 394.091 ms |
| cpu_2tx_1rx | numpy | 215.806 ms | 230.228 ms |
| cpu_2tx_1rx_direct | direct-llvm | 22.221 ms | 32.310 ms |

Direct rendering retains all valid paths and their independent Dopplers. Default tiles: 128 paths × 32 recurrent samples; FP64 arithmetic with analytic phase reinitialization every sample tile. Temporary contribution buffers hold one path tile × the receive window, not all scene paths. See direct_renderer_correctness task for GPU numerical checks.


## Separate instrumented profiles

These instrumented runs are excluded from the performance table. CUDA-event sums are recorded device operation time, not critical-path latency. Host ranges are inclusive and nested; do not add them together.

### cpu_100tx_1rx_direct_events.json

Timed captures: 2; CUDA operations: 0; OptiX kernels: 0; NVTX available: False. Median CUDA event-time sum/capture: **0.000 ms**.

| Host range | Median inclusive time/capture | p95 |
|---|---:|---:|
| rf.channel.proposal_tables | 3.099 ms | 3.390 ms |
| rf.channel.host_proposal_draws | 16.078 ms | 16.894 ms |
| rf.channel.solve | 67.759 ms | 74.453 ms |
| rf.channel.export | 1.193 ms | 1.259 ms |
| rf.channel | 68.975 ms | 75.736 ms |
| rf.iq.waveforms | 330.623 ms | 360.131 ms |
| rf.iq.link_diagnostics | 17.843 ms | 18.858 ms |
| rf.receiver.noise_filter_adc | 0.411 ms | 0.456 ms |
| capture.timed | 423.348 ms | 447.231 ms |

Operation groups, compilation/cache metadata and original events: [profile_summary.json](profile_summary.json) and [raw event JSON](profiles/cpu_100tx_1rx_direct_events.json).

### cpu_100tx_1rx_events.json

Timed captures: 2; CUDA operations: 0; OptiX kernels: 0; NVTX available: False. Median CUDA event-time sum/capture: **0.000 ms**.

| Host range | Median inclusive time/capture | p95 |
|---|---:|---:|
| rf.channel.proposal_tables | 2.985 ms | 3.110 ms |
| rf.channel.host_proposal_draws | 16.062 ms | 16.278 ms |
| rf.channel.solve | 59.932 ms | 60.208 ms |
| rf.channel.export | 1.251 ms | 1.377 ms |
| rf.channel | 61.202 ms | 61.602 ms |
| rf.iq.waveforms | 11087.444 ms | 11108.538 ms |
| rf.iq.link_diagnostics | 26.474 ms | 26.507 ms |
| rf.receiver.noise_filter_adc | 0.374 ms | 0.383 ms |
| capture.timed | 11182.629 ms | 11203.986 ms |

Operation groups, compilation/cache metadata and original events: [profile_summary.json](profile_summary.json) and [raw event JSON](profiles/cpu_100tx_1rx_events.json).

### cpu_2tx_1rx_direct_events.json

Timed captures: 2; CUDA operations: 0; OptiX kernels: 0; NVTX available: False. Median CUDA event-time sum/capture: **0.000 ms**.

| Host range | Median inclusive time/capture | p95 |
|---|---:|---:|
| rf.channel.proposal_tables | 1.732 ms | 1.766 ms |
| rf.channel.host_proposal_draws | 0.702 ms | 0.721 ms |
| rf.channel.solve | 10.807 ms | 10.840 ms |
| rf.channel.export | 0.139 ms | 0.140 ms |
| rf.channel | 10.957 ms | 10.989 ms |
| rf.iq.waveforms | 7.364 ms | 7.418 ms |
| rf.iq.link_diagnostics | 0.426 ms | 0.427 ms |
| rf.receiver.noise_filter_adc | 0.422 ms | 0.449 ms |
| capture.timed | 19.492 ms | 19.500 ms |

Operation groups, compilation/cache metadata and original events: [profile_summary.json](profile_summary.json) and [raw event JSON](profiles/cpu_2tx_1rx_direct_events.json).

### cpu_2tx_1rx_events.json

Timed captures: 2; CUDA operations: 0; OptiX kernels: 0; NVTX available: False. Median CUDA event-time sum/capture: **0.000 ms**.

| Host range | Median inclusive time/capture | p95 |
|---|---:|---:|
| rf.channel.proposal_tables | 1.716 ms | 1.729 ms |
| rf.channel.host_proposal_draws | 0.635 ms | 0.643 ms |
| rf.channel.solve | 9.510 ms | 9.540 ms |
| rf.channel.export | 0.138 ms | 0.155 ms |
| rf.channel | 9.658 ms | 9.670 ms |
| rf.iq.waveforms | 216.322 ms | 219.255 ms |
| rf.iq.link_diagnostics | 0.552 ms | 0.558 ms |
| rf.receiver.noise_filter_adc | 0.338 ms | 0.341 ms |
| capture.timed | 227.223 ms | 230.170 ms |

Operation groups, compilation/cache metadata and original events: [profile_summary.json](profile_summary.json) and [raw event JSON](profiles/cpu_2tx_1rx_events.json).

## GPU telemetry

One-second nvidia-smi samples; includes other processes and may miss peaks. Not allocated-byte or guaranteed peak VRAM measurement.

GPU telemetry unavailable or disabled.

## Task outcomes and compatibility

| Task | Status | Required | Log |
|---|---|---|---|
| cpu_2tx_1rx | ok | True | [log](logs/cpu_2tx_1rx.log) |
| cpu_2tx_1rx_events | ok | True | [log](logs/cpu_2tx_1rx_events.log) |
| cpu_2tx_1rx_direct | ok | True | [log](logs/cpu_2tx_1rx_direct.log) |
| cpu_2tx_1rx_direct_events | ok | True | [log](logs/cpu_2tx_1rx_direct_events.log) |
| cpu_100tx_1rx | ok | True | [log](logs/cpu_100tx_1rx.log) |
| cpu_100tx_1rx_events | ok | True | [log](logs/cpu_100tx_1rx_events.log) |
| cpu_100tx_1rx_direct | ok | True | [log](logs/cpu_100tx_1rx_direct.log) |
| cpu_100tx_1rx_direct_events | ok | True | [log](logs/cpu_100tx_1rx_direct_events.log) |

## Artifacts and interpretation

* Benchmark JSON, profile summaries, environment, logs and checksums are intended for git publication.
* Large Nsight `.nsys-rep`/SQLite files, telemetry CSV and example I/Q/plots live in ignored `raw/`. Keep them locally or attach them to a release separately.
* Nsight timeline/statistics are optional. Missing tooling or profiler permissions are recorded; CUDA-event profiles remain useful.
* P100 lacks RT cores. RTX 4090 estimates in the architecture report are not predictions for this GPU.
* This is one receiver worker. Ten GPUs increase fleet parallelism, not one receiver’s speed.
* For a serial worker, a requested rate f needs f × mean service seconds < 1 for queue stability. Actual delivery latency also includes dispatch, transport and queueing.
* No numerical CPU/GPU equivalence claim follows from matching path counts; this bundle measures performance and basic smoke validity.

[Manifest](manifest.json) · [Device profile summaries](profile_summary.json) · [Telemetry summary](telemetry_summary.json) · [Checksums](checksums.json)

Measurement units and scope: [timing definitions](../../../docs/timing.md); [wall cost per simulated signal second](../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
