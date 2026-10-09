# P100 legacy Sionna profiling results

**Timing scope:** Historical local RF service; model/backend and timed region are specified below. [Common measurement definitions](../../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
Status: **COMPLETE — required collection tasks passed**.

**These results measure Sionna 0.19.2 native propagation plus the branch’s original I/Q/receiver chain. They do not measure the unchanged `profiling/p100` propagation solver.**

## Stack and workload

Legacy native Sionna Fibonacci solver; max_depth=1, LoS/reflection/scattering, scat_keep_prob=1, scat_random_phases=False. 1028 launched rays per TX, shared across receivers. Synthetic single-element arrays. Original terrain mesh and dielectric parameters (epsilon_r=5, conductivity=.01, scattering=.3), converted to legacy scene format; the legacy material has no thickness equivalent.

Original branch SDRNetworkReceiver, waveform synthesis, independent clocks, filtering, noise and ADC; external Paths adapter supplies compact legacy channels and platform Doppler.

4096 complex samples per capture at 2 MS/s, 915 MHz carrier, 1 MHz receive bandwidth, one receiver per benchmark; example uses two TX and two RX.

Not the profiling/p100 custom first-order sampler or Sionna 2.2 implementation. No numerical equivalence validation. Legacy rays and retained-path counts differ. Published current-solver CPU results and its work-count model are not directly comparable.

CPU cases hide GPUs from TensorFlow and use Mitsuba llvm_ad_rgb. CUDA cases use cuda_ad_rgb and TensorFlow CUDA. Dr.Jit uses two threads; TensorFlow thread defaults are not constrained.

Source branch commit: `720c4011522ad25c1e9c5c470bc20f4f34d480c5`. Repository code was not edited. The external harness is retained in `external_harness/`.

GPU inventory:
```text
index, uuid, name, driver_version, memory.total [MiB], compute_cap
0, GPU-0d70be84-560c-cf1e-8d49-c41015f45415, Tesla P100-PCIE-16GB, 580.178.04, 16384 MiB, 6.0
```

## Unprofiled service and channel timings

| Case | Epochs | Service median / p95 / max (ms) | Channel median (ms) | I/Q+receiver median (ms) | Updates/s | Misses 120 Hz / 200 Hz | Retained paths |
|---|---:|---:|---:|---:|---:|---:|---:|
| cpu_100tx_1rx | 30 | 9467.51 / 9553.16 / 9561.89 | 299.43 | 9168.54 | 0.106 | 30 / 30 | 47832–47835 |
| cpu_2tx_1rx | 200 | 371.25 / 384.18 / 427.33 | 207.24 | 163.75 | 2.684 | 200 / 200 | 845–857 |
| cuda_100tx_1rx | 30 | 9480.63 / 9554.35 / 9563.44 | 356.31 | 9113.75 | 0.105 | 30 / 30 | 47832–47835 |
| cuda_2tx_1rx | 200 | 488.51 / 501.13 / 551.26 | 324.09 | 163.06 | 2.044 | 200 / 200 | 845–859 |

Service includes poses, channel solve and synchronization/NumPy export, per-path waveform summation, per-link diagnostics, filtering, noise and ADC. Imports, setup, AirSim, transport, queueing and storage/plotting are excluded.

## Paired CPU/CUDA comparison

| TX | CPU/CUDA median service ratio | CPU/CUDA median channel ratio |
|---|---:|---:|
| 2 | 0.760× | 0.639× |
| 100 | 0.999× | 0.840× |

Ratios above 1 favor CUDA. Retained path counts and backend rounding may differ; these are paired workload timings, not a numerical equivalence claim.

## Startup and separate instrumented profiles

| Case | Preparation (ms) | First capture (ms) |
|---|---:|---:|
| cpu_100tx_1rx | 136.36 | 9570.67 |
| cpu_2tx_1rx | 142.18 | 490.34 |
| cuda_100tx_1rx | 2006.03 | 10435.59 |
| cuda_2tx_1rx | 1912.72 | 1463.37 |

First capture is a fresh process with existing disk caches; caches were not purged. Warmup counts are recorded; first-capture/timed-epoch data and available JIT cache/compilation metadata are retained.

Dr.Jit histories record its CUDA/OptiX operations only, not TensorFlow CUDA kernels. Inclusive host ranges overlap. Device-event sums are not service critical-path latency.

| CUDA profile | Timed epochs | Median Dr.Jit device-event sum (ms) | Median CUDA operation count | Median OptiX operation count |
|---|---:|---:|---:|---:|
| cuda_100tx_1rx_events | 5 | 0.590 | 7 | 5 |
| cuda_2tx_1rx_events | 5 | 0.386 | 7 | 5 |

Preflight: `ok`; 15 retained paths; 7 CUDA operations and 5 OptiX operations recorded.

Original host_numpy_sampling_ms and proposal_table_prepare_ms are adapter compatibility placeholders set to zero; they are not measured stage timings and are excluded from the report.

## Telemetry and task outcomes

```json
{
  "devices": {
    "GPU-0d70be84-560c-cf1e-8d49-c41015f45415": {
      "samples": 992,
      "index": "0",
      "max_sampled_memory_mib": 701.0,
      "max_sampled_utilization_percent": 15.0,
      "max_sampled_power_w": 36.0,
      "max_sampled_temperature_c": 43.0
    }
  },
  "note": "One-second nvidia-smi samples; includes other processes and may miss peaks. Not allocated-byte or guaranteed peak VRAM measurement."
}
```

Telemetry is sampled at one-second intervals and includes other GPU processes; it is not exact per-process peak allocation. Detailed host, driver, quotas and package versions are in `environment.json` and `installed_packages.json`.

| Task | Status | Log |
|---|---|---|
| cuda_preflight | ok | [logs/cuda_preflight.log](logs/cuda_preflight.log) |
| cpu_2tx_1rx | ok | [logs/cpu_2tx_1rx.log](logs/cpu_2tx_1rx.log) |
| cuda_2tx_1rx | ok | [logs/cuda_2tx_1rx.log](logs/cuda_2tx_1rx.log) |
| cuda_2tx_1rx_events | ok | [logs/cuda_2tx_1rx_events.log](logs/cuda_2tx_1rx_events.log) |
| nsys_2tx_1rx | unavailable | [optional](manifest.json) |
| cpu_100tx_1rx | ok | [logs/cpu_100tx_1rx.log](logs/cpu_100tx_1rx.log) |
| cuda_100tx_1rx | ok | [logs/cuda_100tx_1rx.log](logs/cuda_100tx_1rx.log) |
| cuda_100tx_1rx_events | ok | [logs/cuda_100tx_1rx_events.log](logs/cuda_100tx_1rx_events.log) |
| nsys_100tx_1rx | unavailable | [optional](manifest.json) |
| pluto_example | ok | [logs/pluto_example.log](logs/pluto_example.log) |

Nsight is optional and was unavailable unless the task table shows a successful capture. NVTX and Dr.Jit event profiling are retained separately from unprofiled performance runs.

The two-beacon/two-receiver example captures and plots are in `raw/example/`. No independent numerical or scientific correctness validation has been performed.

[Manifest](manifest.json) · [Scope](legacy_scope.json) · [Profile summary](profile_summary.json) · [Checksums](checksums.json)

Sampled telemetry is preserved in `telemetry/gpu_telemetry.csv.gz`; example plots, metadata and JSON summary are preserved in `example_summary/`. Binary I/Q captures remain local in `raw/example/`.

Measurement units and scope: [timing definitions](../../../docs/timing.md); [wall cost per simulated signal second](../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
