# 77 GHz FMCW radar: terrain-masked racetrack

This package replaces the direction-finding emitter with a **moving monostatic
radar** observing three stationary ground targets with no transmitters.
The fixed targets are passive scalar-RCS point scatterers with colored box visuals.
The environment is an independent copy of the current hills/valleys DEM, exported
as identical triangles into Unreal and Sionna. Run with:

```bash
bash scripts/run_dashboard.sh --scenario mmwave-radar --open
```

The dashboard shows received dechirped ADC I/Q, its spectrum/waterfall, a
range/range-rate map and a thresholded radar candidate. It records the exact
samples in the existing GNU Radio/SigMF format for offline skill development.

## Flight and terrain

All coordinates are north/west/up metres, in this package's local RF frame.

- RadarDrone: 20 m/s clockwise stadium racetrack centered at `(0, -80, 210)`;
  400 m straights and 80 m turn radius. It starts at `(-200, 0, 210)`, heads east,
  and repeats. One lap is about 65.1 s; the default 120 s covers several straight
  passes and most of two laps. Nominal turn acceleration is 5 m/s² (~0.51 g).
- Three fixed ground targets near the old receiver laydown. Their scattering
  centers are anchored to the exact shared DEM; the AGL values place each center
  halfway up its illustrative box. None is a drone or a flight-control actor.

  | Target | RF horizontal position (m) | Center AGL (m) | Visual size (m) | RCS (m²) |
  |---|---|---:|---|---:|
  | GroundContainer | `(0, 25)` | 1.3 | 6 × 2.5 × 2.6, orange | 1,000,000 |
  | GroundShelter | `(65, 55)` | 1.8 | 4 × 4 × 3.6, teal | 500,000 |
  | GroundReflector | `(-75, 15)` | 1.0 | 1.5 × 1.5 × 2, violet | 250,000 |

- Planned route qualification: radar clearance stays above 28 m; the western
  part of the southern leg/turn is occluded by the shared hill. The same triangle
  mesh supplies an independent visibility check against Sionna's direct paths.
- Stationary targets still produce Doppler because the radar is moving.
  Relative range rates change sign between approaching and receding passes,
  and their magnitudes stay below the radar's 20 m/s speed. Native flight tracking
  can change the achieved values. Terrain masks part of every target's planned
  line of sight; targets can retain reflected echoes when the direct path is blocked.

Only RadarDrone uses a native ProjectAirSim flight controller and kinematic
readback. Target world positions and velocities are fixed: zero target velocity
is used for both channel propagation and intra-window evolution. The camera
follows 5 m behind the radar and looks toward the target group; labels identify
the radar and each target, omitting terrain-hidden anchors. The radar antenna
ideally tracks **GroundContainer**, the first configured target. Other targets
therefore have different range and off-boresight attenuation. There are no
modeled gimbal limits or tracking error. This is an acquisition setting,
not knowledge passed to the detection skill.

## Hardware and waveform

The reference hardware is TI's **IWR1843BOOST**, an off-the-shelf 77 GHz mmWave
FMCW evaluation board [1]. The IWR1843 supports 76–81 GHz, up to 4 GHz continuous
sweep, three TX/four RX, 12 dBm TX and up to 25 MS/s ADC [2]. This example enables
**one TX and one complex RX channel**, rather than simulating its MIMO array.
TI's board antenna-pattern page reports about 7 dBi peak gain [3]. An older
xWR1843BOOST guide reports a different peak value; this package explicitly uses
the conservative 7 dBi value and does not claim a calibrated board antenna.

| Parameter | Value | Basis |
|---|---:|---|
| Carrier / sweep | 77 GHz / 50 MHz | Configurable example, within device limits |
| Ramp / PRI | 32 µs / 40 µs | Configurable example |
| ADC | 10 MS/s, 256 complex samples/ramp, starting 3 µs into ramp | Configurable example |
| Nominal / sampled range resolution | 3.00 m / 3.75 m | Sweep width / sampled sweep width |
| Unambiguous range rate | ±24.33 m/s | One-TX wavelength/(4×PRI) |
| Detection CPI | 64 chirps = 2.56 ms | Receiver skill setting |
| Range-rate bin spacing | ~0.76 m/s | Wavelength/(2×CPI) |
| RF update / physics step | 4 ms / 1 ms | 100 chirps per synchronized source window |
| TX / antenna peak gain | 12 dBm / 7 dBi each way | Device specification / conservative board reference |
| Target RCS | **1,000,000 / 500,000 / 250,000 m²**, scalar and aspect-independent | Deliberately unrealistic demonstration targets for conspicuous, distinct returns |
| Noise figure / IF voltage gain | 15 dB / 60 dB | Modeling assumptions |
| IF passband / Gaussian beam widths | 30 kHz–4.5 MHz / 56° azimuth × 28° elevation | Modeling assumptions |
| Quantizer | 12 bits, 1 V span, 0.5 V bias, ideal I/Q pair | Transfer-function approximation, not TI ADC calibration |

The three RCS values remain intentionally enormous, preserving conspicuous
returns for demonstrations. They are not calibrated RCS values for shipping
containers, shelters or reflectors, and do not establish the board's detection
range. Edit `radios.json` → `radar.targets[].rcs_m2` for a realistic study.
Terrain occlusion still removes direct paths; reflected returns, noise and
ADC clipping continue to follow the configured model.

Real raw ADC capture from the board requires a supported acquisition setup,
commonly the DCA1000EVM [1,4], beyond buying the radar board alone.

## Transmit/receive control

The skill sends its mode to `PUT /v1/configuration` on the RF adapter, checks
the returned configuration identity, then commands TX and RX on with
`POST /v1/state`. It receives the resulting dechirped ADC I/Q on TCP 8811.
The adapter starts disabled and cannot capture until the skill enables receive.
TX off with RX on removes target illumination/echoes while preserving receiver
noise and ADC behavior. Controls apply at acquisition-window boundaries; settings
cannot change midstream without a new metadata/recording session.
The [control adapter](../../src/airsim_rf/radar_control.py) has no detector
imports. The skill uses the same [hardware-neutral contract](https://github.com/wa200508/Radar-skill/blob/main/docs/transceiver-control.md)
for physical adapters; no TI/DCA1000 hardware driver is supplied yet.
Recorded-I/Q development uses explicit `--replay` and never commands a transmitter.

## Exactly what is simulated

[FMCWRadar](../../src/airsim_rf/fmcw.py) traces Sionna paths from radar to each
passive target once per chirp. The reciprocal scalar point-scatter model pairs
outbound/return paths, preserving complex carrier phase, round-trip delay,
Doppler and RCS scaling consistent with the monostatic radar equation.
`max_depth_per_leg: 1` permits LOS and one specular terrain reflection on each
leg: a reflected/reflected echo therefore has **two total terrain interactions**.
This differs from a one-bounce limit on the complete round trip.

Sionna uses the shared DEM's dielectric material settings for specular paths.
Blocked direct paths are removed, rather than merely attenuated. Reflected
illumination/return paths may still contribute. This model does **not** include
terrain backscatter clutter, diffuse scattering, diffraction, target mesh
scattering, micro-Doppler, atmosphere/rain or mutual radar interference.
The colored box meshes are static presentation markers; their surfaces are not
added as RF obstacles or extra scattering surfaces. Echoes originate at their
configured centers with scalar RCS. The shared terrain remains the RF occluder
and specular reflector. The scalar RCS and common target-directed Gaussian antenna gain are approximations;
a fully polarimetric target scattering matrix and per-path measured board
antenna patterns are not implemented.

The renderer computes dechirped IF directly: it does not sample a 77 GHz carrier
at 10 MS/s. Its convention is TX × conjugate(RX); positive slow-time frequency
means receding range rate. Delay and Doppler create the fast-time beat, and
carrier phase evolves coherently across chirps. The narrowband Doppler model is
retained. Actual radar readback position and velocity are extrapolated within each
4 ms source window, then refreshed. That is a local constant-velocity
approximation, not per-chirp physics readback or a wideband Doppler model.

Noise, approximate steady-state analog IF filtering and ADC quantization follow
propagation. The archived values are **bias-subtracted ADC volts**, after modeled
IF gain. The 256 valid samples occupy their correct positions in each 400-sample
PRI. The other samples are zero-filled **ADC gate gaps**, not continuous receiver
measurements. Receiver configuration records the gate and PRI, so playback does
not compress time or lose slow-time phase. DF/ESM scenario streams remain continuous.
**Runtime:** the 4 ms window is a simulated acquisition interval, not a measured
wall-clock deadline. Each window currently makes 100 channel solves, each batching the three targets, and renders
IF/noise/ADC in NumPy before transport/recording. No new GPU throughput or
120 Hz real-time claim has been measured for this example.

At 10 MS/s, one cf32 channel needs 80 MB/s and about **9.6 GB for 120 s**, plus
journals/video. Set `mission.record_iq=false` to disable bulk recording.

The [Radar RF Skill](https://github.com/wa200508/Radar-skill) selects the transmit
sweep, power and PRI and the receive gate/gain from `radar-mode.json`, commands
the radio adapter to enable TX and RX, then consumes returned ADC samples.
It knows its own transmitted waveform and receiver channel settings. It uses the first 64 chirps from each
100-chirp window, per-ramp DC removal, Hann windows and a 2D FFT, then reports a candidate above an
18 dB contrast threshold relative to the median map power. This is a simple
teaching detector, **not a calibrated CFAR false-alarm specification**. Its peak
range is corrected for range/Doppler coupling; the displayed map's range axis
retains that coupling. Its independent CPU container has no Sionna, CUDA or AirSim
installation and never receives scene, flight plan, target RCS or target truth.

## Editing and code ownership

| Question | Input / implementation |
|---|---|
| Radar flight, speed and altitude? | `flight.json`; native path compilation in [dashboard_scenario.py](../../src/airsim_rf/dashboard_scenario.py) |
| Fixed target locations, heights, box visuals and RCS? | `radios.json` → `radar.targets`; AGL conversion in [dashboard_scenario.py](../../src/airsim_rf/dashboard_scenario.py), shared state resolution in [dashboard_radar.py](../../src/airsim_rf/dashboard_radar.py) |
| Terrain and dielectric assumptions? | `environment.json`, copied/exported into the run's shared geometry bundle |
| Carrier, sweep, ramp, PRI, TX power, receive gate and gain? | `radar-mode.json`, applied by the external skill through its transceiver client |
| Antenna, noise, IF filter, ADC transfer, RCS? | `radios.json` → `radar.profile` and `radar.targets` |
| Clock, duration, recording, camera and chosen skill? | `scenario.json` |
| Path pairing, phase, IF, noise and quantizer? | [fmcw.py](../../src/airsim_rf/fmcw.py) |
| Actual poses, window acquisition and gate packing? | [dashboard_radar.py](../../src/airsim_rf/dashboard_radar.py); orchestrated by [dashboard_producer.py](../../src/airsim_rf/dashboard_producer.py) |
| Detection and range/Doppler FFT? | [Radar-skill processing](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/processing.py) and [receiver app](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/app.py); local `skills/radar.py` is a compatibility import |

The active skill is maintained and tested in its own repository. Its public
container is built directly from that repository by the pinned release workflow. This
scenario pins its image and uses `revision_policy: independent`; simulator/RF
images still must match each other. See [radar skill separation](../../docs/radar-skill.md).

## References

1. Texas Instruments, [IWR1843BOOST evaluation board](https://www.ti.com/tool/IWR1843BOOST).
2. Texas Instruments, [IWR1843 product specifications and datasheet](https://www.ti.com/product/IWR1843).
3. Texas Instruments Radar Toolbox, [IWR1843BOOST antenna radiation patterns](https://dev.ti.com/tirex/content/radar_toolbox_2_30_00_12/hardware_docs/antenna_radiation_patterns/iwr1843boost.html).
4. Texas Instruments, [DCA1000EVM real-time data capture adapter](https://www.ti.com/tool/DCA1000EVM).
