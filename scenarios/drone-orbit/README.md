# Editable drone-orbit scenario

Copy **this whole directory**, edit the files, then point the same published
containers at the copy:

```bash
cp -r scenarios/drone-orbit ~/my-rf-scenario
python3 scripts/launch_dashboard.py --scenario ~/my-rf-scenario --check-scenario
bash scripts/run_dashboard.sh --scenario ~/my-rf-scenario --open
```

No image rebuild is needed. For a standalone launcher, export its packaged example:

```bash
bash run_dashboard.sh --export-scenario ~/my-rf-scenario
bash run_dashboard.sh --scenario ~/my-rf-scenario --open
```

| File | Edit here |
| --- | --- |
| `scenario.json` | References to neighbours; mission clocks/duration, camera, visual appearance, skill image/arguments/ports and compatibility policy. |
| `environment.json` | Explicit DEM coordinates/heights and material constants. RF and Unreal use these same triangles. You may instead reference a neighbouring shared-geometry JSON with `type: geometry`. |
| `flight.json` | Actors, vehicle files, RF-coordinate starting positions/yaw and circle/waypoints/hold flight plans. Add actors here and bind transmitters to them in radios. |
| `quadrotor.jsonc` | Full vehicle/controller/sensor definition. Camera capture interval, resolution and FOV are set by `scenario.json`; the remaining physical configuration stays here. |
| `radios.json` | Carrier/rate, transmitter bindings/mounts/powers/waveform files, antenna patterns, fixed receiver arrays/calibration, front-end profile and propagation/renderer settings. |
| `waveform.json` | QPSK generation parameters. Alternatively `{"type":"samples","file":"your_iq.npy"}` loads any finite 1-D real/complex source samples at the declared sample rate. Include mission coverage plus 32 lookahead samples. Files are never silently looped. |

All asset paths are relative to this directory and must remain inside it. Input
RF coordinates are north/west/up in metres; yaw is positive toward west.
Receiver heights use `altitude_reference: agl` above the heightfield or `absolute`
for RF-up coordinates. Array yaw rotates both element positions and element
patterns. The bundled MUSIC skill requires two coherent ULAs; choose a compatible
custom consumer for other layouts. Per-device source buffers remain independent.

The vehicle data derives from ProjectAirSim's pinned
`robot_quadrotor_fastphysics_sensors.jsonc` at commit
`cfb865f29f255b15ef28ec8fdcfaa01a6b66497f`, with this example's controller/camera
settings. The neighbouring upstream license applies to that data. The heightfield
is the project's original illustrative hills/valley frozen as editable data;
it is not a measured DEM. Dielectrics are uncalibrated assumptions.

See [scenario packages](../../docs/scenarios.md) for the schema, custom skills,
run snapshots and supported runtime capabilities.


## Low flight and demonstration noise

The 250 m orbit now follows the shared terrain with 20 m minimum planned
clearance, a 20% ascent/descent grade bound and a nominal absolute floor of
120 m RF-up. Edit `flight.json` → `flight.terrain_clearance_m` and
`flight.max_vertical_grade`. The native controller follows the compiled 3-D
route; it does not fly the nominal 120 m plane through the terrain.

Edit `radios.json` → `receiver_profile.noise_power_offset_db`. The demo starts
at −25 dB noise power relative to the modeled receiver; **0 restores the original
noise model**. Thermal noise remains enabled, and the ADC stays active.
This is a visibility adjustment, not measured PlutoSDR noise performance.
See [all tuning controls](../../docs/demo-tuning.md) and the
[source/ADC verification](../../results/reviews/low-terrain-demo-20261024/REPORT.md).
