# P100 GPU propagation and pipeline optimization experiments

**Timing scope:** RF fleet-update wall service; serial receivers; trajectory source and loopback consumer. [Common measurement definitions](../../../TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [results/profiling/p100-gpu-system-20261007/comparison/baseline_cuda/measurements.json](comparison/baseline_cuda/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 14.166577 | 170.000 |
| [results/profiling/p100-gpu-system-20261007/comparison/baseline_cuda_repeat/measurements.json](comparison/baseline_cuda_repeat/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 7.091646 | 85.100 |
| [results/profiling/p100-gpu-system-20261007/comparison/fused_cuda/measurements.json](comparison/fused_cuda/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 5.575912 | 66.911 |
| [results/profiling/p100-gpu-system-20261007/comparison/persistent_cuda/measurements.json](comparison/persistent_cuda/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 5.660356 | 67.925 |
| [results/profiling/p100-gpu-system-20261007/comparison_shapes/baseline_cuda/measurements.json](comparison_shapes/baseline_cuda/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 13.972078 | 167.666 |
| [results/profiling/p100-gpu-system-20261007/comparison_shapes/baseline_cuda_repeat/measurements.json](comparison_shapes/baseline_cuda_repeat/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 6.972281 | 83.668 |
| [results/profiling/p100-gpu-system-20261007/comparison_shapes/fused_cuda/measurements.json](comparison_shapes/fused_cuda/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 5.610920 | 67.331 |
| [results/profiling/p100-gpu-system-20261007/comparison_shapes/persistent_cuda/measurements.json](comparison_shapes/persistent_cuda/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 10 | 8.333300 | 0.083333 | 5.622231 | 67.467 |
| [results/profiling/p100-gpu-system-20261007/gpu_pipeline_smoke/measurements.json](gpu_pipeline_smoke/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 2 | 8.333500 | 0.016667 | 0.126940 | 7.616 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->


This collection establishes P100 CUDA/OptiX propagation for the current Sionna RT 2.2.0 first-order model, alongside CuPy FP64/complex128 signal rendering. It does not substitute the legacy Sionna 0.19 model.

Compatibility environment: Mitsuba 3.8.0 / Dr.Jit 1.3.1 / CuPy 13.6 / CUDA 12.2 wheels, on Tesla P100 SM 6.0. The modern pinned Mitsuba 3.9.1 / Dr.Jit 1.5 rejects this device. The older stack accepts CUDA ray intersections but its native scatter-increment emits a Volta-only warp-match instruction. The explicit compatibility layer replaces this uint32 path counter with a zero-copy CUDA atomic operation, disables unsupported local scatter reduction, and handles the absent Metal enum check. No ray, field or path budget is dropped. GPU tensor capacity is padded to powers of two; negative-delay storage padding remains distinct from physical paths.

Optimization controls preserve every path, 1,028 diffuse attempts per link, private source copies and transforms, 2 MS/s, continuous sample accounting, FP64/complex128 rendering, declared 100 us / 2,500 Hz bounds and 1e-10 temporal tolerance. Persistent per-receiver pinned/device workspaces use modest capacity padding, host sampling draws are reused only for identical evaluated probabilities/counts/seed, and changing GPU poses are made opaque rather than reused. Fused projection remains an explicit experimental option; its small measured gain was insufficient to replace the default.

Qualification: the modern-stack renderer/physics suite passed 135 tests; the explicit older GPU stack passed 12 scattering/moving-scene tests, 29 pipeline/reporting/counter tests, and 7 worker-protocol tests in an isolated LLVM process. The final opaque-pose/storage suite passed 27 scattering, moving-scene, receiver and counter tests. Earlier logs preserve provisional compatibility failures, a path-order-sensitive assertion, an indentation error and mixed-backend worker fixture failures; they are diagnostic history, not final qualification outcomes. Worker tests must run separately because switching global Mitsuba variants after Sionna initialization mixes cached CUDA/LLVM types. No new CPU-only end-to-end performance series was collected.

Ten-window comparisons use 100 TX / 10 RX, fresh continuous sources and changing poses, three warmups, one P100, and serial receiver execution:

| Comparison after GPU storage change | Fleet-update wall median ms | Propagation ms | Rendering ms |
|---|---:|---:|---:|
| First baseline process / cache | 1397.35 | 851.54 | 427.34 |
| Persistent inputs + sampling reuse | 562.27 | 47.92 | 395.37 |
| Plus fused projection | 560.41 | 46.93 | 394.60 |
| Repeated baseline with disk-cache reuse | 699.20 | 155.63 | 422.86 |

Baseline cache effects are large. The first baseline cannot be used as an uncontested optimization speedup denominator. The repeat is a new process with warmed shared Dr.Jit disk cache for the same epochs. After these comparisons, opaque pose inputs removed recurring compilation on previously unseen trajectories in a separate full collection. See the [final 30-window GPU pipeline results](../p100-gpu-pipeline-opaque-full-20261007/FINDINGS.md).

`comparison` records the earlier controls, `comparison_shapes` records GPU storage controls, and their manifests identify exact code revisions and commands. The smoke run precedes final source provenance; do not use it as the qualified performance result. Ollama was paused with explicit user permission for timing and restored afterward. Other GPU-resident services remained idle. Raw SC16 captures stay local and ignored.
