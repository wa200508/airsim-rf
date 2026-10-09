# Intermediate GPU propagation collection

**Timing scope:** RF fleet-update wall service; serial receivers; trajectory source and loopback consumer. [Common measurement definitions](../../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
This complete collection runs propagation and rendering on CUDA with the explicit older stack, before making moving pose values opaque. Its 100-TX/10-RX unprofiled median is 1,259.17 ms; the repeated instrumented series is about 575.80 ms. That difference exposed repeated compilation for new trajectory epochs. The original `optix_events` counter incorrectly checked only event type; Dr.Jit 1.3 indicates OptiX with `uses_optix`, so zero in this intermediate file does not establish CPU traversal. The corrected final collection records four OptiX events per target window.

Use the [final opaque-pose collection](../p100-gpu-pipeline-opaque-full-20261007/FINDINGS.md) for the qualified optimized results. These intermediate artifacts retain the actual measurements and source revision without overwriting them.

Measurement units and scope: [timing definitions](../../../docs/timing.md); [wall cost per simulated signal second](../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
