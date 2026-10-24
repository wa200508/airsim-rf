# Longer moving specular capture — 17 October 2026

> Documentation note: reported measurements are preserved. Local artifacts absent from this repository are shown as file references rather than download links.

**Passed for a controlled 4.8-second flight**, ten times the earlier 0.480-second
captures. Two real ProjectAirSim Runtime drones move apart above flat ground;
RF propagation includes the direct and ground-specular paths. Both flight
commands complete, with no ADC clipping and contiguous recording timestamps.

| Measurement | Result |
| --- | ---: |
| Capture windows | 400 × 12 ms |
| Complex samples at 2 MS/s | 9,600,000 |
| Recorded signal duration | 4.800 s |
| Whole-recording I/Q NRMSE | 0.4489% |
| Boundary I/Q NRMSE | 0.4502% |
| Maximum component error | 0.528 ADC counts |
| TX / RX displacement across snapshots | 14.114 / 14.869 m |
| Paths per window | 2 |

Both I/Q errors pass the unchanged 1% thresholds. Injecting a π phase reset
halfway through readback produces approximately 122.4% whole and boundary error,
and is correctly rejected. The CPU reference shares exported path gains,
delays and Dopplers, then independently sums the CW signal and applies the
continuous receiver filter. This qualifies renderer/filter/ADC integration;
it is not independent physical propagation calibration.

## Changes and validation

The coherent-I/Q analyzer previously retained every reference, observation and
per-sample scale array, then allocated additional full-recording arrays. It now
accumulates error, energy and ADC statistics window by window. It preserves
filter state and the ±128-sample boundary neighborhoods, including their
overlap for short windows. The recording inspector likewise reads and hashes
one window at a time and retains only the last window for the spectral summary.
Channel/recording JSON metadata and the generated source waveform still scale
with capture duration; this change bounds I/Q analysis working arrays.

Focused regression coverage compares streaming statistics with a materialized
reference using unequal, overlapping windows, different ADC scales, a continuous
IIR filter and the injected reset. Inspector checks include byte counts, SHA-256,
code extrema and nonzero fraction. Validation (`validation.log`; local artifact, not checked in): **21 passed,
1 skipped** (optional SigMF package absent in this container). The streaming inspector's entire result exactly matches the
original capture inspection for this 38.4 MB recording.

The capture uses the existing `--duration-ms` extension, which extends both the
flight command and finite source waveform. Motion (`specular/motion.json`; local artifact, not checked in),
I/Q analysis (`specular/diffuse-iq.json`; local artifact, not checked in),
negative control (`specular/diffuse-negative-control.json`; local artifact, not checked in),
inspection (`streaming-inspection.json`; local artifact, not checked in),
manifest (`specular/capture/manifest.json`; local artifact, not checked in), exported channels, trajectories and
generated scene configurations are retained. Raw I/Q remains in ignored
`recordings/longrun-specular-20261017`, identified by the inspection hash.
Source hashes (`source-sha256.json`; local artifact, not checked in) identify the qualification and analysis tools.

## Reproduction and remaining priorities

Start the Runtime as described in the [live guide](../../../docs/reference/live-workflow.md).
Inside the existing P100 environment, with the checkout on `PYTHONPATH`:

```bash
python scripts/basis_launch.py scripts/qualify_live_motion.py --pascal-compat \
  --moving-receiver --velocity -3 --duration-ms 4800 --reflection \
  --output recordings/longrun-specular-new
python scripts/analyze_diffuse_iq.py recordings/longrun-specular-new
python scripts/analyze_diffuse_iq.py recordings/longrun-specular-new --negative-control
python scripts/inspect_live_recording.py recordings/longrun-specular-new/capture
```

The dedicated Runtime container was stopped after capture and its
server log (`server.log`; local artifact, not checked in) retained. GPU execution used `airsim-rf:p100-modern-gpu`
with the explicit Pascal adapter. The recorded service ratio is 6.465 wall
seconds per signal second; this shared-host correctness run is not a throughput
comparison.

Next qualification priorities are longer turning/occlusion captures and
arbitrary Unreal geometry alignment. This result covers straight-flight
specular propagation only; diffuse temporal statistics, hardware calibration,
minute-scale stability and real-time operation remain unqualified.
