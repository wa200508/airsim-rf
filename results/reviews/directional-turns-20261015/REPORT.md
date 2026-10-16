# Directional antennas during turning flight — 15 October 2026

Directional gain follows actual drone attitude in a controlled two-drone flight.
The observed gain changes **6.861 dB** over **0.480 simulated seconds**. Against
an independent antenna-pattern calculation, the maximum gain error is
**0.0000116 dB**. Holding orientation fixed gives **12.706 dB RMS error** and is
rejected by the checker.

## Scenario and reference

Repeat the [turning-mount scenario](../turning-mounts-20261015/REPORT.md) with
Sionna's `tr38901` vertically polarized antennas on both radios. Both drones
follow exactly the baseline's recorded poses/timestamps, including nonzero body
mounts. Each capture has 960,000 complex samples at 2 MS/s over forty 12 ms windows.
The baseline is isotropic; direct-path coefficient ratios cancel shared path
loss and polarization factors. An independent CPU calculation rotates the link
directions into each antenna's local frame, then evaluates the installed pattern:
8 dBi peak, 65° full half-power beamwidth in both cuts and 30 dB attenuation cap.
The source implementation is `sionna/rt/antenna_pattern.py::v_tr38901_pattern` in
the pinned Sionna checkout inside the GPU image. This qualifies the orientation
integration and relative directional gain, not absolute antenna calibration or
an independently validated polarization model.

## A failed I/Q check and its cause

| Measurement | 0.01 W source | 1 W source |
| --- | ---: | ---: |
| Reference signal RMS in ADC counts | 8.126 | 81.256 |
| Whole-recording I/Q NRMSE | 5.031% — failed | 0.5031% — passed |
| Boundary-neighborhood I/Q NRMSE | 5.173% — failed | 0.5031% — passed |
| Maximum component error, ADC counts | 0.503 | 0.526 |
| Components matching independently rounded reference codes | 99.874% | 98.807% |
| Clipping | None | None |

Both use the unchanged 1% I/Q threshold. The low-level signal is poorly resolved
by the fixed ADC scale. Error is approximately the half-count rounding bound,
with a small additional numerical rendering/reference discrepancy. Increasing
source power 100-fold raises voltage tenfold and reduces relative error tenfold.
This supports ADC quantization as the dominant cause; the failed low-level result
is retained rather than relabeled as passing. Code-equality fraction can decrease
at higher amplitude because small numerical voltage differences cross more ADC
rounding boundaries, even while relative error improves.

The I/Q reference reuses traced path parameters and applies continuous receiver
filtering. Gain-ratio validation is separate. Source power affects rendered
voltage, not the path coefficient ratio. Both flight commands complete and
recording inspections pass in both runs. These findings concern simulated inputs,
not RF transmission by physical hardware.

## Reproduce

Start the [Runtime server](../../../docs/live-workflow.md#complete-two-radio-first-run).
Run a baseline with `--turning-mounts --moving-receiver`, then:

```bash
python scripts/qualify_live_motion.py --turning-mounts --moving-receiver \
  --antenna-pattern tr38901 --transmit-power-w 0.01 --output recordings/directional-low
python scripts/analyze_directional_turns.py recordings/directional-low \
  --baseline recordings/turning-new
# Expected to fail the unchanged 1% criterion at this ADC signal level:
python scripts/analyze_diffuse_iq.py recordings/directional-low
python scripts/qualify_live_motion.py --turning-mounts --moving-receiver \
  --antenna-pattern tr38901 --transmit-power-w 1 --output recordings/directional-resolved
python scripts/analyze_directional_turns.py recordings/directional-resolved \
  --baseline recordings/turning-new
python scripts/analyze_diffuse_iq.py recordings/directional-resolved
```

Capture used the P100-compatible image, `scripts/basis_launch.py` and
`--pascal-compat`; analysis ran on CPU. Dependency/source provenance is in each
manifest. Timing ratios are wall seconds per simulated signal second; these
shared-host correctness runs include compilation and are not throughput comparisons.

Evidence: [low-level I/Q](low-level/diffuse-iq.json),
[resolved I/Q](resolved/diffuse-iq.json), [gain comparison](resolved/directional-gain.json),
[regression suite](standard-tests.log). Both case directories retain channels,
trajectory, metadata, manifest, flight checks, inspection, client log and raw
recording hash. Raw I/Q stays in ignored local `recordings/`.

This extends controlled direct-path turning qualification to directional gain.
Broader multipath maneuvers, independent polarization calibration and Unreal
alignment remain open. No production renderer tuning was needed.
