# Documentation

Start with a scenario, then use the guides below for the part you want to change.
The two dashboard scenarios are the maintained demonstrations. Other experiments
and benchmark scenes have their own inputs and qualification boundaries.

## Start here

| Page | Answers |
| --- | --- |
| **[Direction finding](../scenarios/drone-orbit/README.md)** | What is the QPSK/drone/array scenario, what does MUSIC show, and where do I edit it? |
| **[FMCW radar](../scenarios/mmwave-radar/README.md)** | What radar, ground targets and waveform are modeled, and what does the range–Doppler map mean? |
| **[Run the dashboard](dashboard.md)** | Pull/run, Python environments, rootless Docker, host display, controls, recordings and cleanup |
| **[Clutter and terrain](clutter.md)** | Ground multipath/backscatter, sampling, occlusion, noise, assumptions and published comparisons |
| **[Profiling and timing](profiling.md)** | Update interval versus wall time, latency, CPU/GPU evidence and stage timing tables |

## Edit or develop

| Task | Page |
| --- | --- |
| Understand ownership and the I/Q boundary | [Architecture](architecture.md) · [README diagram](../README.md#rf-architecture) |
| Find source for antennas, signal, motion or algorithms | [Code map](code-map.md) |
| Copy a scenario or connect a different skill | [Scenario packages](scenarios.md) |
| Tune flight clearance or receiver noise | [Demo tuning](demo-tuning.md) |
| Capture bulk samples and test a skill offline | [I/Q capture/replay](iq-replay.md) · [GNU Radio](gnuradio.md) |
| Add skill-provided plots and metrics | [Skill display contract](skill-display.md) |
| Build images, run checks or contribute | [Development and CI](development.md) · [Build/install reference](setup.md) |

## Detailed reference

These are lookup pages, rather than additional first-run paths.
The [reference folder](reference/README.md) also provides a compact index.

| Topic | References |
| --- | --- |
| Receiver/simulator separation and deployment | [Boundary contract](skill-boundary.md) · [DF skill](direction-finding-skill.md) · [Radar skill and active TX/RX](radar-skill.md) |
| Radar hardware, waveform and source details | [Detailed radar scenario](reference/radar-scenario.md) · [First-order radar equations/implementation](radar-scattering.md) |
| Geometry interchange and scene alignment | [Geometry contract](reference/geometry-contract.md) · [OpenUSD](reference/openusd-workflow.md) · [Unreal import](reference/unreal-geometry.md) |
| Rendering and acquisition interfaces | [Rendering operators](rendering.md) · [APIs](reference/interfaces.md) · [TCP I/Q](reference/iq-stream.md) · [SigMF extension](extensions/airsim_rf.sigmf-ext.md) |
| Timing definitions and raw evidence | [Timing conventions](timing.md) · [Generated measurement catalog](measurements.md) |
| Research and qualification | [Sources and citations](references.md) · [Capability/acceptance matrix](capabilities.md) |
| Extra offline experiments | [Sensing gallery](reference/sensing-plots.md) · [Terrain experiments](reference/terrain.md) · [AoA/tracking](reference/aoa-emitter-tracking.md) |
| Manual acquisition APIs | [Scenario-to-I/Q](reference/scenario-to-iq.md) · [Live recorder](reference/live-workflow.md) |
| Diagnostics | [Troubleshooting](troubleshooting.md) |

## Historical material

[Archive index](archive/README.md) identifies old launch recipes, design studies
and reviews. Dated reports under `results/`, `research_results/` and `docs/archive/reviews/`
retain their original measurements; they are not current demo defaults or a new
real-time qualification. Use the profiling page to put their timing in context.

For a standalone GNU Radio RF skill workspace and metadata-derived acquisition
schedule, see [RF Skill Harness](https://github.com/wa200508/RF-Skill-Harness).
