# Shared terrain, occlusion and display timing — 2026-10-22

The RF solver was already rejecting direct paths behind the current DEM, but
the dashboard independently displayed the newest image, producer state and
skill diagnostics. A real image was observed with timestamp 0.36 s when the
world had reached 1.44 s. Radio annotations also used the latest pose rather
than the image's capture pose. The inset included a hard-coded orange screen
that was absent from the hills-and-valleys scene.

The implementation now:

- Uses the same generated DEM in AirSim and Sionna, removes native Blocks
  physical scenery from the dedicated dashboard world, verifies loaded Sionna
  vertices/topology, and checks the AirSim terrain transform at each RF epoch.
- Checks actual Sionna direct-path counts against independent shared-triangle
  intersections for every antenna element. A disagreement fails capture.
- Reports direct elements and reflected paths separately from MUSIC and received
  power. It never infers a direct path from a detection or turns off all echoes
  merely because a direct ray is blocked.
- Retains 128 skill diagnostic snapshots and publishes timestamp-addressed image
  files. Image, RF truth and skill plots use a pair within 60 ms; a new image
  waits for its RF diagnostics instead of being paired with a previous window.
  The measured time offset and display lag remain visible. Transport counters
  continue to report current ingress independently.
- Places a map of the actual DEM below the camera, with actual receiver positions,
  sight lines and terrain intersection markers. The invented orange screen and
  projected labels that could show through terrain are removed. Waterfall and
  camera/RF labels share the mission-relative T+ origin.

No terrain heights, flight altitude, path, source power, waveform, receiver noise,
reflection order or detection thresholds were changed to force an outage. The
current model uses opaque terrain, direct visibility and first-order specular
reflections. Diffuse scattering, diffraction and transmission remain disabled.
Vehicle bodies and receiver beacons remain outside the ideal point-antenna RF
model. Camera occlusion and a receiver-to-transmitter sight line are different
geometric questions.

Validation:

| Check | Result | Scope |
|---|---|---|
| [Unreal/Sionna terrain alignment](scene-alignment.json) | Passed | Actual packaged Unreal with software Vulkan, independent CPU LiDAR and loaded Sionna mesh |
| Blocked-link and elevation LiDAR probes | Maximum error **0.850 mm** | Five blocked/downward probe groups, 12 returned rays each; two clear receiver-ray groups with no earlier environmental hit |
| Sionna vertex agreement | Maximum error **0.00760 mm** | Loaded PLY topology and vertices compared with shared source geometry |
| [Orbit RF scan](orbit-rf-check.json) | **192 element links**, all agree | 24 static circle positions × eight actual antenna elements, Sionna LLVM, noise disabled, 128-sample tone captures |
| Shadow sector in sampled orbit | 20 blocked element links; zero direct paths | Both sites blocked at 210° and 225°; one site blocked at 240°; sampled angles are not exact transition boundaries |
| Echo-only I/Q regression | Passed | A finite wall blocks the 4 m direct route while a 7.21 m one-bounce route produces nonzero ADC I/Q with noise disabled |
| Timestamp/HTTP regressions | Passed | Delayed image selects older matching diagnostics, future/unavailable diagnostics are rejected, image URL serves its requested immutable frame |
| Supported CPU suite | **299 passed, 169 skipped**, three signal subtests passed | Skips include unavailable optional dependencies and GPU backends |
| Additional dashboard tests in legacy GPU runtime, on CPU | **40 passed** | Includes retained skill snapshots and received-power diagnostics with tracking dependencies installed |
| Browser layout | Passed | Desktop/mobile fixture, no JavaScript errors, map outside camera, correct path-count and time-offset labels; not a physical mission |

The full CPU suite must use the supported CPU image. An exploratory full-suite
run under the legacy Pascal image's LLVM backend had five native-sampler tests
fail because Dr.Jit 1.3.1 lacks `JitBackend.Metal`; the CUDA producer already uses
the explicit Pascal compatibility shim. Those failures were outside the changed
dashboard path. The supported CPU image uses the pinned modern CPU dependencies
and passed the full suite above. This work does not claim a new CUDA/P100 or full
moving GPU mission qualification.

The LiDAR result establishes sampled collision-surface agreement, rather than a
pixel-color comparison. No RF dielectric properties are inferred from visual
colors. The RF scan uses isolated ideal orbit poses, not a newly measured native
flight trajectory, and is not a runtime benchmark. In this particular DEM the
sampled fully shadowed links have no retained first-order specular echoes; they
therefore receive noise in the normal noise-enabled dashboard. The separate wall
regression verifies that valid echoes survive when they do exist.

Reproduce:

```bash
# In the supported CPU test image:
python -m pytest tests/test_dashboard_scene.py tests/test_dashboard_container.py -q

# In the GPU dashboard image, without requiring an NVIDIA device:
python scripts/qualify_dashboard_camera.py --output-dir /work/scene-check
```

The live check uses [the shared-scene probes](../../../scripts/dashboard_scene_probes.py)
and runs in CI before image publication. Initial native-map cleanup can take
several minutes on software rendering; the launcher default timeout is 600 s.
