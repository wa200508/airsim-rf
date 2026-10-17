# Turning radios with multipath — 16 October 2026

Two additional real Runtime flights pass the continuous coherent-sum/filter
reference while both radios turn with nonzero mounts. Each case records
**960,000 complex samples spanning 0.480 simulated seconds** at 2 MS/s, in forty
12 ms channel windows.

| Case | Paths per snapshot | Whole I/Q NRMSE | Boundary I/Q NRMSE |
| --- | ---: | ---: | ---: |
| Isotropic, LoS + specular ground, 0.01 W source | 2 | 0.2474% | 0.2429% |
| Directional, LoS + specular + fixed-surface diffuse, 1 W source | 1,026 | 0.4979% | 0.5006% |

Both are below the unchanged 1% thresholds. Both flight commands complete, with
no ADC clipping. The second uses 1,024 fixed-surface samples; this is an
integration budget, not a convergence guarantee. The cases differ in pattern,
source power and path model and are not comparative power or performance tests.

The body-frame velocity commands, yaw rates and offset mounts are those in the
[turning-mount report](../turning-mounts-20261015/REPORT.md). The second additionally
uses the [directional pattern](../directional-turns-20261015/REPORT.md); its 1 W
source avoids the previously observed poor ADC resolution at lower received
levels. RF geometry remains the synthetic flat ground. All traced complex gains,
delays and Dopplers are exported per snapshot.

The CPU reference sums those paths for the known CW waveform and applies a
continuous receiver filter, then compares actual ADC readback. It reuses path
parameters, so it qualifies the combined renderer/filter/recording integration,
not independent Fresnel/scattering amplitudes or arbitrary physical speckle.
Boundary neighborhoods include 128 samples on each side of each update. The
channel still freezes geometry and antenna gain within each 12 ms window.

## Reproduce

Start the standalone Runtime, then run in the CUDA environment:

```bash
python scripts/qualify_live_motion.py --turning-mounts --moving-receiver \
  --reflection --output recordings/turning-specular-new
python scripts/analyze_diffuse_iq.py recordings/turning-specular-new
python scripts/qualify_live_motion.py --turning-mounts --moving-receiver \
  --diffuse surface --antenna-pattern tr38901 --transmit-power-w 1 \
  --output recordings/turning-diffuse-new
python scripts/analyze_diffuse_iq.py recordings/turning-diffuse-new
```

Capture used the P100-compatible launcher and `--pascal-compat`; analysis ran on
CPU. See [specular checks](specular/diffuse-iq.json),
[combined directional/diffuse checks](directional-surface/diffuse-iq.json), and
the manifests, motion/trajectory, metadata, inspection and logs in each directory.
Raw I/Q and larger channel exports remain ignored locally, identified by hashes.
[Regression log](standard-tests.log).

These cases extend controlled turning coverage to specular and fixed-surface
diffuse paths. General occlusion transitions during turns, roughness calibration,
arbitrary terrain and long-duration stability remain open. No production
renderer tuning was needed. Timing ratios in manifests are wall seconds per
simulated signal second; shared-host correctness captures are not throughput runs.
