> **Detailed radar scenario reference.** For the runnable overview and edit locations, start with the [radar scenario](../../scenarios/mmwave-radar/README.md). For the common ground-response model and figures, see [clutter](../clutter.md).

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
Doppler-horizontal / range-up map and a thresholded radar candidate. It records the exact
samples in the existing GNU Radio/SigMF format for offline skill development.

## Flight and terrain

All coordinates are north/west/up metres, in this package's local RF frame.

- RadarDrone: 20 m/s clockwise stadium racetrack with horizontal center `(0, -80)`;
  400 m straights and 80 m turn radius. It starts at horizontal `(-200, 0)`, heads east,
  and repeats. The horizontal lap length corresponds to about 65.1 s before climbs/controller effects; the default 120 s covers several straight
  passes and most of two laps. Nominal turn acceleration is 5 m/s² (~0.51 g).
- Three fixed ground targets near the old receiver laydown. Their scattering
  centers are anchored to the exact shared DEM; the AGL values place each center
  halfway up its illustrative box. None is a drone or a flight-control actor.

  | Target | RF horizontal position (m) | Center AGL (m) | Visual size (m) | RCS (m²) |
  |---|---|---:|---|---:|
  | GroundContainer | `(0, 25)` | 1.3 | 6 × 2.5 × 2.6, orange | 1,000,000 |
  | GroundShelter | `(65, 55)` | 1.8 | 4 × 4 × 3.6, teal | 500,000 |
  | GroundReflector | `(-75, 15)` | 1.0 | 1.5 × 1.5 × 2, violet | 250,000 |

- Planned route qualification: terrain-following clearance is at least 20 m; the western
  part of the southern leg/turn is occluded by the shared hill. The same triangle
  mesh supplies an independent visibility check against Sionna's direct paths.
- Stationary targets still produce Doppler because the radar is moving.
  Relative range rates change sign between approaching and receding passes,
  and their magnitudes stay below the radar's 20 m/s speed. Native flight tracking
  can change the achieved values. Terrain masks part of every target's planned
  line of sight; terrain clutter can remain when a target direct path is blocked.

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

[FMCWRadar](../../src/airsim_rf/fmcw.py) uses **first-order scattering**:
one direct echo from each visible point target plus one return from each visible
terrain sample. Targets are RCS scatterers, not virtual receiver/transmitter
endpoints. There is no outbound/return path cross-product and no terrain-reflected
illumination or return leg attached to a target. The older
`max_depth_per_leg` setting is replaced by `echo_model: first-order`.

[TerrainBackscatter](../../src/airsim_rf/radar_scattering.py) samples the actual
shared Sionna mesh with **1,024 seeded, stratified, uniform-area points**, controlled by the shared
`propagation.samples_per_link` setting in `radios.json`. Those
points and their unit-magnitude random complex scattering weights stay anchored
to the same geometry between pulses. This is a surface quadrature budget,
not a guarantee of 1,024 surviving echoes. All configured surface areas are
sampled; no antenna hotspot-only sampling is used. Actual two-way beam gain,
local surface normal, range and geometric visibility determine contributions.

The default earth class has an illustrative **sigma0 = −20 dB** (0.01 m² RCS
per m² of actual surface at normal incidence), with a cosine-to-the-first-power
incidence response. Effective patch RCS is `sigma0 × represented area × cos(angle)`.
Increasing sample count reduces each patch's represented area rather than
increasing expected total scattered power. Finite coherent sums exhibit speckle;
changing the sample budget or seed starts a new realization. Numerical
convergence and calibrated land-cover statistics are not established.

`max_range_m: 400` rejects both targets and terrain samples beyond 400 m slant
range **before visibility tracing**. This is an explicit model cutoff, not a
hard cutoff of the analog IF filter. The 4.5 MHz IF corner corresponds to about
432 m at zero Doppler in this mode. In-range target and terrain visibility uses
the shared Sionna/Mitsuba mesh on the active CPU or CUDA backend; a small,
distance-scaled floating-point tolerance prevents a surface sample from
occluding itself. Blocked targets have no direct or secondary target echo.
Visible terrain can still return clutter when a target is blocked.

Dielectric parameters remain the configured propagation materials for ordinary
radio-to-radio links. Radar terrain sigma0 is a separate, explicit empirical
backscatter rule; it is not inferred from permittivity or a visual texture.
Additional cover classes can be encoded as shared mesh objects with distinct
material IDs and corresponding `clutter.materials` rules. No automatic LULC
raster ingestion or calibrated material-to-sigma0 conversion is supplied.
The colored target boxes remain presentation markers with scalar point RCS;
they do not become RF occluders or mesh scattering models. Diffraction,
secondary/multiple scattering, polarimetric target matrices, micro-Doppler,
atmosphere/rain and mutual radar interference are omitted. This is an intentional
fidelity choice; target-assisted multipath is not universally negligible.

ESM/comms still calculate their configured radio-to-radio multipath. This
radar policy does not change the one-way SDR renderer or its propagation solver.
See [first-order radar model and verification](../radar-scattering.md).

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
wall-clock deadline. Each window checks first-order visibility once per chirp and batches all
visible target/clutter tones in bounded NumPy tiles before noise, ADC and
transport/recording. IF filter coefficients are cached per hardware profile. No new GPU throughput or
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
| Radio-pair sampling budget for radar or ESM/comms? | `radios.json` → `propagation.samples_per_link` |
| Radar sigma0/classes, phase seed, range limit? | `radios.json` → `radar.clutter` and `radar.max_range_m` |
| Clock, duration, recording, camera and chosen skill? | `scenario.json` |
| Visibility, terrain quadrature, phase, IF, noise and quantizer? | [radar_scattering.py](../../src/airsim_rf/radar_scattering.py) and [fmcw.py](../../src/airsim_rf/fmcw.py) |
| Actual poses, window acquisition and gate packing? | [dashboard_radar.py](../../src/airsim_rf/dashboard_radar.py); orchestrated by [dashboard_producer.py](../../src/airsim_rf/dashboard_producer.py) |
| Detection and range/Doppler FFT? | [Radar-skill processing](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/processing.py) and [receiver app](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/app.py); local `skills/radar.py` is a compatibility import |

The active skill is maintained and tested in its own repository. Its public
container is built directly from that repository by the pinned release workflow. This
scenario pins its image and uses `revision_policy: independent`; simulator/RF
images still must match each other. See [radar skill separation](../radar-skill.md).

## References

1. Texas Instruments, [IWR1843BOOST evaluation board](https://www.ti.com/tool/IWR1843BOOST).
2. Texas Instruments, [IWR1843 product specifications and datasheet](https://www.ti.com/product/IWR1843).
3. Texas Instruments Radar Toolbox, [IWR1843BOOST antenna radiation patterns](https://dev.ti.com/tirex/content/radar_toolbox_2_30_00_12/hardware_docs/antenna_radiation_patterns/iwr1843boost.html).
4. Texas Instruments, [DCA1000EVM real-time data capture adapter](https://www.ti.com/tool/DCA1000EVM).


## Low flight and demonstration noise

`flight.json` now selects 20 m minimum planned terrain clearance with
`terrain_clearance_m: 20.0` and `max_vertical_grade: 0.2`. The nominal center/start
height of 120 m RF-up is a lower floor. Preparation creates a 3-D route above
the exact DEM, anticipating hills and limiting climb/descent grade. Native
kinematics drive the RF windows as before; this is not an idealized pose clamp.

`radios.json` → `radar.profile.noise_power_offset_db` is the noise control.
The selected demo value **−25 dB** reveals terrain clutter in noisy, quantized
ADC I/Q at the checked route snapshots. **0 restores the original receiver
noise model**. Temperature/noise figure, TX/IF gains, antenna, target RCS and
backscatter rules remain their existing values; the noise offset is an explicit
visualization adjustment rather than a measured board specification.
See [controls and model semantics](../demo-tuning.md) and the
[matched-noise ADC checks](../../results/reviews/low-terrain-demo-20261024/REPORT.md).
