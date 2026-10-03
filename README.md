# airsim-rf

Start with [home setup](REPRODUCE.md) and the measured
[120 Hz timing report](PERFORMANCE.md). This standalone repository contains the
radar models, I/Q generation, Python AirSim adapter, tests and benchmarks.
ProjectAirSim and Sionna RT are pinned external dependencies downloaded by setup.

The [distributed simulation guide](DISTRIBUTED.md) adds one receiver worker per
GPU, an AirSim clock coordinator, and an AMS-GRA starter-kit RF MEL backend plus
DIS scene truth. It includes CPU container tests and per-GPU deployment files.

The [100-transmitter / 10-receiver runtime assessment](NETWORK_RUNTIME.md)
audits the work needed for a general AMS-GRA RF plane and provides reproducible
network propagation benchmarks, scaling arithmetic and GPU sizing assumptions.
The [accepted per-pulse, single-interaction model](PER_PULSE_RUNTIME.md) updates
that baseline with compact channels, new measurements and current limitations.
The [single-bounce optimization report](OPTIMIZATION.md) adds exhaustive one-way
reflection candidates for ESM/comms channels, with paired timings and physical
validation. Enable it with `RFReceiver(..., path_solver="single-bounce")`.
For distributed ground return, use the separate
[TX/RX-aware first-order scattering mode](GROUND_SCATTERING.md). Its per-link
sampling budget covers both antenna patterns and preserves sidelobe support;
the 144-path specular benchmark does not measure ground-clutter fidelity.

[GPU runtime planning](GPU_RUNTIME.md) separates measured CPU costs from
conditional per-GPU work estimates for the 100-TX/10-RX deployment. Host proposal
sampling is timed separately; GPU deadlines and VRAM require target measurements.

The [tested terrain scenario and waterfall plots](TERRAIN_SCENARIO.md) compare
flat ground with a simple DEM containing hills, slopes and a drainage swale.
It includes delay/Doppler waterfalls, coherent LFM responses, received-I/Q
spectrograms, saved data and commands to reproduce them in the container.

For a ready-made CPU test environment, see [the container guide](CONTAINER.md):

```bash
docker run --rm --network none ghcr.io/wa200508/airsim-rf:latest
```

```bash
git clone https://github.com/wa200508/airsim-rf.git
cd airsim-rf
python3.12 scripts/bootstrap.py
.venv/bin/python -m pytest -q
.venv/bin/python examples/distance2gol_radar.py
```

The current hardware-based starting point is an
[Infineon Distance2GoL FMCW profile](DISTANCE2GOL.md): 24.125 GHz, a 200 MHz
sweep over 1.5 ms, +14 dBm EIRP, a directional antenna, and a simulated IF/ADC
chain. Run `.venv/bin/python examples/distance2gol_radar.py` for a 16-chirp
complex I/Q recording. Published specifications and uncalibrated receiver
assumptions are listed in the guide; current regional purchase price needs
checking at the manufacturer checkout.

An initial Python bridge from ProjectAirSim vehicle kinematics to Sionna RT
propagation and complex baseband voltage samples. It includes an off-the-shelf
FMCW profile and an experimental monostatic pulsed LFM radar with scalar point
targets, raw I/Q, and matched-filter range compression. See
[the pulsed radar guide](RADAR.md) for that profile. The passive receiver example
is also retained.
These are signal-generation prototypes; native AirSim sensor publication and
live simulator validation remain to be implemented.

```bash
cd airsim-rf
.venv/bin/python examples/lfm_radar.py
```

This writes `lfm_radar.npz` (raw complex volts and a range profile) and
`lfm_radar.png` (I/Q and target ranges). The validated example recovers point
targets at 299.79 m and 599.58 m, with true ranges of 300 m and 600 m.

The upstream checkouts were fetched on 2026-10-02 and are clean at:

| Source | Version | Commit |
| --- | --- | --- |
| `.deps/ProjectAirSim` | main snapshot, nearest tag v1.1.0; Python client 1.1.0 | `cfb865f29f255b15ef28ec8fdcfaa01a6b66497f` |
| `.deps/sionna-rt` | release v2.2.0 | `15b5ee036917a4c2a9b6420e05570b77717e2fcc` |

The exact commits in `sources.json` identify the tested sources. The bootstrap
installs both source packages editable in this project's `.venv`.

## Run the validated standalone example

From the `airsim-rf` repository root:

```bash
.venv/bin/python examples/los_iq.py --output los_iq.npz
.venv/bin/python -m pytest -q
```

For a fresh checkout, use the tested Python 3.12 environment:

```bash
python3.12 scripts/bootstrap.py
```

The tested backend is `llvm_ad_mono_polarized` (CPU); LLVM is installed on this
machine. An NVIDIA GPU can accelerate larger ray-tracing scenes.

The example uses 1 W transmit power, isotropic vertically polarized antennas,
2.4 GHz carrier, 100 m separation, 10 m/s receding receiver velocity, and a
10 kHz transmitted baseband tone. At 1 MS/s it saves 4096 samples, approximately
4.096 ms. Expected received power is -50.052 dBm and tone frequency including
Doppler is 9919.945 Hz. Noise is disabled for this verification.

```python
import numpy as np

with np.load("los_iq.npz") as recording:
    iq = recording["iq_volts"]    # complex64 [samples]; real=I, imag=Q
    fs = float(recording["sample_rate_hz"])
    epoch_ns = int(recording["sim_time_ns"])
    power_w = np.mean(np.abs(iq)**2) / float(recording["impedance_ohm"])
    spectrum = np.fft.fftshift(np.fft.fft(iq))
    frequencies = np.fft.fftshift(np.fft.fftfreq(iq.size, 1/fs))
```

NPZ also stores carrier frequency and valid path delays in seconds.

## Signal and voltage conventions

Supply a callable `waveform(t_seconds)` returning complex baseband samples for
arbitrary absolute simulation times, including delayed times before a capture
block begins. This avoids rounding fractional propagation delays and avoids
artificial resets between blocks. Tones, chirps, or a pulse-shaped symbol source
can implement this interface. Scale the waveform to unit average squared
magnitude for `transmit_power_w` to represent average transmitted power. The
prototype does not automatically normalize arbitrary waveforms or resample a
finite input recording.

The receiver computes:

```text
v[n] = sqrt(R * Ptx) * sum_p h_p[n] * x(t0 + n/fs - tau_p) + noise[n]
```

`h_p[n]` is Sionna's baseband channel coefficient, including carrier phase,
antenna response, propagation loss, material effects, and local Doppler. Absolute
path delays are preserved with `normalize_delays=False`. Padded invalid paths
are removed. No received-power or delay normalization is applied.

The SISO receiver computes geometry/gain/delay once per capture, with at most
one reflection, and stores one complex coefficient and Doppler value per path.
Fast-time phase evolves analytically; no per-sample ray tracing or dense
paths-by-time coefficient export is needed. Native Sionna still shoots rays
to discover single-reflection candidates at depth one.

The complex voltage envelope uses the RMS convention:
`v_RF(t) = sqrt(2) * real(v(t) * exp(j*2*pi*fc*t))`, giving matched-load average
power `mean(abs(v)**2)/R`. This differs from a peak-envelope convention by
sqrt(2). Default impedance is 50 ohms. The basic `RFReceiver` does not model
ADC quantization, AGC, LO phase noise, oscillator offset, or analog filters.
The separate Distance2GoL FMCW model includes an IF filter and ADC quantization.

Optional circular complex Gaussian noise has variance
`R * k * T * fs * 10**(noise_figure_db/10)` volts squared. This assumes an ideal
receiver covering the full complex Nyquist bandwidth `B=fs`, with equal variance
in I and Q. `RFReceiver` retains a seeded random generator across captures.
Physical use of this approximation should keep signal bandwidth and Doppler
comfortably below the sample rate. The waveform-delay approximation freezes
envelope delays during each block; only carrier Doppler evolves within it.

## Attach to an AirSim vehicle

Start a ProjectAirSim Runtime or Unreal simulation separately. This workspace
does not contain a built simulator or Unreal Engine. The example loads the
specified scene, pauses it, reads ground-truth kinematics, moves the Sionna
receiver to the antenna pose, and captures one block:

```bash
.venv/bin/python examples/airsim_iq.py \
  --address 127.0.0.1 \
  --scene scene_drone_sensors.jsonc \
  --sim-config .deps/ProjectAirSim/client/python/example_user_scripts/sim_config/ \
  --robot Drone1 --tx-ned 100 0 -10 --output airsim_iq.npz
```

The scene is loaded and the simulator remains paused. With no `--rf-scene`,
radio propagation uses an empty free-space scene, regardless of AirSim's visual
environment. To model reflections or obstruction, supply `--rf-scene` with a
matching Mitsuba XML scene, including its meshes and RF material assignments.

The explicit RF scene convention is meters, x north, y west, z up, with the
same origin as AirSim. The conversion from AirSim NED is `(x, -y, -z)`, a proper
rotation that keeps a right-handed basis. Scene export must apply that same
transform and convert Unreal centimeters to meters. Body orientation is
converted to Sionna's Z-Y-X Euler angles. `offset_body_m` attaches an antenna
away from the robot origin; velocity includes the angular lever-arm term using
Fast Physics' body-frame angular velocity. The initial mount assumes aligned
antenna axes after conversion; independent antenna mount rotation is not exposed.

`AirSimRFBridge.capture()` requires a paused world and rejects a racing
timestamp snapshot. For repeated captures, the caller advances the steppable
AirSim clock between blocks and calls capture again. Geometry and channel are
recomputed at each epoch; Doppler phase is local to that block, since carrier
phase already comes from the geometry at its epoch. Keep blocks short enough
for frozen geometry and constant velocity to be reasonable. The caller must
check actual returned simulation times: physics step quantization can cause
gaps or overlaps. The prototype does not claim a continuous, gap-free stream.

## Validation and next integration work

Six receiver tests cover fractional delay, coherent multipath cancellation, matched-load
noise power, actual Sionna free-space loss/carrier phase/delay/Doppler, rotated
antenna mounts, and paused AirSim snapshot handling. The AirSim adapter has been
checked against the current source API and tested with a simulated client;
live AirSim capture has not been exercised because no simulator is running.
Six further pulsed radar tests cover the LFM sweep, monostatic radar equation,
round-trip phase/delay, target range recovery, two-way Doppler, timestamp
precision, and forwarding the drone's antenna state.
Eight FMCW tests cover the off-the-shelf profile, IF beat/power, antenna gain,
ADC clipping and quantization, and coherent frames. Total: 20 passing tests.

To complete the RF sensor integration:

1. Export and align the simulation meshes and assign RF materials; synchronize
   moving scene objects as well as the antenna.
2. Agree on transmitter waveform, carrier, bandwidth, antenna arrangement, and
   receiver electronics. Extend beyond the current one-TX/one-RX/one-antenna link.
3. Add native AirSim RF sensor configuration and publication of timestamped
   I/Q blocks, with simulation clock scheduling, buffering and transport limits.
4. Validate against a live simulator and reference RF cases before using it
   for signal-processing performance claims.

The radar prototype now supplies an LFM pulse and calibrated two-way point
target returns, and the hardware profile adds FMCW dechirping and IF/ADC
simulation. Mesh target scattering and multipath radar echoes remain future
extensions. AirSim's existing radar detections/tracks
do not encode the phase information needed to reconstruct those signals.
