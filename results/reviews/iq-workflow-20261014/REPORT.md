# Scenario-to-I/Q integration qualification — 14 October 2026

All four explicit propagation modes passed a real ProjectAirSim Runtime → GPU
SDR capture → synchronous user callback → saved recording → CPU reader round
trip. The standalone reader example also ran without GPU access. This qualifies
stationary workflow interoperability, not moving diffuse coherence or physical
RF calibration.

## Scenario and procedure

The generated starter has two stationary non-physics robots, mapped to RF
positions (−20, 0, 20) and (20, 0, 20) m above synthetic flat ground. The source
is a finite unit-power +150 kHz complex tone at 2 MS/s; the RF carrier is 915 MHz.
Each mode uses its own generated inputs and three requested 10 ms advances.
Actual 3 ms physics ticks produce three 12 ms windows: **0.036 simulated signal
seconds and 72,000 complex samples per receiver** in each run.

| Mode | Retained paths per window | Callback/readback |
| --- | ---: | --- |
| direct | 1 | Passed, all three windows |
| specular | 2 | Passed, all three windows |
| diffuse-angular | 369 | Passed, all three windows |
| diffuse-surface | 4,098 | Passed, all three windows |

Surface mode uses 4,096 attempted diffuse samples; the other modes use a 1,028
sample setting. Every callback epoch matches its recorded block. Reconstructed
post-ADC complex volts match callback samples within `rtol=2e-7, atol=1e-12`.
These are serialization/scaling checks, not independent propagation truth.

The literal `examples/process_live.py` command also completed ten windows,
**240,000 complex samples spanning 0.120 simulated signal seconds**, printing
per-window epoch, sample count, rate and RMS complex volts. The literal
`examples/process_recording.py` command read the surface-mode recording on CPU.
Regression tests passed: **205 passed, 157 skipped**. Skips do not establish
coverage of optional GPU, simulator or other unavailable test dependencies;
the real four-mode qualification above is separate evidence. Added offline tests
cover independent receiver scales, callback failure, metadata mismatch and
truncated-file rejection.

## Reproduce

Start the Runtime container using [the live setup](../../../docs/reference/live-workflow.md#complete-two-radio-first-run),
then use the installed CUDA Python environment:

```bash
python scripts/qualify_iq_workflow.py --output recordings/iq-workflow-new
python examples/process_live.py \
  --config recordings/iq-workflow-new/specular-inputs/radios.json \
  --output recordings/iq-example-new
python examples/process_recording.py recordings/iq-workflow-new/diffuse-surface
```

This run used the P100-compatible `airsim-rf:p100-modern-gpu` image, the
`scripts/basis_launch.py` launcher and `--pascal-compat` for the first two
commands. The reader used the CPU `airsim-rf:p100-profile` image without GPU
access. Runtime source was pinned to
`cfb865f29f255b15ef28ec8fdcfaa01a6b66497f`; see the container build recipe.
Implementation under test: `76d8a72`, plus the subsequently committed live example
and two reader regression tests. The task Runtime container was stopped after
qualification; unrelated host services were left alone.

## Evidence and boundaries

- [Workflow results](workflow.json), [client log](client.log), [server log](server.log).
- [Regression log](standard-tests.log), [live example output](live-example.log),
  [live example manifest](live-example-manifest.json), [CPU reader output](reader-example.json).
- Per-mode directories retain manifests and SigMF metadata; raw I/Q stays in
  ignored local `recordings/`. [Hashes and byte counts](recording-hashes.json)
  identify those data files. Manifest provenance identifies source inputs.

Recorded timing includes physics/RPC, snapshots, RF capture, data/metadata writes
and synchronous callbacks; startup before recording, final checkpoint writes and
fsync are excluded. Ratios are wall seconds per simulated signal second. These
runs are **not comparative throughput measurements**: first-use compilation,
shared process warmup and other host services differ. In particular, the slower
first mode does not show that direct propagation is inherently slower.

The server supplies flat-ground Runtime physics/API behavior, not Unreal world
mesh export. Fixed-surface integration passing here does not qualify moving
coherent diffuse I/Q, occlusion transitions, turn/mount behavior, calibrated
roughness, physical SDR hardware or distributed transport. The callback is
synchronous Python processing while simulation is paused. The reader supports
this project's SigMF layout; external MATLAB/GNU Radio applications were not run.
