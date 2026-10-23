# 77 GHz FMCW radar: terrain-masked racetrack

This package replaces the direction-finding emitter with a **moving monostatic
radar**. The other drone is a passive point-scattering target, with no transmitter.
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
- TargetDrone: 5 m diameter circle centered at `(0, 25)`, near the old receiver
  laydown. It flies at 2 m/s with 1.6 m/s² centripetal acceleration (~0.16 g).
  Its constant absolute altitude is ground elevation at its circle center +10 m;
  the local terrain variation puts it about 9.4–10.6 m AGL around the circle.
- Planned route qualification: radar clearance stays above 28 m; the western
  part of the southern leg/turn is occluded by the shared hill. The same triangle
  mesh supplies an independent visibility check against Sionna's direct paths.
- Ideal route range-rate extrema are approximately −20 and +19 m/s, derived
  from relative position/velocity. Doppler is never assigned independently of
  motion. Native flight-controller tracking can change the achieved extrema.

Both drones use the native ProjectAirSim flight controller and actual kinematic
readback. The camera follows 5 m behind the radar and looks toward the target;
labels identify radar and target, omitting terrain-hidden anchors. The radar
antenna has ideal target-tracking pointing, distinct from drone body attitude.
It has no modeled gimbal limits or tracking error. This is an acquisition setting,
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
| Target RCS | **1,000,000 m²**, scalar and aspect-independent | Deliberately unrealistic demonstration target for conspicuous returns |
| Noise figure / IF voltage gain | 15 dB / 60 dB | Modeling assumptions |
| IF passband / Gaussian beam widths | 30 kHz–4.5 MHz / 56° azimuth × 28° elevation | Modeling assumptions |
| Quantizer | 12 bits, 1 V span, 0.5 V bias, ideal I/Q pair | Transfer-function approximation, not TI ADC calibration |

The target RCS is intentionally enormous: **80 dB more echo power** than the
previous 0.01 m² setting (10,000× the echo voltage before receiver processing).
It makes the target conspicuous for demonstrations and is not representative
of a real drone or evidence of this board's detection range. Edit
`radios.json` → `radar.targets[0].rcs_m2` to restore a realistic study value.
Terrain occlusion still removes the direct path; reflected returns, noise and
ADC clipping continue to follow the configured model.

Real raw ADC capture from the board requires a supported acquisition setup,
commonly the DCA1000EVM [1,4], beyond buying the radar board alone.

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
scattering, micro-Doppler/rotor blades, atmosphere/rain or mutual radar interference.
The scalar RCS and common target-directed Gaussian antenna gain are approximations;
a fully polarimetric target scattering matrix and per-path measured board
antenna patterns are not implemented.

The renderer computes dechirped IF directly: it does not sample a 77 GHz carrier
at 10 MS/s. Its convention is TX × conjugate(RX); positive slow-time frequency
means receding range rate. Delay and Doppler create the fast-time beat, and
carrier phase evolves coherently across chirps. The narrowband Doppler model is
retained. Actual readback position and velocity are extrapolated within each
4 ms source window, then refreshed. That is a local constant-velocity
approximation, not per-chirp physics readback or a wideband Doppler model.

Noise, approximate steady-state analog IF filtering and ADC quantization follow
propagation. The archived values are **bias-subtracted ADC volts**, after modeled
IF gain. The 256 valid samples occupy their correct positions in each 400-sample
PRI. The other samples are zero-filled **ADC gate gaps**, not continuous receiver
measurements. Receiver configuration records the gate and PRI, so playback does
not compress time or lose slow-time phase. DF/ESM scenario streams remain continuous.
**Runtime:** the 4 ms window is a simulated acquisition interval, not a measured
wall-clock deadline. Each window currently makes 100 channel solves and renders
IF/noise/ADC in NumPy before transport/recording. No new GPU throughput or
120 Hz real-time claim has been measured for this example.

At 10 MS/s, one cf32 channel needs 80 MB/s and about **9.6 GB for 120 s**, plus
journals/video. Set `mission.record_iq=false` to disable bulk recording.

The [Radar RF Skill](https://github.com/wa200508/Radar-skill) knows only receiver channel,
carrier, sample rate and chirp/gate timing. It uses the first 64 chirps from each
100-chirp window, per-ramp DC removal, Hann windows and a 2D FFT, then reports a candidate above an
18 dB contrast threshold relative to the median map power. This is a simple
teaching detector, **not a calibrated CFAR false-alarm specification**. Its peak
range is corrected for range/Doppler coupling; the displayed map's range axis
retains that coupling. Its independent CPU container has no Sionna, CUDA or AirSim
installation and never receives scene, flight plan, target RCS or target truth.

## Editing and code ownership

| Question | Input / implementation |
|---|---|
| Flight, target orbit, speed, height? | `flight.json`; native path compilation in [dashboard_scenario.py](../../src/airsim_rf/dashboard_scenario.py) |
| Terrain and dielectric assumptions? | `environment.json`, copied/exported into the run's shared geometry bundle |
| Carrier, ramp, PRI, ADC, noise, antenna, RCS? | `radios.json` → `radar.profile` and `radar.targets` |
| Clock, duration, recording, camera and chosen skill? | `scenario.json` |
| Path pairing, phase, IF, noise and quantizer? | [fmcw.py](../../src/airsim_rf/fmcw.py) |
| Actual poses, window acquisition and gate packing? | [dashboard_radar.py](../../src/airsim_rf/dashboard_radar.py); orchestrated by [dashboard_producer.py](../../src/airsim_rf/dashboard_producer.py) |
| Detection and range/Doppler FFT? | [Radar-skill processing](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/processing.py) and [receiver app](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/app.py); local `skills/radar.py` is a compatibility import |

The receiver is maintained, tested and published in its own repository. This
scenario pins its image and uses `revision_policy: independent`; simulator/RF
images still must match each other. See [radar skill separation](../../docs/radar-skill.md).

## References

1. Texas Instruments, [IWR1843BOOST evaluation board](https://www.ti.com/tool/IWR1843BOOST).
2. Texas Instruments, [IWR1843 product specifications and datasheet](https://www.ti.com/product/IWR1843).
3. Texas Instruments Radar Toolbox, [IWR1843BOOST antenna radiation patterns](https://dev.ti.com/tirex/content/radar_toolbox_2_30_00_12/hardware_docs/antenna_radiation_patterns/iwr1843boost.html).
4. Texas Instruments, [DCA1000EVM real-time data capture adapter](https://www.ti.com/tool/DCA1000EVM).
