# Moving I/Q and visibility transitions — 14 October 2026

Two real ProjectAirSim Runtime flights passed GPU-to-recording integration:
fixed-surface diffuse propagation with both endpoints moving, and a direct path
that disappears behind an RF screen and returns. Each capture spans **0.480
simulated signal seconds**, with **960,000 complex samples per receiver at
2 MS/s**, across forty 12 ms channel windows. No receiver noise was enabled.

## Physical scenarios

Both flights use the pinned Fast Physics quadrotor/controller, with commanded
TX NED velocity (3, 0, 0) m/s and RX velocity (−3, 1, 0) m/s. Capture starts
after 2.001 simulated seconds of controller settling. Actual RF positions move
approximately from TX (−16.472, 0, 20.363) to (−15.152, 0, 20.359) m and RX
(16.470, −1.167, 20.411) to (15.152, −1.606, 20.407) m. The radios approach
one another while the RX moves laterally. Neither drone flies through the screen.

The diffuse case uses flat RF ground, isotropic vertically polarized antennas,
915 MHz carrier and a finite +150 kHz complex tone at 0.01 W transmit scaling.
There are 1,024 fixed surface samples plus LoS and specular ground paths: 1,026
retained paths in each window. This sample budget tests integration, not power
convergence or calibrated surface roughness.

The screen case uses direct propagation only and a vertical RF-only rectangle
at x=0, y∈[−0.75, −0.65] m, z∈[0, 30] m. As the line between the two radios
sweeps laterally, its intersection with x=0 crosses the rectangle. This narrow
screen intentionally gives both transitions within one short controlled flight.
The Runtime has no matching screen collision geometry. This is not an Unreal
mesh-alignment or collision test.

## What passed

| Check | Fixed-surface diffuse | Direct path and screen |
| --- | --- | --- |
| Actual TX / RX displacement | 1.319 / 1.390 m | 1.319 / 1.390 m |
| Flight commands complete, no ADC clipping | Passed | Passed |
| Paths per snapshot | 1,026 | 1 → 0 → 1 |
| Full recording normalized RMS I/Q error | 0.2396% | 0.2434% |
| Boundary-neighborhood normalized RMS I/Q error | 0.2397% | 0.2459% |

The CPU reference independently sums every exported complex gain, delay and
Doppler for the known CW input, then applies one continuous receiver filter.
It reads the actual ADC recording through the public block reader. Boundary
neighborhoods include 128 samples on each side of every channel update; both
whole-recording and boundary thresholds are 1% NRMSE. The reference shares
traced path parameters with the renderer, so agreement does not independently
validate scattering amplitudes, visibility or physical channel statistics.

For the screen, visibility is additionally checked against an analytic segment–
rectangle intersection at each actual pose. All forty snapshots match. The path
vanishes at 0.144 simulated seconds relative to capture start and returns at
0.360 seconds. Transition timing is resolved at the 12 ms snapshot cadence,
not continuously within each frozen channel window. Receiver filter state
continues through the empty-channel interval; timestamps contain no sample gaps.

An injected π phase reset halfway through the diffuse recording raises whole
and boundary errors to about 144%, and the checker rejects it. The negative
control modifies samples in memory, preserving the source recording.
Regression suite: **207 passed, 157 skipped**; optional skipped dependencies are
not qualified by that count. Real GPU/server runs are separate evidence.

## Reproduce and evidence

Start the [Runtime server](../../../docs/live-workflow.md#complete-two-radio-first-run).
In the CUDA environment, run:

```bash
python scripts/qualify_live_motion.py --moving-receiver --diffuse surface \
  --samples-per-link 1024 --output recordings/surface-new
python scripts/analyze_diffuse_iq.py recordings/surface-new
python scripts/analyze_diffuse_iq.py recordings/surface-new --negative-control
python scripts/qualify_live_motion.py --moving-receiver --occlusion-test \
  --output recordings/screen-new
python scripts/analyze_diffuse_iq.py recordings/screen-new
```

The capture commands here used the P100-compatible image, `scripts/basis_launch.py`
and `--pascal-compat`; analysis ran in the CPU image without GPU access. The
Runtime commit and dependency versions are recorded in each manifest. Captures
and analysis used the scripts committed alongside this report.

- [Diffuse I/Q checks](surface/diffuse-iq.json), [negative control](surface/diffuse-negative-control.json),
  [flight checks](surface/motion.json), [manifest](surface/manifest.json).
- [Screen I/Q checks](screen/diffuse-iq.json), [visibility/flight checks](screen/motion.json),
  [exported channels](screen/channels.json), [manifest](screen/manifest.json).
- Each directory includes trajectory, metadata, inspection, client log and hashes
  of local raw I/Q/channel artifacts. [Regression log](standard-tests.log).

Raw I/Q and the larger diffuse channel export remain under ignored `recordings/`.
Manifest timing includes physics/RPC, snapshots, RF capture, data/metadata writes
and callback work; final checkpoint writes and fsync are excluded. Ratios are
wall seconds per simulated signal second. These shared-host correctness runs
include compilation and are not throughput comparisons.

## Remaining scope

This closes controlled moving fixed-surface I/Q rendering/filter integration and
one direct-path disappearance/return case. It does not establish smooth phase
across arbitrary path births/deaths, physical diffuse speckle, arbitrary geometry,
turn maneuvers/nonzero mounts, Unreal world export, physical SDR calibration or
distributed sample delivery. No production-code tuning or scenario-specific
optimization was needed for these passes.
