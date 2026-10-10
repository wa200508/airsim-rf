# Quality remediation — 9 October 2026

This implements the [quality assessment](project-quality-assessment-20261009.md).
The original assessment remains a dated record. Current guides and gallery have
been revised; historical scientific results have not been retroactively changed.

| Finding | Delivered change |
| --- | --- |
| Q01: physical timing fixtures | Immutable original low-relief XML/mesh, scene hashes and whole-interval conservative clearance bounds for scattering/SDR/fleet timing. Support analysis and GPU preflight use the same versioned scene. Raised sensing terrain remains separate. |
| Q02: stale received powers | Corrected claims; current guide uses a source-derived capture table, checked by CI. Added per-link power/visibility history. |
| Q03: hidden undefined controls | Explicit zero-code and undefined status, nonzero-code panels, spectrum annotations, and NaN classification checks; no artificial measurements. |
| Q04: duplicate bibliography IDs | Separate IQ and environmental citation namespaces; inbound citations updated and unique-ID/fragment checks added. |
| Q05: mixed historical/current guidance | Short current setup, architecture and rendering guides; dated research/recipes preserved under archive. |
| Q06: incomplete live recipe | Generated waveform, matching plane/two-radio scene, dependency extra, file/provenance validation and inspector. Built actual pinned Runtime server and passed P100 recording smoke. |
| Q07: obsolete active generation | Archived overview is opt-in; separated-capture waterfall generation removed. Channel heatmaps are opt-in, explicitly named snapshot diagnostics. Current gallery is canonical. |
| Q08: hidden clock correction | Common absolute frequency axis, distinct styles, readable delay ticks, explicit peak normalization and oracle context. |
| Q09: unclear physical causes | Terrain-aware 3D ordering, recorded altitude/ground profiles, actual blocked-link section and received-power/visibility history. Status cross no longer implies an intersection location. |
| Q10: hardware-neutral interpretation | Scientific captions/manifests describe recorded RF geometry/data; relevant backend details remain in execution provenance and performance/setup. No bitwise hardware-equivalence claim. |
| Q11: insufficient checks | Files/fragments/unique IDs, both figure generators, source hashes, PNG/SVG presence, classified nonfinite values, zero-code consistency and source-derived scalar summary checks. |
| Q12: reading path | Goal-based README and 330 combined lines across the three main maintained guides, with a capability matrix, clock glossary and linked history. |

Additional requested figure improvements include a signed radar height-error
trace, worst-case route marker, explicit waterfall epoch/carrier context,
per-site normalization interpretation, and the nonunique/epoch-zero scope of
conditional geolocation loci. No unsupported ROC, range–Doppler or localization
accuracy claim was added.

## Real-server qualification and discovered source bug

A source-built ProjectAirSim Runtime container provided the actual server APIs.
Its direct `pose`/`twist` RPC response exposed a wrapper assumption in the RF
adapters that offline mocks had missed. The central normalization now accepts
the pinned direct response and the older wrapped shape. SDR/radar/distributed
consumers share it; both distributed shapes have regression coverage.

The [real server report](../../results/reviews/project-quality-20261009/live-server/REPORT.md)
records ten continuous windows, 240,000 complex samples, 0.120 signal seconds,
valid ADC range and the expected +150 kHz spectral peak. This is a stationary,
non-physics, flat-ground smoke test with first-use included in service time;
moving-vehicle physics and Unreal mesh alignment remain future qualification.
The task-created server was stopped afterward. Existing services were untouched.

## Validation and practical limits

- Standard dependency suite: **185 passed, 157 skipped**. CUDA cases skipped here are addressed by the separate device suite; they are not counted as CPU passes.
- Explicit P100 compatibility suite: **150 passed**; final device log is linked below. It covers renderer qualification, real-scene direct/basis comparisons, compatibility semantics and live contracts.
- Live-only offline suite: **8 passed**, including rejection of a timestamp discontinuity.
- Current gallery hashes, asset presence, undefined metrics and scalar summaries pass their checks; timing/runtime/stage tables remain consistent with recorded JSON.
- A [three-update P100 pipeline smoke](../../results/reviews/project-quality-20261009/pipeline-smoke/REPORT.md) exercises the restored timing scene and publishes its provenance. It is screening evidence, not a new sustained-performance headline.

[Validation logs](../../results/reviews/project-quality-20261009/validation) include
the initial diagnostic run of CPU tests on the older Pascal dependency stack
without its explicit compatibility adapter: 177 passed, 157 skipped, five native
sampler failures due to the absent Dr.Jit Metal enum. The standard stack and the
explicitly enabled P100 path are qualified separately. That failed invocation is
not presented as successful CPU compatibility for the older stack.

Raw live I/Q and generated inputs remain in ignored recordings paths; manifests,
hashes, small JSON and logs are published. Large plotting assets are regenerated
from the committed recordings. Further improvements should build on representative
workloads and measured live behavior rather than additional tuning of this one
terrain or reinterpreting renderer-only timings as full-system throughput.
