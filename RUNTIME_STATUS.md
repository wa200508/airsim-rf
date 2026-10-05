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
