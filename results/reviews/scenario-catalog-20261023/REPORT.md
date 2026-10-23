# Selectable direction-finding and radar scenarios — 2026-10-23

## Delivered behavior

- A scenario-only catalog under `scenarios/`, discovered without importing any
  scientific/runtime dependency; ID/path selection, export, and dashboard selector.
- Existing direction-finding package retained, wired to the external DF-Skill.
- New independent `mmwave-radar` package: IWR1843BOOST-inspired 77 GHz FMCW,
  native moving radar and passive target; terrain-masked repeated racetrack.
- Separate NumPy-only radar skill container, receiver TCP v2 window ACK,
  HTTP/epoch results, range/range-rate dashboard and exact SigMF/GNU Radio archive.
- CI builds, qualifies and publishes `dashboard-radar-skill` alongside the
  simulator/RF images. The launcher still starts exactly three services per mission.

## Local evidence

| Check | Result |
|---|---|
| Focused Python regression suite in existing scientific CPU container | **77 passed, 6 skipped**, 17.64 s |
| Shipped JavaScript presentation/selection/radar tests | **9 passed** |
| Repository architecture audit | **Passed**, 73 modules / 218 Python files |
| Maintained Markdown files/fragments, now including scenario guides | **49 passed** |
| Actual independent radar Docker image build | **Passed** |
| Independent image, non-root, `--network none`, actual TCP + HTTP + journal | **Passed**, two windows / 80,000 complex samples; source/DF packages physically absent |
| Real Sionna radar acquisition → lossless archive → TCP → radar skill → result | **Passed** in CPU tests |
| Sionna LOS/specular solve vs shared terrain at clear/blocked positions | **Passed** in CPU tests |
| Planned radar route clearance and occlusion | **Passed**; minimum clearance >28 m, both clear and blocked segments |
| Planned relative range rate | Approximately **−19.96 to +18.81 m/s** over a lap |
| Target clearance | Approximately **9.42–10.61 m AGL**, constant absolute height |

The Python suite covered `test_radar_scenario.py`, `test_fmcw.py`,
`test_scenario_definition.py`, `test_dashboard.py`, `test_dashboard_container.py`,
`test_architecture_boundaries.py`, and `test_sample_recording.py`. Six optional
integration checks were skipped in that CPU image; these are not GPU-flight evidence.
The standalone qualifier also uses a separate synthetic receiver fixture to
verify negative range-rate sign and range/Doppler bin recovery without any source
implementation installed. It is not a hardware accuracy/performance measurement.

Initial container qualification caught unreadable copied files for UID 10001;
explicit readable COPY modes fixed that before the successful image qualification.
The builder also exhausted local VFS disk space; unused build cache was cleared
and the final build completed. Existing images and recordings were retained.

## Explicit limits

No full native rendered two-drone mission, CUDA/P100 performance or hardware
calibration was measured in this environment. The launcher's actual GPU, scene,
camera and initial-acquisition checks remain mandatory before Launch mission.
The 4 ms RF update is simulated time, not an achieved wall-clock throughput.

The radar is a reciprocal scalar point-target/specular-environment model; it
omits terrain backscatter clutter, diffuse scattering, diffraction, target mesh
scattering and rotor micro-Doppler. One reflection **per leg** permits two terrain
interactions in a complete echo. Actual poses/velocities are read every 4 ms and
extrapolated within that window. Default I/Q is post-IF-gain ADC volts with
explicit zero-filled ADC gate gaps. These choices, source citations, hardware
limits and assumed values are detailed in the
[scenario guide](../../../scenarios/mmwave-radar/README.md).
