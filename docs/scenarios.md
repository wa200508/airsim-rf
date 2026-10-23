# Editable scenario packages

A scenario is a **directory of input data**, independent of the containers and
RF skill code. The shipped example is [scenarios/drone-orbit](../scenarios/drone-orbit).
The same simulator/RF images compile and run a different package by changing
`--scenario`. Physical choices no longer live in the dashboard producer.

## Copy, edit, validate, run

From a checkout:

```bash
cp -r scenarios/drone-orbit ~/my-rf-scenario
# Edit the neighbouring JSON/JSONC files in ~/my-rf-scenario.
python3 scripts/launch_dashboard.py --scenario ~/my-rf-scenario --check-scenario
bash scripts/run_dashboard.sh --scenario ~/my-rf-scenario --open
```

The Python validator uses only the standard library and does not contact Docker,
a GPU or a simulator. Geometry and finite waveform coverage checks also run during preparation.
GPU/model execution is checked by the initial scene-derived acquisition before
Launch mission becomes available.

For a downloaded standalone launcher:

```bash
bash run_dashboard.sh --export-scenario ~/my-rf-scenario
# Edit that directory, then:
bash run_dashboard.sh --scenario ~/my-rf-scenario --open
```

Its first use pulls the RF image to extract the launcher and default input data.
An existing cache supports replay without Docker. No image build is needed to
change a scenario. A launch without `--scenario` uses the packaged example.
`--duration 12` overrides only that run's duration; `runtime.json` records the
effective value. **Prepare services** reloads edits for the next mission; an
already prepared mission retains its frozen inputs.
`mission.record_iq` defaults to `true`: bulk samples are saved independently of
video and skill results. Set it to `false` for a run without bulk capture; see
[I/Q capture, replay and disk requirements](iq-replay.md).

## Package layout and ownership

```text
my-rf-scenario/
  scenario.json              entry point, clocks, camera, appearance, skill wiring
  environment.json           DEM or reference to shared geometry; materials, anchor
  flight.json                actors, vehicles, initial poses and flight plans
  quadrotor.jsonc             complete editable vehicle/controller/sensor definition
  radios.json                TX/RX bindings, arrays, carrier/rate, front end and solver
  waveform.json              configurable QPSK or sampled waveform definition
  measured.npy               optional arbitrary sampled waveform
  ...                        additional local geometry, vehicles and waveform files
```

File names other than `scenario.json` are references and can be changed. Paths
are relative to the package root and must stay inside it. Keep assets in this
folder or its subdirectories, so copying it is sufficient for reproduction.
[The example's file guide](../scenarios/drone-orbit/README.md) identifies the edit
points. The loader is [scenario_definition.py](../src/airsim_rf/scenario_definition.py);
the compiler/adapters are [dashboard_scenario.py](../src/airsim_rf/dashboard_scenario.py).

Inputs use RF north/west/up metres and positive yaw toward west. Body-mounted
TX offsets use body forward/right/down metres. Receiver `altitude_reference`
chooses `agl` above the declared heightfield or `absolute` RF-up coordinates.
Array yaw rotates both the element layout and antenna pattern. Different
transmitters have independent waveform buffers and power settings.

`environment.json` supports:

- `type: heightfield`: `x_m`, `y_m`, and `heights_m[y][x]`, explicit `materials`,
  the terrain's `material`, `scene_id`, `revision` and `geodetic_anchor`.
- `type: geometry`: `file` references a neighbouring validated
  [shared-geometry document](geometry-contract.md), plus `geodetic_anchor`. All
  its objects are exported to both Sionna and Unreal using their transforms.
  Use absolute receiver heights when there is no heightfield.

Each `flight.json` actor names its own vehicle file, initial `position_rf_m`,
`yaw_deg`, `settle_s` and `flight`. Supported flight types are:

- `circle`: `center_rf_m`, `radius_m`, `speed_m_s`, `direction` (`left`/`right`),
  `waypoint_step_deg`, `lookahead_m`, `adaptive_lookahead`. Start on the circle.
- `waypoints`: `points_rf_m`, `speed_m_s`, `lookahead_m`, `adaptive_lookahead`,
  optional `repeat`. A non-repeated route ends at its final point.
- `hold`: hold the declared altitude with zero horizontal velocity.

Add transmitter actors and bind them by ID in `radios.json`. Current dashboard
receiver sites are fixed coherent arrays; moving-receiver capture exists in the
separate [live API](live-workflow.md) and is not implicitly enabled by this schema.
Vehicle configurations must support the native flight-control API used by this
runtime. The first TX supplies the dashboard's direct-path diagnostic; received
I/Q includes **all** configured transmitters. The bundled MUSIC application
still assumes one dominant arrival per site even if a multi-emitter scene is run.

`waveform.json` uses the example's QPSK fields or `type: samples` with a relative
`file` containing finite 1-D real/complex NumPy samples. Sample rate comes from
`radios.json`. Amplitudes are retained, not normalized. File onset is mission
origin with zero prehistory; its sample count must cover the rounded acquisition
duration plus 32 lookahead samples. A source is never silently repeated or
truncated. Set distinct source files or QPSK seeds when independent signals are
wanted. Radar/comms/ESM waveforms can be supplied as samples without making the
simulator aware of the receiving algorithm.

## Connect a different RF skill

`scenario.json.skill` selects the consumer image, command arguments, internal
ports and contract. For example:

```json
{
  "kind": "custom",
  "contract": "receiver-tcp-v2",
  "image": "ghcr.io/your-team/your-rf-skill:1",
  "revision_policy": "independent",
  "command": ["--receiver-config", "/config/arrays.json", "--results", "/results"],
  "ports": {"iq": 9911, "http": 9912, "control": null}
}
```

The launcher maps published host ports to those internal ports and connects the
RF source to the chosen I/Q port. It supplies `RF_IQ_PORT`, `RF_HTTP_PORT`,
optional `RF_CONTROL_PORT`, `RF_RECEIVER_CONFIG` and `RF_RESULTS_DIR` environment
variables. The bundled skill honors the port variables; a custom image may
use them or its own declared command arguments. Your image supplies its own entrypoint; the
listed command is its argument vector. A null control port publishes no gRPC
endpoint. `--skill-image` can override the configured image for one invocation.

The consumer must implement the [neutral TCP v2 sample/window-commit contract](iq-stream.md),
return HTTP 200 on `/health` with `complete_windows >= 1` after processing the
initial startup window, and atomically publish `/results/<timestamp_ns>.json`
for synchronized replay. A minimal result contains its neutral `timestamp_ns`;
common counters, receiver spectra and algorithm-specific measurements are
optional. The existing GUI understands its common spectrum/counter fields;
new kinds of algorithm visualization need an observer renderer.

The bundled `kind: music` requires two ULAs with at least three ordered,
calibrated, at-most-half-wavelength-spaced channels per site. Choose `custom`
for other consumer layouts. `revision_policy: matching` enforces the bundled
skill's common source revision with the RF/simulator images. `independent`
permits an independently versioned consumer; simulator and RF images must still
match. Every role is pinned to the image ID actually inspected after pulling.

The skill gets only read-only receiver metadata at `/config/arrays.json` and a
writable results directory. The scenario directory, emitter waveforms, terrain
and source truth are not mounted into it. Changing scenario/skill wiring does
not bypass the [simulation/skill boundary](skill-boundary.md). These are the
project's existing deployment/data contracts, not newly claimed native AMS-GRA
MEL/VITA conformance.

## Reproducibility and generated outputs

Preparation takes a snapshot before image selection and uses that snapshot for
the entire mission. With the default output directory:

```text
recordings/dashboard/
  scenario-input/                  frozen complete input package for preparation
  runtime.json                     effective compiled source configuration
  arrays.json                      resolved absolute receiver layout
  receiver-config.json             receiver-only configuration mounted into skill
  sim_config/                      generated per-actor vehicle and world inputs
  bundle/                          shared Sionna/Unreal geometry
  replays/<run-id>/
    definition/                    this mission's complete input snapshot
    deployment.json                configured tags, pinned image IDs, skill wiring
    scenario.json                  observer summary including input SHA-256 hashes
    frames/ camera/ results/       independent source, video and application outputs
    iq/                            lossless receiver I/Q and neutral replay metadata
```

Edit the input package, not generated `runtime.json` or the run directory.
Historical recordings keep their own definitions when another mission is
prepared. Replay needs no original input path, Docker or GPU.

The reusable dashboard still uses its qualified NVIDIA/ProjectAirSim deployment
and supported propagation/receiver models. JSON configures their capabilities;
a new solver, hardware impairment model or transport requires a runtime adapter.
That is separate from changing terrain, vehicle data, waveform samples, flight
paths, radios or a compatible RF consumer. See the
[scenario-package qualification](../results/reviews/scenario-packages-20261023/REPORT.md).
