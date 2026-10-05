# Current runtime: measured results, estimates and excluded work

Updated **2026-10-05**. This is the current runtime summary. Earlier reports
retain historical experiments and conditional GPU arithmetic; they do not
override the workload and measurements here. The [README](README.md) presents
the same measured table, generated from the published JSON.

**No complete moving-scene, continuous-I/Q simulation has been demonstrated
at real time.** The qualified 100-TX/one-RX renderer runs approximately 194×
slower than real time on the measured CPU and 6.80× slower on the P100.
These are different hardware/backend results, not a universal project slowdown.

## Comparable continuous-I/Q renderer measurements

Each call produces **16,667 complex samples at 2 MS/s** into one receiver,
approximately 8.3335 ms of signal. The scene-update target is **120 Hz**, giving
an 8.3333 ms service budget and 72,000 calls for ten simulated minutes. The
extra fractional sample per window is negligible for these conversions; a
future continuous scheduler must account for sample counts exactly.

Every link contains **1,028 valid paths**. Inputs are arbitrary sampled I/Q,
with private buffers and transforms per directed link. All cases use FP64 /
complex128, 32-tap finite interpolation, a declared 100-microsecond delay bound,
physical Doppler bounds of ±2,500 Hz and temporal tolerance 1e-10. Doppler
phase evolves per output sample; source clocks are equal.

These measurements qualify only the declared delay/Doppler support. Wider
support, more paths or unequal sample clocks require separate measurements;
basis rank and filter costs can grow substantially. They do not establish a
uniform runtime for every arbitrary waveform and scene.

<!-- BEGIN MEASURED RUNTIME TABLE -->

| Backend / TX → RX | Median window latency | p95 | Wall time / simulated time | Rendering cost for 10 simulated minutes |
| --- | ---: | ---: | ---: | ---: |
| [CPU, 100 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_100tx_1rx.json) | 1610.09 ms | 1700.36 ms | 194.06× | 32.34 h |
| [P100 CUDA, 100 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json) | 56.17 ms | 59.65 ms | 6.80× | 68.00 min |
| [CPU, 4 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_4tx_1rx.json) | 78.49 ms | 84.62 ms | 9.45× | 94.49 min |
| [P100 CUDA, 4 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json) | 5.68 ms | 6.05 ms | 0.69× | 6.87 min |
| [CPU, 1 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_1tx_1rx.json) | 21.87 ms | 23.05 ms | 2.64× | 26.45 min |
| [P100 CUDA, 1 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json) | 5.51 ms | 6.14 ms | 0.67× | 6.69 min |

<!-- END MEASURED RUNTIME TABLE -->

Median/p95 describe one warmed, synchronized, preloaded-window renderer call.
**Wall/simulated time = mean call milliseconds × 120 / 1,000.** A ratio of
6.80× means 6.80 wall-clock seconds of rendering work per simulated second;
0.69× means renderer throughput has headroom, not that the complete simulation
has achieved real time. Ten-minute costs multiply the mean of 30 timed windows
by 72,000; they are extrapolations, not ten-minute flight measurements.

Evidence: [qualified collection](results/profiling/p100-basis-optimized-full-20261004/REPORT.md),
[findings](results/profiling/p100-basis-optimized-full-20261004/FINDINGS.md),
[hardware record](results/profiling/p100-basis-optimized-full-20261004/environment.json).
The CPU host was **AMD Ryzen 7 8700G with Radeon 780M graphics**, with 16 logical
CPUs visible and no cgroup CPU quota. The CPU renderer requested **two FFT
workers**; this is not a two-core quota or an all-core Ryzen benchmark. The
GPU was a **Tesla P100-PCIE-16GB**. The integrated Radeon was not used. CuPy
CUDA rendering does not run on that AMD GPU.

The selected GPU configuration is warp-cooperative projection, 100 links per
batch, 2,048-sample blocks, double-sort delay mapping and ordinary FFTs. The
mandatory CUDA suite passed 76 tests. Each timing case's final window passed
the reference comparisons; the suite did not compare every timed window.

## Processing steps by scenario and configuration

All stage timings below are **milliseconds per measured call**. The first table
shows **median ± sample standard deviation**, calculated from the individual
warmed captures (n−1 denominator). The ± value describes observed variability;
it is not a confidence interval, accuracy tolerance or deadline guarantee.
The second table uses the same captures and columns for **p95**, with linear
percentile interpolation. Startup and warmup captures are excluded.

**— means unavailable or outside the measured scope, never zero.** GPU totals
have 30 captures, but detailed GPU steps have only one separate instrumented
capture. Those observations appear in their own table below.

Read the columns from left to right:

- **Pose update:** write moving-platform positions into the propagation scene.
- **Scene propagation:** trace/evaluate paths and export the channel to NumPy.
- **Render preparation:** validate inputs, construct fractional-delay maps and apply link gains.
- **Basis/filter construction:** compute temporal coefficients, evolve path phase and project paths into delay filters.
- **FFT + reconstruction:** private source/filter transforms, convolution, per-sample basis reconstruction and oscillator phase.
- **Other rendering work:** same-capture residual outside those three CPU timers, including basis setup, bookkeeping, error bounds and wrapper summation.
- **Signal rendering subtotal:** complete timed renderer call, including its internal steps. **Do not add this subtotal to those steps again.**
- **Receiver processing:** noise, receiver filters, diagnostics and ADC conversion. Historical direct-SDR rows include rendering in this column because those captures did not time rendering separately.
- **Measured call total:** outer synchronized wall timer. For basis tests this is renderer-only; for historical SDR/LLVM tests it includes poses, propagation and receiver processing.

Stage medians and p95 values need not sum to the call median or p95: each column
is summarized independently. AirSim physics/RPC, transport, queueing, storage and
RF-skill processing were not measured in any of these rows.

The six basis rows use the qualified Ryzen 7 8700G/P100 setup and 1,028 valid
paths per link described above. Historical SDR/LLVM rows use an earlier CPU
container with a two-core quota, tones, independent receiver clocks and an
800-triangle terrain scene; surviving path counts vary with capture. Their
4,096 samples represent **2.048 ms**, plus 256 filter-warmup samples, rather
than the basis workload’s 8.3335 ms. They provide historical pipeline context,
not a matched speed comparison or a full simulation runtime prediction.

<!-- BEGIN STAGE TIMING TABLES -->

### Median ± sample standard deviation

| Configuration / raw captures | n | Pose update | Scene propagation | Render preparation | Basis/filter construction | FFT + reconstruction | Other rendering work | Signal rendering subtotal | Receiver processing | Measured call total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [CPU basis, 100 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_100tx_1rx.json) | 30 | — | — | 90.54 ± 5.73 | 1106.72 ± 16.29 | 397.92 ± 16.77 | 12.31 ± 1.76 | 1610.09 ± 36.60 | — | 1610.09 ± 36.60 |
| [P100 basis, 100 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json) | 30 | — | — | — | — | — | — | 56.17 ± 2.13 | — | 56.17 ± 2.13 |
| [CPU basis, 4 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_4tx_1rx.json) | 30 | — | — | 4.54 ± 0.27 | 45.69 ± 1.11 | 25.57 ± 2.41 | 2.61 ± 0.29 | 78.49 ± 3.38 | — | 78.49 ± 3.38 |
| [P100 basis, 4 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json) | 30 | — | — | — | — | — | — | 5.68 ± 0.18 | — | 5.68 ± 0.18 |
| [CPU basis, 1 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_1tx_1rx.json) | 30 | — | — | 1.01 ± 0.05 | 11.96 ± 0.15 | 7.64 ± 0.34 | 1.30 ± 0.10 | 21.87 ± 0.51 | — | 21.87 ± 0.51 |
| [P100 basis, 1 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json) | 30 | — | — | — | — | — | — | 5.51 ± 0.29 | — | 5.51 ± 0.29 |
| [CPU direct SDR, 2 → 1; 4,096 samples (historical)](benchmarks/results/sdr_cpu_2tx_1rx.json) | 30 | 0.04 ± 0.01 | 23.11 ± 2.16 | — | — | — | — | — | 217.74 ± 13.78 | 240.86 ± 14.10 |
| [CPU direct SDR, 2 → 2; 4,096 samples (historical)](benchmarks/results/sdr_cpu_2tx_2rx.json) | 30 | 0.05 ± 0.01 | 19.59 ± 1.55 | — | — | — | — | — | 389.74 ± 18.89 | 410.42 ± 19.08 |
| [CPU direct SDR, 100 → 1; 4,096 samples (historical)](benchmarks/results/sdr_cpu_100tx_1rx.json) | 10 | 0.32 ± 0.04 | 681.65 ± 25.46 | — | — | — | — | — | 10846.50 ± 121.42 | 11522.77 ± 131.40 |
| [CPU LLVM per-link, 100 → 1; 4,096 samples (historical)](research_results/batched_renderer_cpu/per_link_local.json) | 10 | 0.25 ± 0.04 | 65.20 ± 7.19 | — | — | — | — | 189.40 ± 10.82 | 16.04 ± 1.51 | 274.03 ± 16.89 |
| [CPU LLVM tile 32, 100 → 1; 4,096 samples (historical)](research_results/batched_renderer_cpu/batched_32.json) | 10 | 0.29 ± 0.02 | 60.71 ± 3.23 | — | — | — | — | 170.32 ± 7.00 | 11.00 ± 0.47 | 247.32 ± 7.65 |
| [CPU LLVM tile 128, 100 → 1; 4,096 samples (historical)](research_results/batched_renderer_cpu/batched_128.json) | 10 | 0.29 ± 0.01 | 61.25 ± 2.53 | — | — | — | — | 169.87 ± 11.05 | 10.50 ± 0.54 | 243.25 ± 12.94 |

### 95th percentile

| Configuration / raw captures | n | Pose update | Scene propagation | Render preparation | Basis/filter construction | FFT + reconstruction | Other rendering work | Signal rendering subtotal | Receiver processing | Measured call total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [CPU basis, 100 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_100tx_1rx.json) | 30 | — | — | 99.11 | 1143.81 | 439.91 | 16.47 | 1700.36 | — | 1700.36 |
| [P100 basis, 100 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json) | 30 | — | — | — | — | — | — | 59.65 | — | 59.65 |
| [CPU basis, 4 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_4tx_1rx.json) | 30 | — | — | 4.84 | 48.20 | 29.37 | 3.12 | 84.62 | — | 84.62 |
| [P100 basis, 4 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json) | 30 | — | — | — | — | — | — | 6.05 | — | 6.05 |
| [CPU basis, 1 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_1tx_1rx.json) | 30 | — | — | 1.12 | 12.23 | 8.37 | 1.42 | 23.05 | — | 23.05 |
| [P100 basis, 1 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json) | 30 | — | — | — | — | — | — | 6.14 | — | 6.14 |
| [CPU direct SDR, 2 → 1; 4,096 samples (historical)](benchmarks/results/sdr_cpu_2tx_1rx.json) | 30 | 0.05 | 25.16 | — | — | — | — | — | 237.02 | 259.32 |
| [CPU direct SDR, 2 → 2; 4,096 samples (historical)](benchmarks/results/sdr_cpu_2tx_2rx.json) | 30 | 0.07 | 23.02 | — | — | — | — | — | 427.63 | 446.71 |
| [CPU direct SDR, 100 → 1; 4,096 samples (historical)](benchmarks/results/sdr_cpu_100tx_1rx.json) | 10 | 0.39 | 733.15 | — | — | — | — | — | 11017.94 | 11729.99 |
| [CPU LLVM per-link, 100 → 1; 4,096 samples (historical)](research_results/batched_renderer_cpu/per_link_local.json) | 10 | 0.32 | 78.09 | — | — | — | — | 211.45 | 18.89 | 302.43 |
| [CPU LLVM tile 32, 100 → 1; 4,096 samples (historical)](research_results/batched_renderer_cpu/batched_32.json) | 10 | 0.31 | 67.66 | — | — | — | — | 183.58 | 11.82 | 256.45 |
| [CPU LLVM tile 128, 100 → 1; 4,096 samples (historical)](research_results/batched_renderer_cpu/batched_128.json) | 10 | 0.31 | 66.05 | — | — | — | — | 196.07 | 11.09 | 272.31 |

### GPU stage observations: one instrumented capture per configuration

These are CUDA-event spans, in ms, from a separate capture. **n = 1; no standard deviation or p95 is available.** They include dispatch gaps and profiling overhead, and must not be added to the unprofiled median above.

| Configuration | Pack + upload | Delay map | Temporal coefficients | Path → filter projection | Private FFT filters | Reconstruction + sum | Output export | Instrumented wall total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [P100 basis, 100 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json) | 23.73 | 5.11 | 5.51 | 17.67 | 15.08 | 1.69 | 0.11 | 69.36 |
| [P100 basis, 4 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json) | 1.19 | 1.78 | 2.06 | 1.29 | 1.17 | 0.28 | 0.28 | 8.94 |
| [P100 basis, 1 → 1; 16,667 samples](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json) | 0.38 | 1.71 | 2.09 | 1.17 | 3.81 | 3.65 | 0.18 | 14.15 |

### End-to-end RF pipeline: median ± sample standard deviation

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cpu; AMD EPYC 9V74 80-Core Processor](results/end_to_end/cpu-100tx-10rx-20261005/measurements.json) | 5 | 0.002 ± 0.000 | 54.178 ± 2.301 | 1186.283 ± 108.425 | 10615.410 ± 429.415 | 12.070 ± 0.255 | 88.654 ± 1.960 | 15.093 ± 3.193 | 11986.071 ± 499.771 |
| [10 → 4, basis-cpu; AMD EPYC 9V74 80-Core Processor](results/end_to_end/cpu-10tx-4rx-20261005/measurements.json) | 10 | 0.003 ± 0.000 | 6.085 ± 0.594 | 105.786 ± 32.761 | 493.207 ± 18.241 | 4.571 ± 1.246 | 7.243 ± 0.778 | 6.468 ± 1.211 | 620.592 ± 32.685 |

### End-to-end RF pipeline: p95

| Configuration / raw captures | n | Truth advance | Private sources | Scene propagation | Signal rendering | Noise/filter/ADC | Bridge + other RF work | Delivery + storage | Complete update |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [100 → 10, basis-cpu; AMD EPYC 9V74 80-Core Processor](results/end_to_end/cpu-100tx-10rx-20261005/measurements.json) | 5 | 0.002 | 57.731 | 1353.061 | 11108.158 | 12.203 | 89.477 | 20.940 | 12571.095 |
| [10 → 4, basis-cpu; AMD EPYC 9V74 80-Core Processor](results/end_to_end/cpu-10tx-4rx-20261005/measurements.json) | 10 | 0.003 | 7.042 | 126.508 | 520.594 | 6.852 | 8.558 | 8.899 | 654.255 |

All timings are ms per fleet update. Source generation, propagation, continuous receiver filtering/noise/ADC, loopback HTTP delivery and consumer file readback are included. Sionna propagation is LLVM CPU even with CuPy rendering. Receivers execute serially. The default truth source implements the AirSim contract; it does not run live AirSim physics/RPC or AMS-GRA distributed SDR workers. Startup/warmup are excluded from these tables, physical path counts and hardware/quota are in the linked JSON, and five-/ten-window historical runs do not qualify long-run tail latency.

<!-- END STAGE TIMING TABLES -->

The raw-capture links are the sources for every number. On `profiling/p100`,
regenerate these tables with `python scripts/update_profiling_breakdown.py`,
or verify them with `python scripts/update_profiling_breakdown.py --check`.
The historical renderer-only GPU captures above have just one instrumented
observation. For repeated full-pipeline wall timings and CUDA stage distributions,
use the [P100 end-to-end collector](P100_BASIS_PROFILING.md#complete-rf-pipeline-fill-every-stage-row).
It imports only validated complete bundles and keeps instrumented GPU event
statistics separate from unprofiled latency. No new P100 measurements are
claimed until such a bundle is collected and published.

## Your ten-minute flight: 10 moving TX and four moving RX

This is **40 independent directed links**, rather than the 100-link case in
each measured receiver row. There is no measured 10-TX/four-RX moving-scene
run on the requested home processor. The exact processor referred to as
"Ryzen 7100" remains unidentified; do not silently substitute the recorded
8700G for it.

A CPU-only, serial cost extrapolation divides the measured mean by the number
of links and multiplies by 40. The four-link case gives approximately
0.787 s/update (94.49× slower); the 100-link case gives approximately
0.647 s/update (77.62× slower). At 72,000 updates, that is **12.94–15.75 hours
of rendering work**, reasonably rounded to **13–16 hours**. The earlier
14–16-hour conversation estimate was a rough planning range, not a Ryzen
measurement. "About 100× slower" is an order-of-magnitude description of this
particular CPU extrapolation, not a benchmark or a project-wide result.

This range is not a confidence interval or a guarantee. It assumes similar
per-link CPU costs and serial processing. The CPU renderer handles links
separately; job count, cache behavior, thread choices and the actual host still
matter. Four receiver outputs are not four links: each receives ten transmitters.
No receiver-parallel speedup is credited without measurement. Do not linearly
extrapolate P100's 100-link latency to this small case: its measured 1-/4-link
latencies show substantial fixed/batching costs.

Random flight paths require channel/visibility updates. Those solves, AirSim,
DSP, recording and queues are excluded from the extrapolation. **The complete
flight's wall-clock completion time remains unknown.** A measured advancing
clock run is needed; reserving a day is a scheduling allowance, not a validated
upper bound. Offline simulation must advance every requested epoch and retain
all samples; skipping late frames or dropping I/Q is not equivalent work.

At four receivers and 2 MS/s, ten minutes contains 4.8 billion complex samples:
**38.4 GB as complex64 or 76.8 GB as complex128**, before compression/container
overheads (decimal GB). The earlier conversation's 48-billion/384–768 GB
estimate was ten times too large. On-disk ADC formats can be smaller; conversion
and writing costs still require measurement.

## The original 100-TX/10-RX deployment

The measured P100 row is **100 TX into one RX**, not the whole fleet. A serial
ten-receiver extrapolation on one P100 is approximately **68× slower than real
time**, or **11.33 hours of renderer work per ten simulated minutes**. Ten
identical, independent P100 workers could ideally run those receivers in
parallel at the one-worker **6.80×** rate, about **68 minutes**, if no additional
contention or dispatch costs arose. Neither deployment has been measured.
Ten GPUs do not make an individual receiver's 56.67 ms mean fit into 8.33 ms.

The measured CPU's serial ten-receiver extrapolation is approximately 1,941×
slower, or **323 hours** for ten simulated minutes. Do not apply that number to
the smaller 10-TX/four-RX example. Full service adds other stages in every case.

## What the renderer timer includes and excludes

Included: host validation/packing, private uploads, fresh channel-dependent
delay maps and coefficient/filter construction, path projection, private FFT
filtering, sample reconstruction, coherent receiver summation and synchronized
output download. First-use/JIT and reference calculations are outside timing.

Excluded: waveform generation, physical scene/ray tracing, moving meshes,
receiver noise/filter/ADC, unequal-clock resampling, AirSim physics/Unreal,
transport, queueing and recording. The channels change each capture but are
synthetic arrays; they are not derived from a moving AirSim flight. Current
Sionna RT/Dr.Jit CUDA propagation remains unsupported on the P100; the working
CuPy renderer does not resolve that compatibility issue.

End-to-end **delivery latency** also includes input availability, interpolation
lookahead, queue waits and transport. Renderer service time, achievable output
throughput, simulation update frequency and live delivery latency are different
quantities. A simulation clock configured to 120 Hz does not demonstrate
120 wall-clock updates/s. Event spans from a separate instrumented capture
must not be summed into the unprofiled mean or median.

## Why earlier reports can appear faster

| Earlier result / report | Actual scope | Why it cannot size the current continuous workload |
| --- | --- | --- |
| 7.51 ms radar update, [PERFORMANCE](PERFORMANCE.md) | Eight point targets, direct-only empty scene, one chirp | Small scheduled radar capture; no full environmental multipath or independent continuous streams |
| 162.85 ms / 80 ms frame, [PERFORMANCE](PERFORMANCE.md) | Sixteen-chirp radar frame | About 2.04× renderer/service work per frame interval, not a 120 Hz continuous network result |
| 144 retained paths, [single bounce](OPTIMIZATION.md), [per pulse](PER_PULSE_RUNTIME.md) | Small scene's LoS/specular channel; many links but very few paths | Channel-only timing excludes sample rendering and diffuse ground return |
| 48.6 ms channel, [GPU planning](GPU_RUNTIME.md) | CPU channel/poses/export | No waveform processing; sub-millisecond GPU ray entries elsewhere are hypothetical query-rate arithmetic |
| 243.25 ms service, [batched renderer](BATCHED_RENDERING.md) | Tone inputs, about 42,500 surviving paths total, 4,096 samples per RX | Only 2.048 ms of output, versus the new 8.3335 ms window; scene-dependent survival reduces path work |
| 22× CPU speedup, [basis experiment](DOPPLER_BASIS_FFT.md) | Ratio of two algorithms on one/four-link synthetic jobs | Faster than a baseline does not mean faster than real time; original host differs from the P100 collection |
| 122.67 ms P100, [original run](results/profiling/p100-basis-full-20261004/REPORT.md) | Older gather projection; failed timestamp qualification | Historical diagnostic result; superseded by the qualified 56.17 ms median configuration |
| Legacy Sionna P100 [results](results/profiling/README.md) | Older propagation stack and CPU signal rendering | Separate compatibility experiment, not current CuPy renderer or supported current-stack propagation |

Rays attempted, retained physical paths, filter taps and basis terms are
different counts. A request for 1,028 ray attempts does not guarantee 1,028
valid paths; the latest renderer stress test supplies all of them explicitly.
Short bursts also cannot be compared with continuous output solely by updates/s.
Historical GPU forecasts are sensitivity calculations, not measured capacity.

## Keep the summary reproducible

Run `python3 scripts/update_runtime_docs.py` after selecting a new qualified
collection in that script, or `python3 scripts/update_runtime_docs.py --check`
to verify both published tables against the JSON. Preserve historical reports;
new measurements must state hardware, backend, links, valid paths, sample count,
signal duration, precision, interpolation, delay/Doppler bounds, included work,
accuracy status, warmups and timing distribution. Publish full-service flight
measurements separately from renderer-only results.

## End-to-end RF pipeline tests

See [END_TO_END.md](END_TO_END.md) for the real-terrain scene-to-consumer test,
the direct-renderer integration oracle, and CPU/P100 collection commands.
The default trajectory source exercises the AirSim bridge contract; it does
not execute AirSim physics/RPC. Full distributed continuous-SDR coverage is
still outstanding. New full-pipeline results are distinct from renderer-only
results and do not replace the qualified synthetic stress workload.
