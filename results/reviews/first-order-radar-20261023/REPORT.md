# First-order radar CPU screening — 2026-10-23

The current radar acquires direct target echoes and first-order terrain backscatter. This replaces the earlier outbound/return path pairing. These are short **RF-only** timings, not a live AirSim flight, end-to-end dashboard latency, sustained tail qualification or GPU results.

The CPU is AMD EPYC 9V74, constrained to two cores; Dr.Jit uses two threads. Sionna RT 2.2.0, Mitsuba 3.9.1, Dr.Jit 1.5.0. Each new case measures ten warmed 4 ms windows (100 chirps, 256 ADC samples/chirp; 40,000 stream samples including gate gaps). Window origins repeat while the platform advances within each window. Stage timers add diagnostic host overhead. Raw files record source hashes, scenario hashes, first use and individual calls.

## Median ± sample standard deviation, milliseconds per 4 ms RF window

| Configuration | Geometry / visibility | Channel export | IF tone synthesis | Other acquisition work | Total |
|---|---:|---:|---:|---:|---:|
| Before: two-leg specular, east_clear (n=5) | 479.85 ± 15.48 | 11.10 ± 0.45 | Not separated | 255.18 ± 10.79¹ | 746.88 ± 25.68 |
| Before: two-leg specular, west_masked (n=5) | 444.41 ± 5.41 | 3.96 ± 0.18 | Not separated | 59.85 ± 1.57¹ | 507.38 ± 6.22 |
| [clear-targets](clear-targets.json) | 8.66 ± 0.30 | N/A² | 9.74 ± 0.41 | 33.14 ± 0.73 | 51.58 ± 1.11 |
| [masked-targets](masked-targets.json) | 9.17 ± 0.31 | N/A² | 6.20 ± 0.43 | 36.23 ± 1.19 | 51.48 ± 1.66 |
| [clear-clutter](clear-clutter.json) | 14.38 ± 0.36 | N/A² | 243.93 ± 4.10 | 79.59 ± 2.16 | 337.14 ± 5.83 |
| [masked-clutter](masked-clutter.json) | 14.51 ± 1.12 | N/A² | 214.69 ± 10.65 | 79.79 ± 2.70 | 309.54 ± 12.13 |
| [1024-valid-scatterers-targets](1024-valid-scatterers-targets.json) | 28.60 ± 2.35 | N/A² | 704.41 ± 37.02 | 1261.32 ± 54.42 | 1976.28 ± 82.38 |

¹ Historical other work includes IF synthesis, metadata extraction, noise and ADC. Old geometry timing is a Sionna path solve, not just direct segment visibility. [Unmodified prior CPU record](before-two-leg-cpu.json), taken from the hypothetical study on base `8a064a39612c4744ddcdf6a0fb1daf0f641b742a`. The old and new rows use the same window settings, viewpoints, CPU quota and library versions, but **different physical models**: this is not a matched-fidelity optimization ratio.

² First-order echoes are calculated directly on the host; there is no Sionna CIR export stage. Medians of individual stages need not add to the median total.

## 95th percentile, milliseconds per 4 ms RF window

| Configuration | Geometry / visibility | Channel export | IF tone synthesis | Other acquisition work | Total |
|---|---:|---:|---:|---:|---:|
| Before: east_clear (n=5) | 501.08 | 11.76 | Not separated | 269.05 | 781.64 |
| Before: west_masked (n=5) | 451.96 | 4.22 | Not separated | 62.13 | 516.71 |
| clear-targets | 9.07 | N/A | 10.51 | 34.36 | 53.56 |
| masked-targets | 9.68 | N/A | 6.97 | 37.71 | 54.00 |
| clear-clutter | 14.98 | N/A | 249.14 | 82.62 | 345.16 |
| masked-clutter | 16.51 | N/A | 233.24 | 83.24 | 331.22 |
| 1024-valid-scatterers-targets | 31.39 | N/A | 729.27 | 1370.57 | 2118.61 |

Percentiles use linear interpolation. These small samples do not establish long-run tail latency.

## Actual echo work and signal-time context

| Configuration | Target echoes, first chirp | Terrain echoes, first chirp | Measured wall seconds / signal second |
|---|---:|---:|---:|
| clear-targets | 3 | 0 | 12.99 |
| masked-targets | 0 | 0 | 12.91 |
| clear-clutter | 3 | 355 | 84.37 |
| masked-clutter | 0 | 296 | 77.79 |
| 1024-valid-scatterers-targets | 1024 | 0 | 497.97 |

The terrain budget is 1,024 fixed quadrature points over the configured map. Range, surface normal, antenna gain and occlusion reduce the survivors; they are not silently reported as 1,024 valid paths. The separate **1,024-valid-scatterers** stress uses a deterministic point cloud in an empty visibility scene, retains all 1,024 echoes per chirp, and includes the cost of per-target pose/metadata processing. It isolates dense echo work, not terrain tracing or a realistic target scene. No quadratic outbound/return pairing occurs in either case.

All rows remain slower than real time on this CPU. IF synthesis remains NumPy on the host, including on a GPU ray-tracing deployment. No GPU speedup or 120 Hz qualification is inferred. The former six-hour result was an extrapolation of a different, quadratic renderer, not a run to which these measurements can claim a validated speedup.

Excluded from all RF timers: AirSim RPC/physics, camera, network delivery/queueing, bulk recording, receiver skill/DSP and startup. Noise, ADC and gate packing are included. Writes are normal JSON output after measurement, not timed recording service.

## Reproduce

```bash
PYTHONPATH=src python benchmarks/benchmark_first_order_radar.py --iterations 10 --output /tmp/first-order-radar-results
```

Use the project CPU dependencies. This harness explicitly selects LLVM and does not measure CUDA. Compare raw stage fields across cases; do not substitute these RF-window timings for whole-flight latency. See the [model](../../../docs/radar-scattering.md) and [common timing conventions](../../../docs/timing.md).
