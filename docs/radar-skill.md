[Documentation](README.md) · [Scenarios](../scenarios/README.md) · [Run dashboard](dashboard.md)

# Radar RF Skill is a separate project

The active radar skill is maintained at **[wa200508/Radar-skill](https://github.com/wa200508/Radar-skill)**.
It follows the [Direction Finding RF Skill separation](direction-finding-skill.md).
The skill selects the FMCW sweep, TX power, PRI, receive gate and gain, commands
a transceiver adapter, then consumes returned dechirped complex ADC I/Q.
It neither imports nor receives the simulator's target, RCS, flight or terrain.

| Repository | Owns |
|---|---|
| airsim-rf | Scenarios, native flight, shared geometry, first-order target/terrain scattering channel, FMCW/IF/noise/ADC acquisition, exact sample recording, dashboard observer |
| Radar-skill | Waveform and TX/RX control, range/Doppler FFT and candidate detector, active application, TCP/HTTP/result interfaces, neutral recording/replay adapters, tests and CPU container |

The actual detector lives in [processing.py](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/processing.py);
the service is [app.py](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/app.py).
Local `src/airsim_rf/skills/radar.py` is a legacy import/CLI shim.
It contains no radar algorithm or server implementation.
Simulation modules are forbidden from importing `radar_skill`, just as they
are forbidden from importing `df_skill`; the architecture audit enforces both.

## Pins and deployment

Pinned source: [9c9a57339784f87034e835f836076aaa8691f08a](https://github.com/wa200508/Radar-skill/tree/9c9a57339784f87034e835f836076aaa8691f08a).

```text
ghcr.io/wa200508/airsim-rf:radar-skill-sha-9c9a57339784f87034e835f836076aaa8691f08a
```

The scenario selects that immutable public image with `revision_policy: independent`.
Simulator and RF images still must match. The radar source pin lives in
`requirements-radar-skill.txt`; its receiver image/arguments/ports live in
`scenarios/mmwave-radar/scenario.json`. `Dockerfile.dashboard --target radar-skill`
and the old `airsim-rf:dashboard-radar-skill` tag are compatibility aliases of
the external image. They no longer build a second copy of the application.

CPU bootstrap installs the small external package without additional dependency
resolution for cross-repository acquisition/consumer tests and legacy imports.
For a Python installation needing the old namespace, use `pip install 'airsim-rf[radar]'`.
The old Python math/consumer imports remain compatible; the active CLI requires
`--mode` and `--radio-url`. Recorded input explicitly uses `--replay`.
The standalone skill requires NumPy only, without AirSim, Sionna, CUDA or DF-Skill.

Existing copied radar scenarios adopting the external image must also change
`revision_policy` from `matching` to `independent`; unrelated repositories
cannot share Git commit identifiers. This does not relax simulator/RF matching.

## Public image distribution

The release workflow [radar-skill.yml](../.github/workflows/radar-skill.yml)
builds the exact external Git commit using Radar-skill's own Dockerfile and
publishes the result in the existing public `airsim-rf` container package.
No AirSim source or second radar implementation is added to this build.
The OCI revision is the **radar source commit**, independently of the simulator
release commit. Offline qualification and a fresh anonymous Docker pull gate
publication. The skill repository tests its current checkout and smoke-tests
the pinned public release; this release workflow owns public publication.
The dashboard uses this path so no registry login is required.

When updating the radar version, update `requirements-radar-skill.txt`, the
scenario image, Dockerfile alias, and this release workflow's source revision
together. The unchanged numerical processing, interfaces and license are owned
by Radar-skill regardless of the registry package hosting its image.

## Transmit and receive

`scenarios/mmwave-radar/radar-mode.json` is the editable operating mode, selected
by `skill.mode` in scenario.json. It owns the waveform and electrical settings;
radios.json retains hardware antenna/filter/noise/ADC parameters and target RCS.
The launcher mounts only the mode and receiver metadata into the skill and starts
the acquisition container under network alias rf-acquisition. The skill sends
PUT /v1/configuration to http://rf-acquisition:8814, validates its configuration
identity and sends POST /v1/state enabling transmit and receive. The adapter
starts with both off; no source acquisition occurs before these commands.

The adapter in [radar_control.py](../src/airsim_rf/radar_control.py) is independent
of the skill implementation. It validates against modeled IWR1843/stream limits
and applies settings atomically at the next window. TX-off/RX-on produces no
radar target echoes while retaining noise/ADC behavior; RX-off pauses acquisition.
Status distinguishes accepted commands from the applied configuration/timestamp.
[The external client](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/transceiver.py)
uses the same [contract](https://github.com/wa200508/Radar-skill/blob/main/docs/transceiver-control.md)
for physical adapters. A vendor hardware driver is not included.

The skill's HTTP POST /transceiver/state forwards explicit TX/RX commands;
normal skill shutdown requests both off. Recorded-I/Q development uses `--replay`,
which rejects active-control options and never contacts a radio. Midstream
waveform/carrier/rate changes require a fresh session and matching metadata.
This HTTP API is not a claim of native AMS-GRA MEL/VITA transmit compatibility.

## Data and replay

The neutral TCP v2 and lossless cf32/SigMF formats are unchanged.
Both repository adapters preserve acquisition timestamps, gate gaps, channel
identity, volts and phase. [Radar-skill's replay adapter](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/sample_recording.py)
can stream an existing acquisition archive into a fresh unchanged consumer.
The standalone qualifier checks real TCP/HTTP/journals with all source packages
physically absent and requires identical radar results after recorded-I/Q replay.

The processing remains a single-channel, 64-chirp Hann-windowed FFT with an
18 dB median-map contrast detector. This extraction does not change the
algorithm, introduce CFAR performance claims, add gRPC acquisition control,
or alter the exaggerated demonstration RCS. See the [scenario/model guide](../scenarios/mmwave-radar/README.md)
and [I/Q development/replay guide](iq-replay.md).

## License

Apache-2.0, matching DF-Skill and the starter kit's public RF example license
selection. The new distribution preserves airsim-rf's original MIT notice.
airsim-rf itself remains MIT licensed.

## Skill-owned dashboard display

The skill's `display.py` defines its plots, labels, units, selectors and metric
bindings. `GET /display` exposes the description, and every timestamped result
carries it for synchronized live display and playback. See the
[RF Skill Display contract](skill-display.md) for extension instructions and the
[JSON schema](schemas/rf-skill-display-v1.schema.json). The dashboard's generic
renderer is `src/airsim_rf/dashboard_static/skill-display.js`; the observer replay
projection is `src/airsim_rf/skill_display.py`. Neither source nor simulator
selects a receiver algorithm or interprets its live result fields.

The simulator's [first-order radar model](radar-scattering.md) now combines
visible direct target echoes and area-normalized terrain clutter with an explicit
range cutoff. These settings and scene truth remain in the simulator; neither
this skill's control protocol nor its I/Q/FFT processing consumes them.


### Range–Doppler coordinates and color scales

The skill emits `power_db[range_index][doppler_index]`, `range_m` and signed
`doppler_khz`. Range increases upward; Doppler increases to the right. In the
maintained mode the full FFT axes span approximately 0–480 m and ±12.5 kHz.
Positive Doppler means receding motion. Apparent range retains FMCW coupling;
the candidate's range estimate separately corrects its Doppler contribution.
The color quantity is contrast relative to the current map median, not calibrated
SNR. Noise-detail, strong-echo and wide-dynamic-range presets change the view
only; samples and the 18 dB detector threshold stay unchanged. Finite weak-bin
values are preserved instead of clipping the result matrix at −20 dB.
Known earlier radar recordings receive an observer-only orientation projection;
their original matrices, archived I/Q and detections remain untouched. Values
already clipped when an old recording was created cannot be recovered by replay.
See the [clutter audit](../results/reviews/clutter-sampling-sweep-20261023/REPORT.md)
for absolute-power maps and paired noise/ADC comparisons.
