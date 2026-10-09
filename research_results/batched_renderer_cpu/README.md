# Batched renderer CPU measurements

**Timing scope:** Renderer-call wall service or separately labeled projection/kernel-call experiment; excludes propagation and receiver processing. [Common measurement definitions](../../TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [research_results/batched_renderer_cpu/batched_128.json](batched_128.json) — Local RF service | unprofiled_benchmark | 10 | 2.048000 | 0.020480 | 2.480152 | 121.101 |
| [research_results/batched_renderer_cpu/batched_32.json](batched_32.json) — Local RF service | unprofiled_benchmark | 10 | 2.048000 | 0.020480 | 2.477535 | 120.973 |
| [research_results/batched_renderer_cpu/batched_events.json](batched_events.json) — Local RF service | instrumented_profile | 3 | 2.048000 | 0.006144 | 0.733953 | 119.458 |
| [research_results/batched_renderer_cpu/per_link_local.json](per_link_local.json) — Local RF service | unprofiled_benchmark | 10 | 2.048000 | 0.020480 | 2.778200 | 135.654 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->


See [the implementation and comparison](../../BATCHED_RENDERING.md).

These measurements were collected on the dirty working tree based on
`413da40f6e20911a08e5a72f9df5e8929b80b33f`, before committing the new renderer.
The recorded implementation hashes identify the measured source. Subsequent
changes added collector reduction flags, report wording, tests and documentation; measured
renderer, receiver and benchmark implementation files were unchanged.

`per_link_local.json`, `batched_32.json` and `batched_128.json` use identical
scene epochs and retained path counts, per-link diagnostics enabled, two
warmups and ten unprofiled captures. `batched_events.json` is a separate
instrumented run and does not enter that comparison. `sampled_input.json` is
a separate one-link, fixed-valid-path renderer-only stress measurement.

Validation after implementation: **120 passed, 22 skipped**, both in the host
venv and in the offline, nonroot profiling container. Skips are CUDA cases:
there is no GPU in this workspace. The container overlaid the final test file
on the freshly built profiling image and used a temporary-memory mount to
avoid this workspace's Docker storage limit. A separate offline container
collector smoke run passed the CPU scene benchmark, event profiling, arbitrary
sampled-input benchmark and report aggregation. It overlaid the final collector
script and used two transmitters, 64 output samples and 16 paths/attempts per
link solely to check the harness; those timings are not performance evidence.

The target 100-transmitter/10-receiver, 2 MS/s, 120 Hz continuous workload
has not been demonstrated. GPU timing has not been measured here.
