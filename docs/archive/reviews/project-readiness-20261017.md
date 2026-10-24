# Project readiness and priorities — 17 October 2026

This is a repository-based assessment, not a new benchmark or hardware sizing
result. It incorporates the current uncommitted qualification work.

**20 October 2026: priority 1 is complete for static shared environments with
moving radios.** The [closure evidence](../../../results/reviews/priority1-20261020/REPORT.md)
qualifies nonprimitive shared geometry, independent collision/RF intersections,
turns, obstruction and first-order reflections together, recorded I/Q and a
revision/reload policy. The package remains local; do not publish or deliver it.

**20 October 2026: priority 2 is complete for the qualified local Linux package.**
The [acceptance report](../../../results/reviews/priority2-20261020/REPORT.md)
records a fresh dependency install, local wheel/assets/commands, a clean Docker
build, complete CPU suite, installed-wheel live capture and current user guides.
Nothing was published or delivered.

**20 October 2026: priority 3 is complete for the user-selected Python AoA /
emitter-tracking example.** The [acceptance report](../../../results/reviews/priority3-20261020/REPORT.md)
records independently modulated QPSK through eight propagated ADC channels,
external MUSIC and FilterPy, fixed held-out bearing/track metrics, isolated
installed-wheel CPU replay and replacement guidance. The [ready-made guide](../../reference/aoa-emitter-tracking.md)
links the official SDR University Challenge/MUSIC/tracking examples. Motion here
is a supplied RF trajectory, not live physics; the retained specular stress
fails the same bearing gate. No general multipath/hardware-accuracy claim.

## Destination

The [recorded user target](../planning.md#affordable-realtime-rf) is
approximately $5,000 total compute, 100 independent transmitters, 10 receivers,
continuous ESM/comms I/Q at 2 MS/s per radio, moving platforms, first-order
environmental multipath, and 120 Hz scene/channel updates. Preserve valid paths,
fractional delays, individual Doppler, coherent sums and continuous samples.
Do not assume favorable channels, share transmitter buffers/transforms across
independent jobs, or assume linear multi-GPU scaling to justify capacity.

The project has a working experimental pipeline with substantial numerical and
integration evidence. It has not demonstrated this deployment target.

## What is established

- Sampled-waveform rendering, propagation, receiver DSP and recording exist.
  The [full pipeline benchmark](../../performance.md) includes 100 × 10 operation
  on a P100, with private transmitter data. It uses supplied trajectories;
  live simulator physics/RPC are excluded.
- The P100 is accessible through the qualified Docker environment. Host-only
  GPU detection has been misleading in this environment.
- [Shared-geometry captures](../../../results/reviews/priority1-20261020/REPORT.md)
  now qualify nonprimitive matching collision/RF meshes and combined turning,
  obstruction and first-order reflection at 2 MS/s with 12 ms updates. Earlier
  [longer Runtime captures](../../../results/reviews/longrun-turns-20261017/REPORT.md)
  retain 9.6-second direct-turn and separate 4.8-second screen evidence. None is
  a 120 Hz fleet demonstration or a calibrated general-world result.
- [Local package acceptance](../../../results/reviews/priority2-20261020/REPORT.md)
  includes a fresh dependency install and Docker build, installed-wheel CLI/assets,
  253 CPU passes (158 hardware skips), three focused GPU passes, an actual
  installed-wheel recording and independent official SigMF consumption. No
  release/publication or full GPU-suite claim is made.

## Updated priorities — user direction, 18 October 2026

This order supersedes the earlier feasibility-first recommendation. Broad
capability and usability come first; performance is the lowest priority.

| Priority | Work | Estimated remaining effort | Completion criteria |
| --- | --- | --- | --- |
| 1 — ✓ complete | Match simulator and RF geometry | Closed 20 October; [evidence](../../../results/reviews/priority1-20261020/REPORT.md) | Shared scene geometry, explicit coordinates/transforms/materials and revision tracking; independent intersection checks; moving turns, obstruction and first-order reflections in matching scenes. Define how object changes update RF geometry. |
| 2 — ✓ complete | Consolidate into a usable package — do not deliver | Closed 20 October; [evidence](../../../results/reviews/priority2-20261020/REPORT.md) | Coherent local package with reproducible setup, preflight guidance, complete example assets and configurations, documented interfaces, actionable errors, troubleshooting, expected outputs and a current capability/acceptance matrix. Preserve pending changes and evidence; reconcile stale documentation. Do not publish, release or deliver. |
| 3 — ✓ complete | Demonstrate useful downstream results | Closed 20 October; [evidence](../../../results/reviews/priority3-20261020/REPORT.md) | User-selected Python AoA and emitter tracking: independent modulated QPSK through an actual external MUSIC/FilterPy consumer, fixed bearing/position/velocity and coverage metrics, negative controls, isolated installed-wheel replay and waveform/algorithm replacement guidance. Qualified calibrated single-emitter 2D LOS case; coherent multipath stress fails. No distributed continuous SDR-plane claim. |
| 4 | Make sustained operation dependable | 16–32 active hours, plus long-run execution time | Bounded source access and hashing, efficient metadata persistence, atomic checkpoints and explicit recovery/backpressure behavior. Progress through proposed one-minute and ten-minute captures, including consumer stalls and interruptions; preserve private transmitter storage semantics. |
| 5 | Establish independent physical accuracy | 24–60 active hours for independent numerical validation; hardware validation separately estimated at 2–6+ elapsed weeks | Independent amplitude, delay, Doppler, antenna and cadence checks with error budgets; diffuse convergence and temporal validity where needed. Hardware calibration before claims of measured-radio equivalence. |
| 6 | Performance | 16–40 active hours for profiling and an initial optimization/feasibility pass; full target completion not yet estimable | Once broad capability and usability are in order, profile the full pipeline and measure hardware/partitioning options against the original target without relaxing fidelity or private-input requirements. |

Packaging is a substantial product milestone. Existing correctness checks and
honest model limitations remain necessary throughout the earlier stages.
Performance figures below are retained as context, not immediate assignments.

## Estimate assumptions and uncertainty — 19 October 2026

**Usage-aware scheduling supersedes these hours as a calendar forecast.** See the
[project-specific token budget plan](token-budget-plan-20261019.md), based on
actual GPT-6 Astra Medium session counters and concrete work batches. The hour
ranges below are retained as the earlier uncalibrated estimates, not model-runtime
or token forecasts.

These are rough **remaining-effort planning estimates**, based on the current
repository and saved evidence, not measured task durations or completion promises.
Active hours mean focused implementation, analysis, documentation and attended
qualification by one agent. They exclude the current pause, resource queues,
unattended runs, downloads/build waits and procurement. A working day means about
eight active hours. The ranges assume the preceding priorities have established
their interfaces and examples, so shared work is not counted repeatedly.

**Historical estimate:** execution was paused when these estimates were saved.
The user resumed priority 1 on 20 October; its closure is recorded above.

| Priority | What the estimate covers | Main uncertainty / reason it could take longer |
| --- | --- | --- |
| 1 — Geometry, complete | The client mesh API worked without a rebuild. Nonprimitive collision/RF agreement, moving/turning capture, instance/reflection regressions and revision/reload behavior now pass. | Scope is static shared environments in the pinned stack. Continuous moving/deforming obstacles and arbitrary existing-world extraction remain separate capabilities. |
| 2 — Usable local package, complete | Complete bundled ground/shared examples, installed CLI/preflight/consumers, configuration/API docs, troubleshooting/capability matrix, clean install/container validation and real installed-wheel capture now pass. No publication or delivery. | Scope remains the qualified Python 3.12/Linux/Docker workflow. Broader platforms, an installer UI and release distribution were not part of this milestone. |
| 3 — Downstream results, complete | Python MUSIC/FilterPy AoA and emitter tracking from propagated QPSK ADC recordings, independent installed-wheel CPU replay, fixed held-out metrics/negative controls and complete replacement guide. | Ideal synchronized/calibrated single-emitter 2D LOS supplied trajectory. The retained specular stress fails the unchanged bearing gate; arbitrary multipath, live moving-array geometry and calibrated hardware accuracy remain outside this milestone. |
| 4 — Sustained operation | Bound source access/hashing, improve metadata persistence, add atomic checkpoints and defined recovery/backpressure, then qualify one-minute and ten-minute captures with interruption and consumer-stall cases. | Full-pipeline speed and storage can dominate elapsed time. The historical 44.7 wall-seconds/signal-second figure would make one ten-minute run about 7.5 hours, if applicable; it is not a forecast for the eventual qualification configuration. Repeats and fault cases add runtime. |
| 5 — Independent accuracy | Establish independent analytical/numerical references and error budgets for amplitude, delay, Doppler, antenna response and cadence; assess relevant diffuse convergence/temporal behavior. | Independent reference quality and model discrepancies. The 24–60 hours covers numerical evidence only. Measured-radio equivalence additionally needs calibrated hardware, a controlled setup, measured materials/antennas and repeatable data. The 2–6+ week hardware allowance is provisional and assumes equipment/lab access; without access, no reliable completion date exists. |
| 6 — Performance | Profile the assembled pipeline, identify bottlenecks, implement/measure initial improvements and assess hardware/partitioning feasibility without relaxing fidelity. | Achieving the original approximately $5,000, 100-TX/10-RX, 2-MS/s, 120-Hz target remains unproven. The initial-pass estimate is not an estimate to achieve that target. Results may require architectural changes or show that the target needs revision; do not promise closure on a fixed schedule yet. |

Re-estimate after the client-mesh probe for priority 1, after a clean setup for
priority 2, after the first consumer result for priority 3, and after the first
one-minute run for priority 4. Select the independent physical references before
committing a schedule for priority 5; use the full-pipeline profile to estimate
priority 6. Do not add these ranges into a firm delivery date: qualification
runtime and the two research-heavy milestones are not yet bounded.

## Confirmed audience and packaging requirements

The user explicitly confirmed **RF/SDR engineers and algorithm developers** as
the primary audience. Assume RF expertise, but not familiarity with this
repository, Unreal, Sionna or its container setup. The package should let them:

1. Install and check prerequisites through one clear starting workflow.
2. Configure matching scene geometry, platforms, radios and RF materials.
3. Supply independent sampled waveforms and select receiver settings.
4. Run a complete example with documented expected outputs and limitations.
5. Consume I/Q and ground truth through documented formats/APIs and integrate
   their own comms/ESM algorithms without modifying simulator internals.
6. Diagnose configuration and runtime failures with actionable guidance.

Examples must bundle their required assets, configurations and waveform
creation steps. Document units, coordinate systems, timestamps, sample formats,
amplitude conventions, model scope and extension points. A new user should not
need to reconstruct the workflow from historical research reports. A particular
UI technology or graphical interface has not been requested or selected.

## Retained technical context for later work

The current 100 × 10 pipeline averages **372.320 ms per update**, or **44.678
wall seconds per signal second**, versus an 8.333 ms budget at 120 Hz. Closing
that gap requires about a 44.7-fold throughput improvement relative to this
measured configuration. That is not a prediction for another GPU or a claim
that every component scales equally. Live simulator costs would add work.
The benchmark covers only 0.250 simulated seconds per receiver.

The recent persistent-buffer experiment found approximately a 2.5% renderer
improvement under its matched controls. Persistent buffer reuse is already
available in the production receiver, so this is not another unclaimed
full-pipeline speedup. Stable-channel reuse results are conditional and cannot
be used as the general moving-scene capacity estimate.

Geometry is an independent correctness blocker: a visually plausible simulator
scene does not automatically give the RF solver the same obstacles or materials.
Current coherent I/Q references also share traced gains/delays/Dopplers with
the implementation; their strong error numbers do not independently validate
RF amplitudes or the environment.

Longer operation has concrete implementation limits. In
[live.py](../../../src/airsim_rf/live.py), validation and runtime load whole waveform
arrays, hashing reads whole files, and each recording checkpoint rewrites
growing metadata. The recent analyzers bound their I/Q working arrays, but
metadata and parts of the qualification helper still grow with duration.
At ten receivers and 2 MS/s, raw SC16 output alone is 80 MB/s (48 GB over ten
minutes); cf32 transport is 160 MB/s before protocol overhead. Source data and
private copies are additional costs. Output/storage therefore belong in the
capacity study.

## Next-agent handoff

- **Priorities 1–3 complete in their recorded scopes.** Start priority 4 when directed.
  See the [current quickstart](../../quickstart.md), [capability matrix](../../capabilities.md)
  and [local package acceptance](../../../results/reviews/priority2-20261020/REPORT.md).
  The local CPU image is `airsim-rf:priority2-local`; the task-owned simulator is
  stopped, unrelated services remain running, and nothing has been published.

- **Priority 1 completed on 20 October.** See the
  [closure report](../../../results/reviews/priority1-20261020/REPORT.md) and
  [current workflow](../../reference/openusd-workflow.md). The previous pause/resume note is historical.
- The qualified source route is OpenUSD shared triangles → generated GLB for
  Blocks collision and PLY/XML for RF, with full hashes and explicit RF materials.
  Combined turns, obstruction and ground reflection pass through the complete
  recorder. Object changes require a new bundle, world placement, RF scene and
  receiver at a recording boundary. Continuous dynamic obstacles, arbitrary
  existing-world extraction, camera rendering and calibrated materials are outside
  the qualified scope. The priority order and original fleet target remain intact.
- Standards remain as selected in the [ASE/Open Arsenal review](ase-standards-selection-20261018.md):
  RF MEL, OMS/UCI/CAL and DIS at ecosystem boundaries; OpenUSD for scene assets.
  No new RF standards-profile endpoint exists yet.
- Continue with priorities 4–6 in the order above. The consolidated package
  remains local, without delivery/publication/release. Audience: RF/SDR engineers
  and algorithm developers.
- On 19 October the user authorized GPU use and explicitly authorized
  qualification checks, superseding the earlier no-test/no-GPU restriction.
  Do not interrupt unrelated GPU processes or containers.
- Preserve existing uncommitted changes and evidence. Recent work covers
  qualification tools, live-workflow documentation and reports under
  `results/reviews/longrun-20261017/`,
  `results/reviews/longrun-turns-20261017/` and
  `results/profiling/p100-basis-persistent-20261004/`.
- The original fleet/sample-rate/budget target remains recorded for later
  performance work; it must not displace the user's current emphasis on broad
  capability and usability.
- This document records the confirmed audience, current priorities, packaging
  expectations and operational constraints. The earlier feasibility-first
  recommendation in chat is superseded.

## Supporting references

- [Architecture and model boundaries](../../architecture.md)
- [Scenario-to-I/Q workflow](../../reference/scenario-to-iq.md)
- [Unreal geometry qualification](../../reference/unreal-geometry.md)
- [Streaming protocol and failure semantics](../../reference/iq-stream.md)
- [Rendering accuracy and diffuse-model limitations](../../rendering.md)
- [Setup and qualified environments](../../setup.md)
- [Development and CI](../../development.md)
- [Recent performance experiment](../../../results/profiling/p100-basis-persistent-20261004/REPORT.md)
