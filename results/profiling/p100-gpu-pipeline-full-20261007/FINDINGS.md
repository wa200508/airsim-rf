# Intermediate GPU propagation collection

**Timing scope:** RF fleet-update wall service; serial receivers; trajectory source and loopback consumer. [Common measurement definitions](../../../TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-instrumented/measurements.json](profiles/cuda-100tx-10rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 17.325668 | 69.303 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-100tx-10rx-unprofiled/measurements.json](profiles/cuda-100tx-10rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 37.925993 | 151.704 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-instrumented/measurements.json](profiles/cuda-10tx-4rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 1.961967 | 7.848 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-10tx-4rx-unprofiled/measurements.json](profiles/cuda-10tx-4rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 4.343547 | 17.374 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-instrumented/measurements.json](profiles/cuda-2tx-2rx-instrumented/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 30 | 8.333333 | 0.250000 | 0.841250 | 3.365 |
| [results/profiling/p100-gpu-pipeline-full-20261007/profiles/cuda-2tx-2rx-unprofiled/measurements.json](profiles/cuda-2tx-2rx-unprofiled/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 1.336400 | 5.346 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->


This complete collection runs propagation and rendering on CUDA with the explicit older stack, before making moving pose values opaque. Its 100-TX/10-RX unprofiled median is 1,259.17 ms; the repeated instrumented series is about 575.80 ms. That difference exposed repeated compilation for new trajectory epochs. The original `optix_events` counter incorrectly checked only event type; Dr.Jit 1.3 indicates OptiX with `uses_optix`, so zero in this intermediate file does not establish CPU traversal. The corrected final collection records four OptiX events per target window.

Use the [final opaque-pose collection](../p100-gpu-pipeline-opaque-full-20261007/FINDINGS.md) for the qualified optimized results. These intermediate artifacts retain the actual measurements and source revision without overwriting them.
