# First-order radar CPU screening — 2026-10-23

The current radar acquires direct target echoes and first-order terrain backscatter. This replaces the earlier outbound/return path pairing. These are short **RF-only** timings, not a live AirSim flight, end-to-end dashboard latency, sustained tail qualification or GPU results.

The CPU is AMD EPYC 9V74, constrained to two cores; Dr.Jit uses two threads. Sionna RT 2.2.0, Mitsuba 3.9.1, Dr.Jit 1.5.0. Each new case measures ten warmed 4 ms windows (100 chirps, 256 ADC samples/chirp; 40,000 stream samples including gate gaps). Window origins repeat while the platform advances within each window. Stage timers add diagnostic host overhead. Raw files record source hashes, scenario hashes, first use and individual calls.

## Median ± sample standard deviation, milliseconds per 4 ms RF window

| Configuration | Geometry / visibility | Channel export | IF tone synthesis | Other acquisition work | Total |
|---|---:|---:|---:|---:|---:|
| Before: two-leg specular, east_clear (n=5) | 479.85 ± 15.48 | 11.10 ± 0.45 | Not separated | 255.18 ± 10.79¹ | 746.88 ± 25.68 |
| Before: two-leg specular, west_masked (n=5) | 444.41 ± 5.41 | 3.96 ± 0.18 | Not separated | 59.85 ± 1.57¹ | 507.38 ± 6.22 |
| [clear-targets](clear-targets.json) | 9.11 ± 0.25 | N/A² | 10.73 ± 0.59 | 36.32 ± 1.70 | 55.99 ± 2.36 |
| [masked-targets](masked-targets.json) | 8.79 ± 0.52 | N/A² | 5.97 ± 0.40 | 34.77 ± 1.75 | 49.57 ± 2.37 |
| [clear-clutter](clear-clutter.json) | 14.01 ± 0.69 | N/A² | 244.35 ± 6.23 | 82.31 ± 3.27 | 340.87 ± 9.50 |
| [masked-clutter](masked-clutter.json) | 14.22 ± 0.34 | N/A² | 207.72 ± 3.25 | 77.56 ± 2.61 | 298.80 ± 5.37 |
| [1024-valid-scatterers-targets](1024-valid-scatterers-targets.json) | 26.55 ± 1.99 | N/A² | 655.73 ± 33.22 | 1228.53 ± 75.71 | 1912.20 ± 104.75 |

¹ Historical other work includes IF synthesis, metadata extraction, noise and ADC. Old geometry timing is a Sionna path solve, not just direct segment visibility. [Unmodified prior CPU record](before-two-leg-cpu.json), taken from the hypothetical study on base `8a064a39612c4744ddcdf6a0fb1daf0f641b742a`. The old and new rows use the same window settings, viewpoints, CPU quota and library versions, but **different physical models**: this is not a matched-fidelity optimization ratio.

² First-order echoes are calculated directly on the host; there is no Sionna CIR export stage. Medians of individual stages need not add to the median total.

## 95th percentile, milliseconds per 4 ms RF window

| Configuration | Geometry / visibility | Channel export | IF tone synthesis | Other acquisition work | Total |
|---|---:|---:|---:|---:|---:|
| Before: east_clear (n=5) | 501.08 | 11.76 | Not separated | 269.05 | 781.64 |
| Before: west_masked (n=5) | 451.96 | 4.22 | Not separated | 62.13 | 516.71 |
| clear-targets | 9.50 | N/A | 11.62 | 39.41 | 60.25 |
| masked-targets | 9.64 | N/A | 6.71 | 37.77 | 53.73 |
| clear-clutter | 15.18 | N/A | 255.88 | 86.78 | 357.11 |
| masked-clutter | 14.54 | N/A | 209.26 | 81.02 | 304.20 |
| 1024-valid-scatterers-targets | 29.88 | N/A | 719.40 | 1365.29 | 2097.55 |

Percentiles use linear interpolation. These small samples do not establish long-run tail latency.

## Actual echo work and signal-time context

| Configuration | Target echoes, first chirp | Terrain echoes, first chirp | Measured wall seconds / signal second |
|---|---:|---:|---:|
| clear-targets | 3 | 0 | 14.15 |
| masked-targets | 0 | 0 | 12.50 |
| clear-clutter | 3 | 355 | 85.49 |
| masked-clutter | 0 | 296 | 74.46 |
| 1024-valid-scatterers-targets | 1024 | 0 | 481.07 |

The terrain budget is 1,024 fixed quadrature points over the configured map. Range, surface normal, antenna gain and occlusion reduce the survivors; they are not silently reported as 1,024 valid paths. The separate **1,024-valid-scatterers** stress uses a deterministic point cloud in an empty visibility scene, retains all 1,024 echoes per chirp, and includes the cost of per-target pose/metadata processing. It isolates dense echo work, not terrain tracing or a realistic target scene. No quadratic outbound/return pairing occurs in either case.

All rows remain slower than real time on this CPU. IF synthesis remains NumPy on the host, including on a GPU ray-tracing deployment. No GPU speedup or 120 Hz qualification is inferred. The former six-hour result was an extrapolation of a different, quadratic renderer, not a run to which these measurements can claim a validated speedup.

Excluded from all RF timers: AirSim RPC/physics, camera, network delivery/queueing, bulk recording, receiver skill/DSP and startup. Noise, ADC and gate packing are included. Writes are normal JSON output after measurement, not timed recording service.

## Reproduce

```bash
PYTHONPATH=src python benchmarks/benchmark_first_order_radar.py --iterations 10 --output /tmp/first-order-radar-results
```

Use the project CPU dependencies. This harness explicitly selects LLVM and does not measure CUDA. Compare raw stage fields across cases; do not substitute these RF-window timings for whole-flight latency. See the [model](../../../docs/radar-scattering.md) and [common timing conventions](../../../docs/timing.md).
