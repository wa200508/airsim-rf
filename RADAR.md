# Drone-mounted pulsed LFM radar

The prototype triggers one linear frequency-modulated pulse from the drone's
antenna location and returns complex baseband voltage samples over one pulse
repetition interval. Transmit and receive antennas occupy the same location.
Sionna computes a direct one-way path to each specified point target; the model
constructs the reciprocal return path and applies a scalar radar cross-section.

## Run it

```bash
cd airsim-rf
.venv/bin/python examples/lfm_radar.py
.venv/bin/python -m pytest -q
```

The example drone flies at 20 m/s toward two targets, at the same altitude of
50 m. Targets have true ranges of 300 m and 600 m, and RCS of 1 and 16 m²,
respectively. Their voltages are roughly equal: the farther target's increased
RCS compensates for its additional two-way loss. The example is noiseless by
default; `--noise` enables thermal receiver noise with a 4 dB noise figure.

The noiseless verified outputs are 299.79 m and 599.58 m after matched filtering,
and +1334.26 Hz Doppler for both targets. Positive Doppler means decreasing
range. Range estimates are quantized to the 3.00 m sample spacing, while nominal
range resolution is 7.49 m. No CFAR detection or range interpolation is applied.

| Parameter | Default |
| --- | --- |
| Carrier | 10 GHz |
| LFM bandwidth | 20 MHz, from -10 to +10 MHz baseband |
| Pulse duration | 1 µs |
| Pulse repetition interval | 100 µs (10 kHz PRF) |
| Complex sample rate | 50 MS/s |
| Receive window | 5000 samples |
| Peak transmit power | 100 W (1 W average at 1% duty cycle for a pulse train) |
| Antennas | One isotropic, vertically polarized antenna per endpoint |
| Loaded voltage impedance | 50 Ω, RMS complex-envelope convention |
| Receiver blanking | First 1 µs blanked during transmission |
| Receiver noise | Disabled; optional 290 K, 4 dB noise figure |

These are editable starting parameters in `RadarConfig`, not a hardware
specification. Blanking gives a nominal full-pulse minimum range near 150 m;
nearer targets can have truncated echoes. A full echo must arrive before the
receive window ends, near 14.84 km with these settings. This single-pulse model
does not alias echoes from earlier pulses into the window.

## Work with raw samples

`lfm_radar.npz` contains raw `iq_volts` (complex64), the sampled transmitted
chirp, pulse parameters, carrier/sample rate, voltage impedance, sim timestamp,
target truth metadata, valid round-trip delays, and a separately derived
complex matched-filter range profile. I is the real part and Q the imaginary
part. No dechirping or range processing is embedded in the raw I/Q.

```python
import numpy as np
from scipy.signal import correlate

with np.load("lfm_radar.npz") as data:
    iq = data["iq_volts"]
    tx = data["tx_template"]
    fs = float(data["sample_rate_hz"])
    compressed = correlate(iq, tx, mode="full", method="fft")[len(tx)-1:]
    ranges = np.arange(len(compressed)) * 299792458.0 / (2*fs)
```

The package's `range_compress()` also divides by the chirp's discrete energy,
so its output has units of complex volts. Raw matched-load echo power is
`abs(iq)**2 / impedance_ohm`, before pulse averaging.

## Attach it to ProjectAirSim

A simulator must be running separately. This example loads the supplied scene
and leaves it paused after triggering the radar pulse:

```bash
.venv/bin/python examples/airsim_lfm_radar.py \
  --model pulsed \
  --scene scene_drone_sensors.jsonc \
  --sim-config .deps/ProjectAirSim/client/python/example_user_scripts/sim_config/ \
  --robot Drone1 \
  --target-ned 300 0 -50 1 \
  --target-ned 600 0 -50 16 \
  --output airsim_lfm_radar.npz
```

Each `--target-ned` specifies a stationary point target's north/east/down
coordinates in meters and RCS in m². Targets are explicitly defined RF
scatterers; they are not inferred from scene actors. Ranges are measured from
the actual drone pose, so the sample coordinates above only give 300/600 m
ranges when the drone is at NED `(0,0,-50)`.

`--mount-body X Y Z` places the antenna relative to the drone body origin;
the adapter includes rotational lever-arm velocity. The adapter reads the
paused drone's ground-truth position, orientation, and velocity, converts NED
to the RF scene's north/west/up basis, and supplies the sim timestamp. Live
simulator capture has not been verified here; the adapter is source-checked
and unit-tested with a simulated client.

With no `--rf-scene`, propagation is free space. An aligned Mitsuba scene can
provide line-of-sight obstruction via `--rf-scene`; export geometry in meters,
with x north, y west, z up and the AirSim world origin. Point targets must be
placed in free space rather than inside an opaque target mesh, since this
solver treats them as virtual radio endpoints, not mesh scattering surfaces.

For repeated pulses, advance the paused simulator by a PRI between calls to
`AirSimRadarBridge.capture(targets)` and retain the actual sim timestamps. A
moving target can be supplied through `PointTarget.velocity_m_s`, but its
position must also be updated by the caller at each pulse epoch. During each
short receive window, geometry and envelope delay are frozen and carrier
Doppler evolves from the supplied velocities. Continuous pulse scheduling,
physics-step quantization, and overlapping-window handling remain the caller's
responsibility.

## Echo model and limits

For isotropic aligned antennas in free space the model is calibrated to:

```text
tau = 2*R/c
fD = -2*radial_range_rate/lambda
Pr = Ppeak * lambda² * sigma / ((4*pi)³ * R⁴)
v(t) = sqrt(Z*Ppeak) * h_echo(t) * chirp(t-tau)
```

The Sionna one-way coefficient already includes loss, carrier delay phase,
polarization coupling, and Doppler. The reciprocal monostatic echo coefficient
is `h_oneway(t)**2 * sqrt(4*pi*sigma)/lambda`, doubling phase and Doppler while
giving the radar equation's power scaling. The scalar target scattering phase
is set to zero; RCS alone does not describe a real target's scattering phase or
polarimetric response. Vertically polarized virtual target antennas are a
simple polarization approximation. Antenna tilt can affect coupling, but a
directional radar beam pattern is not modeled.

This model does not calculate full electromagnetic mesh scattering, multipath
radar echoes, clutter, receiver leakage, oscillator phase noise, or ADC effects.
The matched-filter example has no sidelobe window, and the rectangular LFM
pulse produces the expected range sidelobes. Optional noise assumes ideal
full complex Nyquist bandwidth. Raw samples represent one triggered pulse;
slow-time Doppler estimation requires a coherent sequence of pulses and enough
observation time. The reported target Doppler values are truth metadata, not
velocity estimates from the single-pulse matched filter.

The current integration is a Python sensor adapter. Publishing radar I/Q as a
native ProjectAirSim sensor topic and testing it with a live simulator remain
the next integration steps. FMCW would instead use repeated continuous chirps
and a receive dechirping stage; it is not the implemented waveform here.
