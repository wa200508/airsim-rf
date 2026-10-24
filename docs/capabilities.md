[Documentation](README.md) · [Scenarios](../scenarios/README.md) · [Run dashboard](dashboard.md)

# Capabilities and qualification boundaries

The maintained product is the two-scenario [RF dashboard](dashboard.md).
Implementation, numerical checks, packaged/native checks and real hardware
validation are distinct claims.

| Capability | Implemented / checked | Boundary |
| --- | --- | --- |
| Pull-and-run dashboard | Published simulator/RF/independent-skill images, readiness checks, host UI, cleanup and saved playback | Linux x86-64 / NVIDIA deployment; real GPU readiness is checked on your machine |
| Direction finding | Flying QPSK source, two coherent ULAs, one-way propagation, ADC I/Q and independent MUSIC skill | ULA front/back/elevation ambiguity; reflections can bias the estimator; no measured hardware accuracy |
| Active radar | Skill-commanded TX/RX, 77 GHz FMCW, three fixed RCS targets and first-order terrain echoes | One TX/RX channel, exaggerated target RCS, no target-leg multipath or calibrated CFAR |
| Shared terrain | Same native/RF triangles, independent direct-ray comparisons, LiDAR/native camera checks | Static synthetic terrain; no automatic general-world or moving/deforming-object extraction |
| Low flight | Compiled routes with between-waypoint clearance and grade checks, native spawn/path consistency | Planned clearance is not a full-flight native tracking guarantee |
| Noise and ADC | Configurable modeled noise, explicit demo offset, analog/digital scaling checks and quantization | Uncalibrated front end, no measured ENOB/compression claim |
| Independent skill boundary | Separate repositories/images, real TCP/I/Q journal/replay qualification, active-radio control contract | Physical drivers and a native coherent-array MEL/VITA bridge are not supplied |
| Data and display | Bulk cf32/SigMF, GNU Radio flowgraphs, timestamped camera/telemetry/results and skill-owned displays | Replay contains only saved products; long-run storage/throughput depends on configuration |
| Performance | Recorded CPU RF-window and P100 one-way fleet evidence | Current demo whole-flight latency and 120 Hz operation remain unqualified |

Use [scenario settings](../scenarios/README.md), [clutter assumptions](clutter.md),
[profiling evidence](profiling.md), [boundary contracts](skill-boundary.md) and
[development/CI](development.md) for the supporting details. The
[low-terrain ADC audit](../results/reviews/low-terrain-demo-20261024/REPORT.md)
checks snapshots, not a complete mission or GPU runtime.

The [earlier priority-based acceptance matrix](archive/capabilities-20261020.md)
and [dated reviews](archive/reviews) retain the original qualification decisions;
they do not override the current scenario configuration or measured timing scope.
