# Off-the-shelf radar profile: Infineon Distance2GoL

The new default hardware profile is based on the purchasable
[Infineon DEMO DISTANCE2GOL kit](https://www.infineon.com/evaluation-board/DEMO-DISTANCE2GOL)
(order code `DEMODISTANCE2GOLTOBO1`). It combines the BGT24LTR11 RF shield and
Radar Baseboard MCU4. It supports software-controlled FMCW ranging, one TX and
one RX, and sampled in-phase and quadrature IF channels. This is a specification
based simulation profile, not a calibrated digital twin or a driver for the kit.

The manufacturer page was checked on 2026-10-02 and listed the product as active
with stock available. Its embedded unit quote was 217.65, but a currency-qualified
regional checkout price was not available in the retrieved page. Check the
product link for current price, currency, tax and shipping before setting a
hardware budget. The choice prioritizes an accessible research kit with documented
LFM ranging and sampled I/Q; an under-$250 landed price has not been verified.

The primary technical source is Infineon's
[AN615, revision 1.10, 2023-02-14](https://www.infineon.com/assets/row/public/documents/24/42/infineon-an615-bgt24ltr11-demo-distance2gol-applicationnotes-en.pdf).
Table 1 gives RF and antenna specifications; Table 4 gives FMCW timing;
Figure 11 gives the high-gain baseband response. Section 3.2 describes synchronized
ADC sampling of I/Q, and the platform overview identifies an SD card interface
for storing raw data. USB GUI support is documented, but a live raw-data SDK
capture workflow has not been tested here.

## Run and inspect the recording

```bash
cd airsim-rf
.venv/bin/python examples/distance2gol_radar.py
.venv/bin/python -m pytest -q
```

This produces `distance2gol_radar.npz` and `distance2gol_radar.png`. The default
example models a drone at 2 m altitude moving forward at 0.3 m/s, with stationary
point targets at 10 m and 14 m (0.1 and 0.4 m² RCS). It records 16 chirps,
each with 128 complex samples, with thermal noise and ADC quantization enabled.
The observed range FFT peaks were 9.88 m and 14.05 m, with no clipping. First
chirp beat frequencies were 8846.76 Hz and 12404.78 Hz. Small range offsets arise
from FFT bin spacing, motion during the frame, and range-Doppler coupling.

```python
import json
import numpy as np

with np.load("distance2gol_radar.npz") as data:
    analog_if = data["if_volts"]          # complex64 [chirp, sample], simulated AC IF
    adc_iq = data["adc_iq_volts"]         # complex64 [chirp, sample], bias-subtracted ADC volts
    adc_codes = data["adc_codes"]        # uint16 [chirp, sample, 2], unsigned I/Q
    epochs_ns = data["sim_time_ns"]      # int64 [chirp], transmit-trigger timestamps
    profile = json.loads(str(data["profile_json"]))
    window = np.hanning(adc_iq.shape[1])
    range_fft = np.fft.fft(adc_iq * window, axis=1)
```

The saved profile records all published values and simulation choices. Truth
arrays (`target_ranges_m`, `target_doppler_hz`, `target_beat_hz`, and
`target_delays_s`) are separate from raw signal data. Reconstructed zero can
have a half-LSB offset because a 12-bit unipolar ADC does not have a code exactly
at 1.65 V. Your processing can remove per-chirp DC as appropriate.

`--no-noise` disables thermal noise while retaining ADC quantization.
`--speed` sets drone forward speed for the offline constant-velocity example.

## Published parameters and simulation assumptions

| Parameter | Model | Basis |
| --- | --- | --- |
| Center frequency | 24.125 GHz | AN615 Table 1 |
| Sweep | 24.025–24.225 GHz, 200 MHz | AN615 Tables 1 and 4 |
| Up-ramp duration | 1.5 ms | Table 4's stated default |
| MMIC output | +6 dBm | Table 1 EIRP conditions |
| TX feed loss | 2 dB | Table 1 EIRP conditions |
| Antenna peak gain | 10 dBi each | Table 1; section 3.7 also reports 9.6 dBi simulated |
| Boresight EIRP | +14 dBm | +6 − 2 + 10 |
| Full half-power beamwidth | 80° azimuth × 29° elevation | Table 1 |
| Beam shape | Front-facing Gaussian, zero rear gain | Approximation; sidelobes not reconstructed |
| High-gain IF amplification | 57 dB | Table 1 / Figure 11 |
| High-gain IF corners | 7 and 15 kHz | Table 1 / Figure 11 |
| Filter implementation | Analog 4th-order Butterworth bandpass for tones | Approximation to corners; not an exact circuit fit |
| ADC bias | 1.65 V | Section 3.8 |
| ADC conversion | 12-bit, 0–3.3 V | Modeling assumption, not validated firmware/ADC calibration |
| ADC sample rate/count | 100 kS/s, 128 samples | Modeling choice, not vendor default |
| ADC start | 100 µs into ramp | Modeling choice; capture ends at 1.38 ms |
| Chirp repetition interval | 5 ms | One example in AN615 Table 6, not a firmware default |
| Mixer voltage conversion gain | 0 dB | Uncalibrated estimate |
| Receiver noise figure | 12 dB | Uncalibrated estimate |
| Temperature | 290 K | Simulation choice |
| RF voltage reference impedance | 50 Ω | Simulation reference, not IF load calibration |

The nominal full-sweep range resolution is 0.749 m. The selected ADC acquisition
window observes only 1.28 ms of the 1.5 ms ramp, giving 0.878 m nominal resolution
before Hann window broadening. Fourfold FFT zero padding gives 0.220 m display
bins; it does not improve physical resolution. The 7–15 kHz IF passband
corresponds approximately to 7.87–16.86 m for stationary targets with this slope.
Signals outside that region are attenuated, not discarded. The model is using
the high-gain IF response, not the board's low-gain output response.

Infineon reports typical human detection at 15 m, with target and setting
dependent limits. Our point RCS examples do not validate that human detection
claim. Low-frequency attenuation and sidelobes outside the modeled passband
need a circuit model or measured frequency response for accurate prediction.
RX feed loss and absolute mixer conversion gain also need measurement; the
current IF volts are simulated estimates, not predictions calibrated to a
particular physical board.

## Signal model

The module uses LFM as repeated FMCW sweeps. Simulated mixing produces complex
IF directly, so the 200 MHz RF sweep does not need to be sampled at the ADC's
100 kS/s rate. The explicit convention is `TX * conjugate(RX)`:

```text
k = sweep_bandwidth / ramp_duration
tau = 2*R/c
fD = -2*range_rate/lambda
fbeat = k*tau - fD
apparent_range = c*fbeat/(2*k)
```

Positive Doppler is closing motion. A positive Doppler shifts the beat-derived
apparent range downward. Actual hardware I/Q sign or channel order may differ
and should be checked with a known target before comparing recordings.

Sionna provides each target's direct path, including carrier phase,
free-space loss, polarization coupling and any blockage from an aligned RF
scene. As in the pulsed prototype, the reciprocal point target echo is calibrated
to the monostatic radar equation with scalar RCS. A Gaussian antenna power pattern
applies gain on transmit and receive; a one-way -3 dB beam angle reduces echo
power by approximately 6 dB across the two-way link.

The IF chain adds an estimated mixer gain, the published op-amp gain, an
approximate filter response, colored thermal noise, ADC DC bias, clipping and
quantization. Tone filtering assumes steady state over the ADC window; ramp
reset transients and chirp nonlinearity are not modeled. Noise uses a digital
bandpass approximation with warm-up samples. Filtering of RF oscillator phase
noise, clutter, TX leakage and circuit offsets is also not yet modeled.

Offline frames update both drone and target positions between chirps using
constant velocities, retaining geometry-derived carrier phase. Within a ramp,
positions and envelope delays are frozen while Doppler is applied. With a 5 ms
PRI, a simple slow-time FFT has a ±0.621 m/s monostatic unambiguous velocity
limit at 24.125 GHz. Higher speeds can alias; this is a property of the selected
frame schedule, not the module's complete tracking capability.

## Use the profile on an AirSim drone

The existing AirSim adapter now selects `distance2gol` by default. With a live
simulator running separately:

```bash
.venv/bin/python examples/airsim_lfm_radar.py \
  --model distance2gol \
  --scene scene_drone_sensors.jsonc \
  --sim-config .deps/ProjectAirSim/client/python/example_user_scripts/sim_config/ \
  --robot Drone1 \
  --target-ned 10 0 -2 0.1 \
  --target-ned 14 0 -2 0.4 \
  --output airsim_distance2gol.npz
```

Coordinates are absolute AirSim NED meters; those targets are at 10/14 m only
when the drone is at `(0,0,-2)`. The antenna boresight is the drone's body +X
axis. Antenna offset is configurable via `--mount-body X Y Z`. This command
loads the scene, pauses it and captures a single ramp with the current antenna
pose and velocity. It leaves the simulator paused.

For live frames, call `AirSimRadarBridge.capture(targets)` after stepping the
simulator to each chirp epoch, then use `save_frame(captures, filename)` to save
the cube. Preserve actual timestamps if physics-step timing differs from the
requested PRI. The standalone `capture_frame()` extrapolates motion offline;
it does not drive AirSim physics. `--rf-scene` accepts an aligned Mitsuba scene
for blockage; without it, the RF scene is empty free space. Mesh scattering and
native AirSim sensor publication remain future integration work.

All 20 tests pass, including FMCW beat/range-Doppler coupling, radar power through
the IF chain, antenna gain, quantization/clipping, acquisition constraints and
coherent frame phase and batched target mapping. Tests use actual Sionna propagation. Live AirSim and a
physical Distance2GoL board have not been exercised in this workspace.
