# Longer turns and direct-path occlusion — 17 October 2026

> Documentation note: reported measurements are preserved. Local artifacts absent from this repository are shown as file references rather than download links.

The real Runtime/P100 workflow now passes a **9.6-second turning capture** and
a separate **4.8-second straight-flight screen capture**. The turn records
19.2 million complex samples across 800 windows; the screen records 9.6 million
across 400 windows. Both use 2 MS/s and 12 ms channel snapshots, with contiguous
sample timestamps, no ADC clipping and completed TX/RX flight commands.

| Capture | Whole I/Q NRMSE | Combined boundary NRMSE | Additional checks |
| --- | ---: | ---: | --- |
| Initial 4.8-second turn | 0.2518% | 0.2512% | Independent mount position, velocity and direct-path geometry pass |
| Final 9.6-second turn | 0.2861% | 0.2860% | TX/RX heading changes 6.674/4.735 radians; mount/path checks pass |
| 4.8-second screen | 0.1123% | 0.1122% | All 400 analytic visibility checks pass; both individual transition checks pass |

The same 1% I/Q limits are retained. For the final turn, maximum path-length
error is 0.00894 mm; Doppler error against a pose finite difference is 0.00106 Hz.
Maximum mount-velocity error is 0.000387 m/s. The within-window tone estimator
differs from the direct-path prediction by at most 0.01533 Hz. The injected
half-recording π reset produces 118.9% whole/boundary error and is rejected.

## Qualification fixes exposed by the longer cases

The initial 9.6-second turn completed successfully but its qualifier reported
failure: the straight-flight lateral-motion condition required `abs(v_y)>0.1`
in every window. RX's measured lateral velocity ranges from −2.806 to +2.793 m/s
and legitimately crosses zero; twelve windows fell below that threshold.
The independent mount geometry and Doppler checks passed on this same capture.
The original failure (`initial-full-turn/motion.json`; local artifact, not checked in) and client log are retained.

Turning runs now apply the same 0.1 m/s threshold to RMS lateral speed over the
sampled windows. Straight-flight runs retain the original every-window check.
The corrected run reports 2.178 m/s lateral RMS and passes. A regression uses
a full circular velocity trajectory with direction reversals, plus stationary
and isolated-spike negative cases. Independent heading and mount-geometry
qualification remains necessary; RMS lateral activity alone does not prove
correct turning kinematics.

The I/Q analyzer now also evaluates each **path-count transition** separately.
Combining hundreds of boundary neighborhoods can hide a defect at one transition.
New regression data inject a localized error that passes whole-recording and
combined-boundary thresholds but fails this individual check. The implementation
keeps window-sized I/Q arrays; only small per-boundary energy accumulators grow
with the number of windows. A transition with zero reference energy cannot pass
the relative-error check.

In the actual screen capture the path disappears at 0.144 s and returns at
0.360 s, relative to capture start. Individual ±128-sample neighborhoods have
0.2621% and 0.2600% NRMSE, respectively. Receiver filter state is retained through
the empty-channel interval. Visibility and transition timing refer to the
12 ms snapshot cadence. A path replacement that preserves the path count is
not identified as a separate transition by this check.

## Evidence and reproduction

The final turn (`turn-9.6s/`; local artifact, not checked in), shorter turn (`turn-4.8s/`; local artifact, not checked in) and screen (`screen-4.8s/`; local artifact, not checked in)
directories retain motion, channel, trajectory, inspection and analysis JSON,
manifests, SigMF metadata, generated configurations and client logs. Raw I/Q is
retained in ignored `recordings/longrun-*-20261017` directories and identified
by the inspections' SHA-256 hashes. Source before (`source-before.json`; local artifact, not checked in) and
source after (`source-after.json`; local artifact, not checked in) identify qualification changes.

Focused regressions (`validation.log`; local artifact, not checked in): **33 passed, 1 skipped**; the skip is the
optional SigMF package absent from this container. The dedicated Runtime server
was stopped after recording; its log (`server.log`; local artifact, not checked in) is retained. These are
shared-host correctness captures, not comparative throughput measurements.

Start the Runtime using the [live guide](../../../docs/reference/live-workflow.md). In the
P100 environment with this checkout on `PYTHONPATH`:

```bash
python scripts/basis_launch.py scripts/qualify_live_motion.py --pascal-compat \
  --moving-receiver --turning-mounts --duration-ms 9600 \
  --output recordings/full-turn-new
python scripts/analyze_turning_mounts.py recordings/full-turn-new
python scripts/analyze_diffuse_iq.py recordings/full-turn-new
python scripts/analyze_diffuse_iq.py recordings/full-turn-new --negative-control

python scripts/basis_launch.py scripts/qualify_live_motion.py --pascal-compat \
  --moving-receiver --occlusion-test --duration-ms 4800 \
  --output recordings/screen-new
python scripts/analyze_diffuse_iq.py recordings/screen-new
```

These are separate controlled direct-path cases. The screen remains RF-only,
without matching Runtime collision geometry. The coherent I/Q reference shares
traced gains/delays/Dopplers and does not independently calibrate RF amplitudes.
Combined turning/occlusion, diffuse transitions, arbitrary Unreal mesh export,
minute-scale stability and hardware calibration remain open.
