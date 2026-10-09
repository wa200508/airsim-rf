# Updated P100 harness validation on the CPU workspace

**Timing scope:** Renderer-call wall service or separately labeled projection/kernel-call experiment; excludes propagation and receiver processing. [Common measurement definitions](../../TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [research_results/p100_basis_harness/cpu_100tx.json](cpu_100tx.json) — Renderer call | unprofiled_basis_benchmark | 2 | 8.333500 | 0.016667 | 5.757116 | 345.420 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->


This validates the collection scripts and full 100-transmitter input budget,
not GPU performance. The implementation is on `profiling/p100`, based on the
merge of `f56914b` with the earlier P100 results at `e8eaf70`.

`cpu_100tx.json` uses 100 private transmitter streams, one receiver, **102,800
valid paths**, 16,667 output samples at 2 MS/s, delay bound 100 microseconds,
Doppler bound +/-2,500 Hz, FP64 and equal sample clocks. One warmup precedes
two timed changing-channel windows. Source hashes identify measured code.
Two windows are a harness smoke test, not qualified latency percentiles.

The all-job initial/final direct checks include every path of every link.
First/last transmitter checks cover all 16,667 output samples. All checks pass.
Median renderer wall latency is approximately 2.879 seconds on this two-core
CPU workspace. There is no CUDA timing in this artifact.

Host and offline nonroot container validation pass **134 tests, with 25 GPU
cases skipped**. The CPU-only collector also passes inside the built container.
Projection and
reconstruction kernels compile for Pascal `compute_60` using the pinned CUDA
12.2 NVRTC library. The profiling image builds with pinned CuPy/runtime/cuFFT
dependencies. Actual CUDA kernel execution remains untested in this workspace;
the P100 preflight/correctness run must verify it before accepting GPU timings.

The CPU-only collector smoke run and a deliberately GPU-blocked collection both
produce reports. The latter exits nonzero and preserves the CUDA blocker, CPU
evidence and failed task status. Instrumented timings are excluded from the
throughput table, and accuracy failures invalidate performance results.
