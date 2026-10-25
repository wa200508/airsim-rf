# FMCW radar: drone, ground targets and terrain clutter

[Documentation](../../docs/README.md) · [Direction-finding scenario](../drone-orbit/README.md) · [Dashboard help](../../docs/dashboard.md)

A flying 77 GHz radar follows a racetrack past three stationary ground targets.
The source generates target echoes and terrain backscatter; the independent
[Radar-skill](https://github.com/wa200508/Radar-skill) commands TX/RX and processes
received I/Q into range–Doppler maps.

```bash
bash scripts/run_dashboard.sh --scenario mmwave-radar --open
```

Open http://localhost:8765 and select **Launch mission** after readiness passes.

## What to look for

- **Range–Doppler:** Doppler is horizontal; range increases upward. Ground and
  targets have Doppler because the radar moves. Displayed range retains FMCW
  coupling; the strongest candidate's range is separately corrected.
- **Terrain masking and clutter:** a blocked target has no modeled echo. Visible
  foreground terrain can still return clutter. The saved receiver I/Q includes
  target echoes, terrain clutter and noise. The narrow/medium/wide dropdown
  changes only color limits; every option shows that same combined signal.
- **Receiver spectrum/waterfall:** dechirped ADC volts, with timing preserved
  across chirps. Gaps outside receive gates are zero-filled, not measurements.
- **Candidate:** a simple 18 dB median-map contrast threshold, not calibrated CFAR.
  The skill knows its own waveform but receives no scene or target truth.

## Scenario settings

| Item | Default |
| --- | --- |
| Hardware inspiration | TI IWR1843BOOST; one TX / one complex RX, not its full MIMO array |
| Waveform | 77 GHz carrier; 50 MHz up-chirp over 32 µs; 40 µs PRI; 12 dBm TX |
| Acquisition | 10 MS/s; 256 samples/chirp starting at 3 µs; 100 chirps per 4 ms window |
| Skill processing | First 64 chirps / 2.56 ms; Hann-windowed 2-D FFT |
| Resolution | About 3.75 m sampled range and 0.76 m/s range rate; unambiguous rate about ±24.3 m/s |
| Flight | 20 m/s racetrack, 400 m straights / 80 m turns; 20 m minimum planned clearance |
| Antenna | Ideal target tracking; 7 dBi peak / 56° azimuth × 28° elevation Gaussian approximation |
| Terrain | Same illustrative DEM as the DF scenario; explicit earth backscatter sigma0 −20 dB |
| Clutter budget / cutoff | 1,024 proposed surface samples per link; 400 m slant range |
| Demo noise | −25 dB noise-power offset; set 0 for the original modeled receiver noise |

The native aircraft follows a terrain-aware path with a 20% grade bound. The
antenna tracks GroundContainer; the other targets have different off-boresight
attenuation. The nominal 120 m RF-up floor is raised over the hills.

| Target | Horizontal RF position (m) | Center AGL (m) | RCS (m²) |
| --- | --- | ---: | ---: |
| GroundContainer | (0, 25) | 1.3 | 1,000,000 |
| GroundShelter | (65, 55) | 1.8 | 500,000 |
| GroundReflector | (−75, 15) | 1.0 | 250,000 |

These RCS values are **deliberately enormous** for a conspicuous demonstration.
The colored boxes are visual markers; RF uses fixed, aspect-independent point
RCS. The model has first-order target/terrain returns and no target-leg
multipath, diffraction or secondary scattering. Noise reduction, receiver gain,
material and antenna assumptions are not measured board calibration.

## Edit this package

| File | Change |
| --- | --- |
| [flight.json](flight.json) | Racetrack, speed, terrain clearance and grade |
| [radar-mode.json](radar-mode.json) | Skill-commanded sweep, carrier, PRI, power, receive gate and gain |
| [radios.json](radios.json) | Antenna, noise/ADC, target positions/RCS, `propagation.samples_per_link`, clutter classes and range limit |
| [environment.json](environment.json) | Shared DEM and materials |
| [scenario.json](scenario.json) | Duration, recording, camera and skill image/wiring |
| [quadrotor.jsonc](quadrotor.jsonc) | Vehicle/controller/sensors |

Copy this entire directory and use `--scenario /path/to/copy`; see
[scenario editing](../../docs/scenarios.md). At 10 MS/s a 120 s single-channel
cf32 recording needs about **9.6 GB**, plus video/journals. Review
[I/Q recording](../../docs/iq-replay.md) or disable `mission.record_iq`.

[Clutter model and figures](../../docs/clutter.md) · [Noise/flight tuning](../../docs/demo-tuning.md)
· [Profiling](../../docs/profiling.md) · [Detailed hardware, equations and citations](../../docs/reference/radar-scenario.md)
· [Independent skill/control contract](../../docs/radar-skill.md)

TI references: [IWR1843BOOST](https://www.ti.com/tool/IWR1843BOOST),
[IWR1843 specifications](https://www.ti.com/product/IWR1843). Real raw-board ADC
capture needs a compatible acquisition setup, commonly
[DCA1000EVM](https://www.ti.com/tool/DCA1000EVM). [Vehicle asset license](PROJECTAIRSIM-LICENSE.txt).
