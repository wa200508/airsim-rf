> **Historical acceptance matrix.** This records the earlier priority-based qualification; use the [current capability summary](../capabilities.md) for the dashboard.

[Documentation](../README.md) · [Scenarios](../../scenarios/README.md) · [Run dashboard](../dashboard.md)

# Current capabilities and acceptance matrix

Primary users are RF/SDR engineers and algorithm developers. The local package
supports controlled numerical and simulator workflows. It is experimental and
has not demonstrated the original affordable real-time fleet target. Use this
matrix to distinguish an implemented interface from qualified behavior.

| Capability | Current supported/qualified scope | Evidence or next acceptance step |
| --- | --- | --- |
| Install and start locally | Python 3.12/Linux x86-64; pinned source/dependency bootstrap, local wheel, bundled examples, offline plan/inspection/processing commands. No package delivery/publication. | [Priority 2 acceptance](../../results/reviews/priority2-20261020/REPORT.md); fresh dependency environment and wheel imported from site-packages outside the checkout. |
| Shared simulator/RF geometry | Static file-backed USD triangles, explicit units/transforms/RF materials, native instances and reflected winding. Generated GLB collision meshes and RF PLY/XML share one source in pinned Blocks 1.0.1. | [Priority 1 closure](../../results/reviews/priority1-20261020/REPORT.md): independent Unreal/CPU/GPU rays, turns, obstruction and first-order reflection together, recorded geometry identity. |
| Geometry changes | Pose/scale guards at both interval endpoints; a changed static actor rejects capture before sample generation. New revision/bundle/placement/scene/receiver at a recording boundary. | [Revision policy](../reference/openusd-workflow.md#geometry-changes-and-cache-lifetime). No continuous moving/deforming obstacle updates, transient-motion detection or arbitrary existing-world extraction. |
| Live recording | Dedicated real ProjectAirSim world, single stepping owner, actual elapsed-time samples, nominal clocks, private TX sources, continuous receiver/filter state, per-receiver signed ADC I/Q and provenance. | [Live workflow](../reference/live-workflow.md); pinned P100 GPU stack. Fresh configuration preflight occurs before world mutation. Other hardware/versions need qualification. |
| Radio motion | Controlled real Fast Physics straight and turning flights, two moving radios, body-mounted aperture offsets and attitude-dependent antenna gains. | [Geometry closure](../../results/reviews/priority1-20261020/REPORT.md), [directional check](../../results/reviews/directional-turns-20261015/REPORT.md). Starter package example is stationary; flight commands require an application stepping owner. |
| Propagation | Direct visibility, first-order specular reflection; explicit experimental angular or fixed-surface diffuse modes. Per-path gain/delay/Doppler and coherent sums retained. | [Rendering limits](../rendering.md), [diffuse audit](../../results/reviews/diffuse-stability-20261012/REPORT.md). No higher-order paths, calibrated roughness, general temporal-speckle validity or general terrain qualification. |
| Waveforms and receiver | Independent finite complex sampled TX arrays, declared occupied bandwidth/TX watts, interpolation and zero boundaries; configurable filtering, thermal noise and signed 12-bit ADC model. | [Interfaces](../reference/interfaces.md). Files are not looped/normalized; model parameters are not measured hardware calibration. |
| Saved I/Q interoperability | Windowed complex-volts/raw-code reader and official SigMF 1.13.0 readback of actual captures. Separate analysis can use NumPy/SigMF only. | [SigMF evidence](../../results/reviews/sigmf-interop-20261015/REPORT.md), [geometry closure audit](../../results/reviews/priority1-20261020/closure.json). |
| In-process / external consumers | Synchronous per-receiver callback and experimental framed TCP transport with completion/error semantics. | [TCP protocol](../reference/iq-stream.md). No real-time delivery guarantee, hardware driver or distributed continuous SDR plane. |
| Useful downstream algorithm result | Independent QPSK → eight individually propagated ADC channels → external Python MUSIC → two-bearing fusion → FilterPy emitter track. CPU-only installed-wheel replay with no emitter truth/source waveform mounted. | **Priority 3 complete** for this single-emitter calibrated 2D LOS case: [ready-made example](../reference/aoa-emitter-tracking.md), [acceptance](../../results/reviews/priority3-20261020/REPORT.md). Supplied RF motion, not live physics. Retained specular stress fails the unchanged bearing gate; no multipath-robust/hardware-accuracy or BER claim. |
| Sustained operation | Short controlled captures including a 9.6 s direct-path turn and 4.8 s screen case; I/Q analyzers use window-sized sample arrays. | **Priority 4 pending:** whole waveform loading/hashing and growing metadata remain; one/ten-minute operation, atomic recovery and consumer-fault qualification are open. |
| Independent physical accuracy | Analytical geometric/delay/Doppler checks and numerical renderer references in controlled cases. | **Priority 5 pending:** independent amplitude/material/antenna error budgets, diffuse convergence and calibrated hardware evidence. Shared traced-path references do not establish those. |
| Performance | Measured full 100×10 trajectory workload at 2 MS/s on one P100; slower than real time. | **Priority 6 pending:** [performance record](../performance.md). No demonstrated approximately $5,000, 120 Hz, live 100-TX/10-RX deployment. |
| Standards and radar workers | Existing AMS-GRA radar RPC workers and documented ecosystem selections; continuous SDR is a separate API. | [Architecture](../architecture.md), [standards selection](reviews/ase-standards-selection-20261018.md). No certification or newly implemented RF MEL/OMS/DIS profile endpoint. |

The qualified CPU lock uses Sionna RT 2.2.0, Mitsuba 3.9.1 and Dr.Jit 1.5.0.
The P100 exception uses Mitsuba 3.8.0 and Dr.Jit 1.3.1 with explicit compatibility
guards and CUDA wheel-library setup. OpenUSD 26.8 is qualified. Declared broader
package ranges do not constitute a tested environment matrix. Linux/Docker is
the supported local workflow; Windows/macOS setup and other GPUs are not
qualified by these reports.
