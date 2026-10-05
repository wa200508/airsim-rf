# airsim-rf

A standalone RF simulation project using ProjectAirSim scene truth and Sionna
propagation, with radar/SDR models, complex I/Q rendering and receiver-worker
integration for AMS-GRA.

## How close are we to real time?

**The complete moving-scene RF simulation has not been demonstrated at real
time.** The latest qualified **100-transmitter/one-receiver renderer** is
**6.80× slower than real time on a P100** and **194× slower on the measured CPU**.
The much smaller one-/four-transmitter P100 cases meet the renderer's budget;
that does not qualify the complete scene-to-receiver service.

All rows below render **16,667 samples at 2 MS/s per receiver**, with **1,028
valid paths per directed link**, private arbitrary-waveform inputs, per-sample
narrowband Doppler, FP64/complex128, 32-tap interpolation, 100 µs declared delay
support and ±2,500 Hz physical Doppler. They use 120 updates/s and an **8.33 ms
service budget**. These are comparable continuous-I/Q renderer measurements.

<!-- BEGIN MEASURED RUNTIME TABLE -->

| Backend / TX → RX | Median window latency | p95 | Wall time / simulated time | Rendering cost for 10 simulated minutes |
| --- | ---: | ---: | ---: | ---: |
| [CPU, 100 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_100tx_1rx.json) | 1610.09 ms | 1700.36 ms | 194.06× | 32.34 h |
| [P100 CUDA, 100 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_100tx_1rx.json) | 56.17 ms | 59.65 ms | 6.80× | 68.00 min |
| [CPU, 4 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_4tx_1rx.json) | 78.49 ms | 84.62 ms | 9.45× | 94.49 min |
| [P100 CUDA, 4 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_4tx_1rx.json) | 5.68 ms | 6.05 ms | 0.69× | 6.87 min |
| [CPU, 1 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cpu_1tx_1rx.json) | 21.87 ms | 23.05 ms | 2.64× | 26.45 min |
| [P100 CUDA, 1 → 1](results/profiling/p100-basis-optimized-full-20261004/profiles/basis_cuda_1tx_1rx.json) | 5.51 ms | 6.14 ms | 0.67× | 6.69 min |

<!-- END MEASURED RUNTIME TABLE -->

Ratios and ten-minute costs use the **mean** of 30 warmed windows, not the
median or an algorithm speedup. Costs are extrapolated renderer work, not
measured ten-minute flights. A ratio below 1 means renderer throughput headroom.
The CPU host was **Ryzen 7 8700G**, with two FFT workers configured and no CPU
quota; its Radeon 780M was unused. The GPU was **P100-PCIE-16GB**. The current
CUDA renderer cannot use an AMD integrated GPU.

**Your 10-moving-TX/four-moving-RX case:** approximately **13–16 hours of CPU
rendering for ten simulated minutes** (about 78–94× slower), from a serial
40-link extrapolation. This is not a benchmark of that workload or the
unidentified “Ryzen 7100.” Random-flight propagation, AirSim, receiver DSP,
clock resampling, queues and recording add unmeasured work, so **complete
flight completion time remains unknown**. No unmeasured receiver parallelism
or transmitter sharing is credited.

For the original **100-TX/10-RX** goal, these GPU rows cover one receiver only.
One P100 processing ten receivers serially would imply about 11.33 hours of
rendering per ten simulated minutes; ten independent P100s could ideally
approach 68 minutes in parallel. Both are extrapolations, not fleet tests.
Current Sionna RT/Dr.Jit CUDA propagation is unsupported on P100; these results
qualify the separate CuPy renderer, not an integrated P100 simulation.

See [runtime context and historical comparisons](RUNTIME_STATUS.md) for included
stages, delivery latency, formulas and why older short-burst/channel-only numbers
appear faster. The [qualified report](results/profiling/p100-basis-optimized-full-20261004/REPORT.md)
and [optimization findings](results/profiling/p100-basis-optimized-full-20261004/FINDINGS.md)
preserve the raw evidence. Required CUDA qualification passed 76 tests.

## Run and explore

- [Home setup](REPRODUCE.md) and [container tests](CONTAINER.md).
- [P100 GPU collection](P100_BASIS_PROFILING.md): use the qualified warp
  configuration on `profiling/p100`:
  `bash scripts/run_p100_docker.sh --doppler-basis --projection warp --batch-links 100 --block-samples 2048 --run-id p100-basis-optimized-full`.
- [Doppler-basis rendering](DOPPLER_BASIS_FFT.md), [direct reference](DIRECT_PATH_RENDERING.md)
  and [historical batched rendering](BATCHED_RENDERING.md).
- [PlutoSDR-class COTS lab](COTS_SDR_LAB.md): moving emitters/listeners, receiver
  processing, recordings and SigMF export. Run
  `.venv/bin/python examples/pluto_esm_drones.py --output-dir recordings/pluto_esm`.
- [Distributed workers](DISTRIBUTED.md) and [AMS-GRA compatibility](AMS_GRA_COMPATIBILITY.md):
  architecture and CPU validation; live end-to-end runtime remains unqualified.
- [TX/RX-aware ground scattering](GROUND_SCATTERING.md), [DEM/waterfalls](TERRAIN_SCENARIO.md)
  and [focused terrain signatures](TERRAIN_SIGNATURE.md).
- [Historical small-radar timing](PERFORMANCE.md), [per-pulse model](PER_PULSE_RUNTIME.md),
  [single-bounce work](OPTIMIZATION.md), [network planning](NETWORK_RUNTIME.md),
  [GPU planning](GPU_RUNTIME.md), [older SDR timing](SDR_RUNTIME.md),
  [scaling analysis](SDR_COMPLEXITY.md), [affordable architecture study](AFFORDABLE_REALTIME_RF.md)
  and [independent-input optimization](INDEPENDENT_TX_OPTIMIZATION.md).
  These have different workloads or assumed GPU rates; use the summary above
  for current measured renderer capacity.

## Published environmental RF precedents

The [channel-to-I/Q implementation review](IQ_RENDERING_REFERENCES.md) traces
sample rendering in Sionna PHY, GNU Radio, NVIDIA's CUDA channel emulator,
ACHEM/CHEM and HermesPy, with citations to inspected code and reduced-rank
delay/Doppler research. It explains which implementations preserve per-sample
evolution, which freeze or simplify channels, and how they relate to our
projection bottleneck. SimART is compared as a scene/channel integration
platform; its inspected main runner evaluates link metrics rather than
rendering continuous receiver I/Q.

The [detailed comparison with published implementations](ENVIRONMENTAL_RF_REFERENCES.md)
documents how this project relates to MathWorks terrain-clutter I/Q examples,
Ansys STK/Perceive EM, Remcom WaveFarer, NVIDIA Sionna RT, RadarSimPy and RaySAR.
It includes a capability matrix, modeling assumptions, code and paper citations,
and a proposed independent validation sequence.

The closest terrain-to-I/Q examples are MathWorks'
[site-specific bistatic land clutter](https://www.mathworks.com/help/radar/ug/bistatic-clutter-part-3-simulating-site-specific-bistatic-land-clutter.html)
and RadarSimPy's
[Grand Canyon radar altimeter](https://radarsimx.com/2025/11/21/pulse-radar-altimeter-altitude/).
Ansys' [RF Channel Modeler](https://help.agi.com/stk/Content/comm/RFCMOverview.htm)
provides a close architectural precedent for a main scene simulator with a GPU
RF plugin. These references support the scene/channel/waveform approach;
our current ground model still needs calibrated backscatter, persistent
scatterer phase, slow-time correlation and coherent-I/Q convergence checks.
Our first-order mode also excludes target-plus-ground multiple-interaction paths.

## Getting started

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

For processing-step columns, **median ± standard deviation**, and a separate
**p95** table, see [the consolidated profiling breakdown](RUNTIME_STATUS.md#processing-steps-by-scenario-and-configuration).
