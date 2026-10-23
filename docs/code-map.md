# Where to find the code

**Scenario choices are now data in one directory.** Start with
[scenarios/drone-orbit](../scenarios/drone-orbit), copy that folder, and launch
with `--scenario /path/to/your-copy`. See [scenario packages](scenarios.md).
The input package is independent of the containers and RF skill implementation.

## Find the scenario definition

| Question | Editable input |
| --- | --- |
| Which files make up the scenario? Which RF skill runs? | [scenario.json](../scenarios/drone-orbit/scenario.json): references, mission clocks/duration, skill image, argument list and internal ports. |
| Where are terrain heights and RF material assumptions? | [environment.json](../scenarios/drone-orbit/environment.json): explicit DEM grid, relative permittivity, conductivity and geodetic anchor. A neighbouring shared-geometry JSON can replace the heightfield. |
| Which actors move, and along what paths? | [flight.json](../scenarios/drone-orbit/flight.json): actor IDs, initial RF-coordinate poses, circle/waypoints/hold plans, speed and controller lookahead. |
| Which vehicle, controller and sensors? | [quadrotor.jsonc](../scenarios/drone-orbit/quadrotor.jsonc): complete vehicle definition. Camera capture settings come from the manifest. |
| What are the antennas, receiver laydown and calibration? | [radios.json](../scenarios/drone-orbit/radios.json): TX/RX element patterns, polarization, fixed array centers/yaw/spacing, ordered channel IDs, calibration and TX body mounts. |
| What signal, carrier, power and sample rate? | `radios.json` binds each transmitter to a [waveform definition](../scenarios/drone-orbit/waveform.json) and declares carrier/rate/power/bandwidth bounds. A waveform may reference arbitrary sampled `.npy` data in the package. |
| Which noise, filtering, ADC front end and propagation backend? | `radios.json.receiver_profile` and `.propagation`: device-model values, renderer, path solver, depth, scattering budget, delay/Doppler bounds and continuity. |
| Which chase camera and visual terrain color? | `scenario.json.camera` and `.appearance`: actor/sensor, distance, receiver-facing boom, image settings, labels, base color and emission. These do not set RF dielectric properties. |

The packaged example remains one QPSK transmitter on a 250 m left orbit at
25 m/s and RF-up altitude 200 m, two four-element 915 MHz ULAs, 2 MS/s, 120 ms
RF windows and an illustrative 800 m hills/valley heightfield. Those are example
input values, not assumptions embedded in the generic source loop. Its Pluto
front-end approximation and material constants remain uncalibrated assumptions.

## Follow the implementation

| Stage | Code and entry point |
| --- | --- |
| Validate related inputs/assets and freeze them | [scenario_definition.py](../src/airsim_rf/scenario_definition.py): `load()`, `asset()`, `snapshot()`, `fingerprints()`; standard library only. |
| Compile scene, vehicles and receiver metadata | [dashboard_scenario.py](../src/airsim_rf/dashboard_scenario.py): `prepare()`. Both Unreal and Sionna receive the same source triangles. |
| Generate independent source samples | `WaveformSource.window()` in that module; `emitters_for_window()` builds per-TX sampled buffers. |
| Compile a flight command | `flight_path()` handles circle, waypoints and hold without replacing actual simulator readback. |
| Create configured antennas and RF front end | `create_receiver()` constructs the same one-way `SDRNetworkReceiver` for live use and CPU qualification. |
| Advance the world and update moving transmitters | [dashboard_producer.py](../src/airsim_rf/dashboard_producer.py): `run()` loads `runtime.json`, controls the declared actors, reads actual poses/velocities and applies body mounts at each acquisition epoch. |
| Convert poses/body offsets to RF coordinates | [bridge.py](../src/airsim_rf/bridge.py): `mount_kinematics()`, north/east/down ↔ north/west/up. |
| Discover and validate paths | [single_bounce.py](../src/airsim_rf/single_bounce.py): direct/first-order planar specular adapter. [scattering.py](../src/airsim_rf/scattering.py) implements the different sampled scattering adapter. |
| Turn path gains/delays/Dopplers into samples | [sdr.py](../src/airsim_rf/sdr.py): `SDRNetworkReceiver.capture()` dispatches the configured renderer, receiver filtering/noise and ADC. The example selects [CudaDopplerBasisRenderer](../src/airsim_rf/research/doppler_basis_cuda.py). |
| Readable reference operator | [receiver.py](../src/airsim_rf/receiver.py): `synthesize_voltage()`; [CPU basis renderer](../src/airsim_rf/research/doppler_basis.py). |
| Shared-world integrity and direct-ray checks | [geometry.py](../src/airsim_rf/geometry.py), [geometry_sync.py](../src/airsim_rf/geometry_sync.py), [dashboard_geometry.py](../src/airsim_rf/dashboard_geometry.py). Diagnostics inspect actual paths rather than muting hidden links. |
| Camera boom and actual-frame labels | [dashboard_view.py](../src/airsim_rf/dashboard_view.py): `camera_frame()`, `relative_camera_pose()`, `camera_labels()`. Terrain visibility of a label is separate from a TX/RX radio link. |
| Neutral receiver stream and lockstep | [sample_stream.py](../src/airsim_rf/sample_stream.py), [dashboard_sync.py](../src/airsim_rf/dashboard_sync.py): acquisition timestamps, channels and generic window acknowledgements, without algorithm outputs. |
| Bulk I/Q recording and unchanged-skill replay | [sample_recording.py](../src/airsim_rf/sample_recording.py): `SampleRecordingWriter`, `iter_recorded_windows()`, `replay()`; NumPy and neutral transport only. See [capture/replay guide](iq-replay.md). |
| Generate portable GNU Radio starter graphs | [gnuradio_export.py](../src/airsim_rf/gnuradio_export.py): stock complex File Sources, shared vector pacer and per-channel DSP outputs. See [GNU Radio development](gnuradio.md). |
| Service lifecycle, scenario/skill wiring, replay and HTTP | [dashboard.py](../src/airsim_rf/dashboard.py); [standalone shell launcher](../scripts/run_dashboard.sh). |
| Plotting and playback presentation | [app.js](../src/airsim_rf/dashboard_static/app.js), [index.html](../src/airsim_rf/dashboard_static/index.html), [style.css](../src/airsim_rf/dashboard_static/style.css). The browser does not run MUSIC. |

Propagation gains and delays remain frozen within each RF window; per-path
narrowband Doppler evolves over its samples. The example does not enable diffuse
scattering, diffraction, refraction or higher-order reflections. An alternate
input must select a backend that actually implements its requested effects.

<a id="find-the-actual-music-algorithm"></a>

## Find the Direction Finding RF Skill

The application is now [DF-Skill app.py](https://github.com/wa200508/DF-Skill/blob/main/src/df_skill/app.py),
`DirectionFindingSkill.process()`. The old local imports are compatibility shims. It groups coherent channels, applies the supplied complex
calibration, and analyzes at most the first 24,000 samples per window. It uses
only post-ADC volts, timestamps and its own receiver metadata, with no source
waveform, emitter truth or paths.

Numerical receiver math lives in [DF-Skill music.py](https://github.com/wa200508/DF-Skill/blob/main/src/df_skill/music.py):

- `PhysicalULA.steering_vector()` uses physical element offsets and carrier.
- `estimate_bearing()` checks geometry/coherence, uses a covariance eigenvalue
  ratio gate of 5 and calls the external `doa_py.algorithm.music(num_signal=1)`.
  The live candidate searches −90°…+90° and rejects edge peaks.
- `spatial_spectrum()` evaluates −180°…+180° at 0.1° steps for the live circular
  plot. It normalizes the pseudospectrum to 0 dB; this curve alone is not a
  detection decision. A ULA's mirrored front/back lobes remain ambiguous.
- `frequency_psd()` computes two-sided voltage PSD independently for element 0
  at each site, supporting the receiver dropdown and stored waterfalls.

The algorithm itself is the installed open-source
[doa_py](https://github.com/zhiim/doa_py), pinned by
[requirements-tracking-lock.txt](../requirements-tracking-lock.txt). To inspect
that exact implementation in a running skill container:

```bash
docker ps --format '{{.Names}}'
docker exec YOUR_SKILL_CONTAINER python -c 'import inspect; from doa_py.algorithm import music; print(inspect.getfile(music)); print(inspect.getsource(music))'
```

Offline [aoa_tracking.py](../src/airsim_rf/aoa_tracking.py) adapts completed
recordings to [processing/tracking.py](../src/airsim_rf/processing/tracking.py),
adding bearing intersection and FilterPy tracking under its declared assumptions.
Held-out truth scoring lives in [evaluation/tracking.py](../src/airsim_rf/evaluation/tracking.py).
It is not part of the deployed skill. The gRPC control/status schema in
[src/airsim_rf/ams](../src/airsim_rf/ams) does not implement MUSIC.

## Inspect what a run actually used

Input defaults explain a new copy; the archive explains a particular run:

```text
recordings/dashboard/
  scenario-input/                 frozen package used for preparation
  runtime.json                    effective compiled source/vehicle/radio settings
  receiver-config.json            receiver-only metadata mounted into the skill
  sim_config/                     generated per-actor JSONC and steppable world
  bundle/                         shared geometry, materials, transforms and hashes
  replays/<run-id>/
    definition/                   complete scenario input snapshot
    deployment.json               configured tags, pinned image IDs, skill wiring
    scenario.json                 observer summary and input SHA-256 hashes
    frames/<sim-time-ns>.json      source telemetry/truth only
    results/<timestamp-ns>.json    independent RF application outputs
    camera/<frame-key>.jpg         actual recorded camera image and labels
    camera/<frame-key>.json        image time, geometry hash and label metadata
    iq/                           exact receiver samples and neutral replay metadata
```

The archive also retains raw receiver I/Q when `mission.record_iq` is enabled;
see [bulk capture and RF-skill replay](iq-replay.md). Source and
application journals meet only in [dashboard_recording.py](../src/airsim_rf/dashboard_recording.py).
See the [boundary guide](skill-boundary.md), [dashboard operations](dashboard.md),
[interfaces](interfaces.md) and [scenario-package schema](scenarios.md).

Other offline radar/FMCW examples and renderer benchmarks remain separate
workflows. Their point-target/LFM scenarios do not configure the live SDR
application, and historical reports/figures do not change input defaults.

## Radar scenario and catalog

The [scenario catalog](../scenarios/README.md) now also contains the
[77 GHz radar racetrack package](../scenarios/mmwave-radar/README.md). Its file
guide covers chirps, IF/ADC settings, antenna, passive target RCS, trajectory
and terrain masking. Source acquisition is in
[dashboard_radar.py](../src/airsim_rf/dashboard_radar.py) and
[fmcw.py](../src/airsim_rf/fmcw.py); independent receiver detection is in
[skills/radar.py](../src/airsim_rf/skills/radar.py). The preceding MUSIC map
continues to describe the direction-finding package.
