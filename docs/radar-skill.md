# Radar RF Skill is a separate project

The live radar receiver is maintained at **[wa200508/Radar-skill](https://github.com/wa200508/Radar-skill)**.
It follows the [Direction Finding RF Skill separation](direction-finding-skill.md).
The skill consumes dechirped complex ADC I/Q and receiver chirp/gate settings.
It neither imports nor receives the simulator's target, RCS, flight or terrain.

| Repository | Owns |
|---|---|
| airsim-rf | Scenarios, native flight, shared geometry, reciprocal radar point-target channel, FMCW/IF/noise/ADC acquisition, exact sample recording, dashboard observer |
| Radar-skill | Range/Doppler FFT and candidate detector, receiver application, TCP/HTTP/result interfaces, neutral recording/replay adapters, tests, CPU container and publication |

The actual detector lives in [processing.py](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/processing.py);
the service is [app.py](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/app.py).
Local `src/airsim_rf/skills/radar.py` is a legacy import/CLI shim.
It contains no radar algorithm or server implementation.
Simulation modules are forbidden from importing `radar_skill`, just as they
are forbidden from importing `df_skill`; the architecture audit enforces both.

## Pins and deployment

Pinned source: [ed36dffc23e716e24d7bf3ed084c0358d1d12e18](https://github.com/wa200508/Radar-skill/tree/ed36dffc23e716e24d7bf3ed084c0358d1d12e18).

```text
ghcr.io/wa200508/radar-skill:sha-ed36dffc23e716e24d7bf3ed084c0358d1d12e18
```

The scenario selects that immutable image with `revision_policy: independent`.
Simulator and RF images still must match. The radar source pin lives in
`requirements-radar-skill.txt`; its receiver image/arguments/ports live in
`scenarios/mmwave-radar/scenario.json`. `Dockerfile.dashboard --target radar-skill`
and the old `airsim-rf:dashboard-radar-skill` tag are compatibility aliases of
the external image. They no longer build a second copy of the application.

CPU bootstrap installs the small external package without additional dependency
resolution for cross-repository acquisition/consumer tests and legacy imports.
For a Python installation needing the old namespace, use `pip install 'airsim-rf[radar]'`.
The standalone skill requires NumPy only, without AirSim, Sionna, CUDA or DF-Skill.

Existing copied radar scenarios adopting the external image must also change
`revision_policy` from `matching` to `independent`; unrelated repositories
cannot share Git commit identifiers. This does not relax simulator/RF matching.

## Data and replay

The neutral TCP v2 and lossless cf32/SigMF formats are unchanged.
Both repository adapters preserve acquisition timestamps, gate gaps, channel
identity, volts and phase. [Radar-skill's replay adapter](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/sample_recording.py)
can stream an existing acquisition archive into a fresh unchanged consumer.
The standalone qualifier checks real TCP/HTTP/journals with all source packages
physically absent and requires identical radar results after recorded-I/Q replay.

The current skill remains a single-channel, 64-chirp Hann-windowed FFT with an
18 dB median-map contrast detector. This extraction does not change the
algorithm, introduce CFAR performance claims, add gRPC acquisition control,
or alter the exaggerated demonstration RCS. See the [scenario/model guide](../scenarios/mmwave-radar/README.md)
and [I/Q development/replay guide](iq-replay.md).

## License

Apache-2.0, matching DF-Skill and the starter kit's public RF example license
selection. The new distribution preserves airsim-rf's original MIT notice.
airsim-rf itself remains MIT licensed.
