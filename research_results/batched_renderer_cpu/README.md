# Batched renderer CPU measurements

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
