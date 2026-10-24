# Turning drones with offset radios — 15 October 2026

Real Runtime flight, offset radio kinematics, GPU direct-path propagation and
recorded I/Q pass a controlled turning case. Capture spans **0.480 simulated
signal seconds**, or **960,000 complex samples at 2 MS/s**, across forty 12 ms
channel windows. This is an integration/accuracy check, not a throughput run.

## Scenario

Both Fast Physics drones start at NED (−20, 0, −20) and (20, 0, −20) m. TX is
commanded to move body-forward at 3 m/s with +0.7 rad/s yaw rate. RX receives
body velocity (−3, 1, 0) m/s with −0.5 rad/s yaw rate. Capture starts after 2.001
simulated seconds of settling. These commands are body-relative, so the paths
curve as the drones yaw; the measured poses and velocities, not commanded values,
are used for validation.

The TX radio sits at body offset (0.6, 0.2, 0.1) m, and RX at (−0.4, 0.3, −0.1) m.
Rotation moves these phase centers relative to their drone centers. Their velocity
must include angular velocity crossed with the rotated lever arm. The RF scene
is flat ground with direct paths only; antennas are isotropic, vertically
polarized. Carrier is 915 MHz; input is a known +150 kHz tone, with noise disabled.

## Independent checks

The analyzer transforms each saved pose quaternion and mount offset directly,
without calling the bridge's mount conversion. It finite-differences the resulting
positions to check velocity, and finite-differences radio separation to check
Doppler. Interior samples avoid one-sided endpoint derivative errors. Tolerances
were set to 0.05 m/s velocity, 1 mm path length and 0.15 Hz Doppler.

| Measurement | Result |
| --- | ---: |
| TX / RX mount displacement | 1.129 / 1.284 m |
| TX / RX travel-heading change | 0.252 / 0.181 rad |
| Maximum TX / RX mount velocity error | 0.000234 / 0.000156 m/s |
| Maximum direct-path length error | 0.00000628 m |
| Maximum Doppler error vs range finite difference | 0.000702 Hz |
| Maximum measured tone Doppler error vs bridge prediction | 0.000441 Hz |
| Whole-recording I/Q normalized RMS error | 0.2487% |
| Boundary-neighborhood I/Q normalized RMS error | 0.2505% |

Both flight commands completed, with no ADC clipping. Ignoring mount offsets
fails the 1 mm range tolerance: even the smallest resulting error is 2.43 mm.
This is a useful negative control against accidentally using drone centers.

The separate I/Q reference sums exported complex path gains, delay and Doppler,
then continuously filters the signal and compares with the public recording
reader. It shares traced path parameters; it independently checks signal
rendering/filter state, not the electromagnetic gain model. Its 1% NRMSE
threshold passes for both whole-recording and 128-sample boundary neighborhoods.

## Reproduce

Start the [Runtime server](../../../docs/reference/live-workflow.md#complete-two-radio-first-run),
then run in the CUDA environment:

```bash
python scripts/qualify_live_motion.py --moving-receiver --turning-mounts \
  --output recordings/turning-new
python scripts/analyze_turning_mounts.py recordings/turning-new
python scripts/analyze_diffuse_iq.py recordings/turning-new
```

Capture used the P100-compatible image with `scripts/basis_launch.py` and
`--pascal-compat`. Analysis ran in the CPU image. The pinned Runtime revision,
source/config hashes, actual sample interval and dependency versions are in the
[manifest](manifest.json). The task server was stopped afterward.

[Geometry checks](turning-mounts.json), [I/Q checks](diffuse-iq.json),
[flight/Doppler checks](motion.json), [trajectory](trajectory.json),
[channels](channels.json), [recording inspection](inspection.json),
[client log](client.log), [regression log](standard-tests.log).
Raw I/Q remains in ignored local `recordings/`; its [hash](local-artifacts.json)
is retained here. Regression suite: **208 passed, 157 skipped**.

## Scope and remaining work

This qualifies one controlled turning case with nonzero TX/RX mounts and direct
propagation. Isotropic antennas do not qualify directional antenna gain/pattern
rotation, and this flight does not cover arbitrary roll/pitch, multipath
occlusion or diffuse changes during turns. Those remain broader model tests.
Unreal mesh alignment and distributed SDR transport remain separate integration
work. No production implementation changes were needed for this case.

Recorded service timing includes physics/RPC, snapshot, RF capture and recording
writes; it excludes final checkpoint writes and fsync. Ratios use wall seconds
per simulated signal second. Compilation and shared-host activity make this
correctness run unsuitable for comparative performance conclusions.
