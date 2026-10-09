# Qualified P100 optimization results

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


Source: `3985b4f02f4e20e48cd1890d9c493317f5e76efc`, clean build. All eight required collection tasks passed, including 76 CUDA correctness tests and six paired CPU/GPU timing cases. Nsight remains unavailable, so no pure kernel-execution timeline was collected.

The absolute oscillator phase bug is fixed through exact modular arithmetic on the float frequency's rational representation and integer nanoseconds. Split Unix-epoch captures now pass for positive, negative and non-integer frequency offsets. The original failed qualification artifacts remain published.

Selected configuration: warp-cooperative path projection, 100 links per batch, 2,048-sample blocks, original double-sort delay mapping and ordinary FFT. It retains all 102,800 paths per receiver window, FP64/complex128, and temporal tolerance 1e-10. See the [complete optimization comparisons](../p100-basis-optimization-20261004/README.md).

Thirty-window 100-TX GPU median is 56.167 ms, p95 59.645 ms, versus the previously published gather/eight-link 122.671 ms median: approximately 2.18 times faster. Current paired CPU median is 1,610.094 ms, approximately 28.67 times the GPU median. GPU 1-TX and 4-TX medians are 5.508 and 5.676 ms, each with zero of thirty renderer-deadline misses. The 100-TX case misses all thirty deadlines and still needs approximately 6.80 times improvement in mean service time for 120 Hz.

These medians measure complete synchronized synthetic **signal renderer calls**, including host packing, uploads, new channel/filter construction, projection, private FFTs, coherent sum and output download. They exclude propagation/path tracing, startup, reference validation, source generation, receiver noise/filter/ADC, clock resampling, AirSim and network service. They are individual case medians, not a median across the suite. Modern Sionna/DrJit CUDA propagation remains unsupported on P100; previous legacy Sionna propagation results retain their separate scope.

Reference comparisons use the final timed window of each case, including all output samples against CPU basis and all-path direct checks. They do not validate every timed window individually. The 100-TX full-window normalized RMS error is 1.97543e-12. Every case passed its final reference checks.

The separate instrumented 100-TX capture reports projection 17.668 ms and private FFT filtering 15.082 ms, plus host packing/upload 23.729 ms, delay map 5.111 ms, temporal construction 5.514 ms, reconstruction/sum 1.686 ms and export 0.107 ms. These CUDA-event spans include submission and idle gaps. They are from a different capture and must not be summed into or treated as a breakdown of the 56.167 ms median. They show substantial remaining work in projection and filtering; they do not establish a precise percentage attribution.

One-second telemetry reached 83% utilization and 1,401 MiB resident memory. It samples the whole device and may miss peaks; maximum utilization is not sustained arithmetic throughput. Low memory residency does not imply cheap computation. The renderer repeatedly evaluates many FP64 path contributions and independent FFT filters. Adding VRAM allocation alone would not reduce this work.

The tested reduced-sorting and in-place FFT options passed qualification but showed no clear latency benefit. Five tested block sizes favored the existing 2,048 samples. Further investigations can target persistent host/device buffers, measured packing/upload overlap, fused projection/filter operations, and explicit reuse when channels or waveforms remain stable. These require their own qualification and timings; this collection assumes changing channels and private sources each capture.
