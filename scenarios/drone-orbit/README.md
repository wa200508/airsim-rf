# Direction finding: drone over two receiving arrays

[Documentation](../../docs/README.md) · [Radar scenario](../mmwave-radar/README.md) · [Dashboard help](../../docs/dashboard.md)

A QPSK transmitter flies a circle above hills and a valley. Two fixed coherent
arrays receive direct and terrain-reflected signals; the independent
[DF-Skill](https://github.com/wa200508/DF-Skill) applies MUSIC to the received I/Q.

```bash
bash scripts/run_dashboard.sh --scenario drone-orbit --open
```

Open http://localhost:8765 and select **Launch mission** after readiness passes.
The same inputs run in the published containers; no scenario-specific rebuild
is required.

## What to look for

- **Receiver I/Q stream:** select either array's spectrum and waterfall.
- **MUSIC Spatial Search:** a full circular azimuth search with relative-power,
  eigenvalue and inter-element phase diagnostics. A ULA has front/back and
  elevation ambiguity; a peak is an arrival candidate, not guaranteed emitter truth.
- **Terrain masking:** reflections may remain when direct sight is blocked;
  a channel with no modeled path contains receiver noise/ADC output.
- **Camera and playback:** the native camera, actual drone track and RF results
  are paired by timestamp. Saved runs replay without rerunning simulation.

## Scenario settings

| Item | Default |
| --- | --- |
| Transmitter | One private QPSK source, 915 MHz carrier, 0.1 W |
| Receivers | Two stationary four-element vertical-polarized ULAs, 8 m AGL |
| Acquisition | 2 MS/s continuous post-ADC I/Q; 120 ms windows |
| Flight | 250 m-radius left orbit, 25 m/s; 20 m minimum planned terrain clearance |
| Terrain | Shared 800 m-wide illustrative DEM; RF-up elevation 100–190 m |
| Propagation | Direct and supported first-order specular paths; diffuse scattering, diffraction and transmission disabled |
| Front end | PlutoSDR-class filter/noise/12-bit ADC approximation |
| Demo noise | −25 dB noise-power offset; set 0 for the original modeled receiver noise |

The nominal 120 m RF-up height is a lower floor, not a flight plane through the
hills. The compiler anticipates terrain with a 20% ascent/descent grade bound;
actual native motion drives RF. The terrain, antennas and receiver response
are uncalibrated models. The skill receives receiver calibration and samples,
without the transmitter position, paths or terrain truth.

## Edit this package

| File | Change |
| --- | --- |
| [flight.json](flight.json) | Orbit, speed, clearance and climb grade |
| [radios.json](radios.json) | TX power, antennas, array laydown, receiver profile, noise and propagation |
| [waveform.json](waveform.json) | QPSK parameters or a private finite `.npy` sample source |
| [environment.json](environment.json) | DEM and dielectric properties shared by both engines |
| [scenario.json](scenario.json) | Duration, recording, camera and independent skill image/wiring |
| [quadrotor.jsonc](quadrotor.jsonc) | Vehicle dynamics, controller and sensors |

Copy the whole directory to make a variation:

```bash
cp -r scenarios/drone-orbit ~/my-df-scenario
python3 scripts/launch_dashboard.py --scenario ~/my-df-scenario --check-scenario
bash scripts/run_dashboard.sh --scenario ~/my-df-scenario --open
```

[Flight/noise knobs](../../docs/demo-tuning.md) · [Scenario schema](../../docs/scenarios.md)
· [Find the code](../../docs/code-map.md) · [Clutter/multipath](../../docs/clutter.md)
· [Profiling](../../docs/profiling.md) · [I/Q replay](../../docs/iq-replay.md)

Vehicle/controller data derives from pinned ProjectAirSim configuration;
[the neighboring upstream license](PROJECTAIRSIM-LICENSE.txt) applies to that
asset. The DEM is an original illustrative grid, not a surveyed environment.
