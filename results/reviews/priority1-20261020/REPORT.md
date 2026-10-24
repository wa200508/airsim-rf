# Priority 1 complete — 20 October 2026

> Documentation note: reported measurements are preserved. Local artifacts absent from this repository are shown as file references rather than download links.

**Passed: simulator and RF geometry match for static shared environments with
moving radios in the pinned stack.** The readiness list's first priority is
closed. No simulator rebuild was needed. Package consolidation remains priority 2;
no package was published, released or delivered.

## Acceptance evidence

[Machine closure audit](closure.json) passes all 20 checks. It verifies that
collision-probe and capture bundles have identical geometry content hashes,
checks every recorded geometry epoch, and independently reads every captured
sample with official SigMF 1.13.0. Focused regressions (`regressions.log`; local artifact, not checked in):
**50 passed, no skips**. These cover native USD instance proxies, centimetre units,
reflected winding, baked shear/reflection, bundle integrity, false-success mesh
loading, stale geometry and failure before sample generation.

| Saved criterion | Result and evidence |
| --- | --- |
| Shared scene geometry | OpenUSD triangles generate both Blocks GLB collision meshes and RF PLY/XML. The scene includes ground, an asymmetric sloping roof, rotated wall and obstruction screen. No packaged nonprimitive mesh assertion is needed. |
| Coordinates, transforms, materials and revisions | Explicit stage units/frame, affine local-to-NED transforms, corrected winding, declared RF properties and content hashes survive into bundles and per-window provenance. Visual materials do not supply RF properties. |
| Independent intersections | Combined-scene probes (`combined-mesh-probe/report.json`; local artifact, not checked in): **426 Unreal CPU LiDAR returns**, all four object identities, compared with CPU triangle intersections and Mitsuba CUDA rays. Maximum CPU error **0.0458 mm**, GPU error **0.0562 mm**, gate **1 mm**. Roof and screen distinguish the mesh from a box surrogate. |
| Moving turns, obstruction and first-order reflection in matching scenes | Combined capture (`combined/motion.json`; local artifact, not checked in): both fast-physics radios turn and move, with nonzero aperture mounts. All 40 direct-visibility predictions match independent shared-triangle intersections; the direct path disappears and returns while the ground reflection remains in every window. |
| Usable continuous I/Q | Combined CPU reference (`combined/diffuse-iq.json`; local artifact, not checked in): **960,000 complex samples**, 0.480 s at 2 MS/s, 12 ms windows, contiguous samples and no clipping. Whole I/Q NRMSE **0.2701%**, boundary **0.2708%**, gate **1%**. Both individual path transitions pass. Official SigMF reads all samples and agrees with the project's volts reader. |
| Object changes and caches | Old binding rejects a wall moved 1 m. A new complete revision and fresh RF scene match the moved wall to **0.000239 mm**; old-scene ray error is **500 mm**. Changing scenes rebuilds the plane cache (two builds); a fresh revision solver builds its own cache (one). See revision checks (`combined-mesh-probe/report.json`; local artifact, not checked in). |

The combined direct path disappears at **0.168 s** and returns at **0.264 s**,
relative to capture start. Individual transition I/Q errors are **0.2994%** and
**0.4227%**. A half-recording π phase-reset control (`combined/diffuse-negative-control.json`; local artifact, not checked in)
is rejected with **154.7%** whole-recording error and **155.7%** boundary error.

Two auxiliary captures provide separate controls:

| Capture | Signal / samples | Whole / boundary I/Q NRMSE | Additional evidence |
| --- | --- | --- | --- |
| Clear turning link (`turning/motion.json`; local artifact, not checked in) | 0.480 s / 960,000 | 0.2413% / 0.2421% | Independent mount checks (`turning/turning-mounts.json`; local artifact, not checked in): headings change 0.252 / 0.181 rad; max mount-velocity error 0.000538 m/s; direct length error 0.00771 mm; Doppler error 0.000582 Hz. |
| Straight-flight obstruction (`obstruction/motion.json`; local artifact, not checked in) | 4.800 s / 9,600,000 | 0.1123% / 0.1129% | All 400 shared-triangle visibility checks pass; direct path disappears at 0.144 s and returns at 0.360 s; each transition passes below 0.254%. |

Each capture's `bundle`, `trajectory.json`, `channels.json`, `inspection.json`,
`geometry-checks.json` and `capture/` retain source identity, kinematics, traced
paths, recording metadata and raw I/Q. Larger I/Q files remain ignored locally;
their SHA-256 identities are saved in `closure.json` and `inspection.json`.
Collision observations and revised bundles are saved in the three probe folders.
Final source hashes (`sources.json`; local artifact, not checked in) and copies under `sources/` preserve the
implementation. Run-specific probe script hashes are recorded in each report.

## Implementation and supported change policy

`airsim_rf.glb_geometry` writes deterministic GLB 2.0 with triangle indices and
flat normals. `generated:glb` bindings bake affine linear terms into vertices,
correct reflection winding, and retain translation on the actor. The pinned
Blocks loader's coordinate inverse is actor NED `(x,y,z)` → glTF `(x,-z,y)`;
independent runtime rays now qualify that previously inferred mapping.

Spawning requires a dedicated paused world, disables physics for environment
meshes, rejects existing names, and verifies inventory and pose/scale readback.
The upstream loader can return a requested name even after parse failure; the
adapter explicitly detects that case. Partial failures retain created actors
and report their names for inspection.

The policy is **static environment during a recording; explicit reload between
revisions**. The operator must not edit environment actors during capture.
Start/end pose and scale guards reject observed changes before I/Q generation.
For a pose/scale edit, obtain a paused complete snapshot and assign a new revision.
For topology/material edits, revise USD/profile and re-import. Export a new bundle,
place matching simulator geometry, and create a new RF scene, receiver and
recording. This discards geometry-dependent caches and continuous DSP state.
Generated meshes must be respawned when baked affine terms change. The old bundle
remains immutable. No hot reload or cross-revision I/Q stitching is supported.

Pose APIs cannot detect transient move-and-return motion, topology/material edits
or unlisted objects. Those are operator-controlled restrictions, not capabilities
established by the static guard. Continuous moving/deforming obstacles require a
separate implementation. See the [workflow](../../../docs/reference/openusd-workflow.md).

## Environment and reproduction

- Existing `airsim-rf:p100-modern-gpu` image; Tesla P100, Sionna RT 2.2.0,
  Mitsuba 3.8.0, explicit Pascal compatibility.
- OpenUSD 26.8 in `.deps/openusd-26.8`; SigMF 1.13.0 in `.deps/sigmf-interop`.
- Pinned Blocks Linux 1.0.1, null-RHI CPU collision mode. This does not qualify
  rendered cameras. The included scenes are offset 100 m above the original
  Blocks map, which is outside the declared RF domain.
- GPU checked before work: 263 MiB, 0% utilization. Unrelated `comfyui`,
  `gitlab-runner` and `immich_machine_learning` containers were left running.
- Only task-owned `airsim-rf-priority1-20261020` was started and stopped.
  Server log (`server.log`; local artifact, not checked in). No GPU allocation was reserved after qualification.

Start a dedicated Blocks server using [the documented command](../../../docs/reference/unreal-geometry.md).
From the repository root, choose a new `OUT` and run commands in the qualified
container environment (the shell function only supplies the existing runtime):

```bash
OUT=results/reviews/priority1-repeat
rfpython() {
  docker run --rm --gpus device=0 --network host --user 1000:1000 \
    --tmpfs /.drjit:rw,mode=1777 -e HOME=/tmp \
    -e PYTHONPATH=/work/repo/src:/work/repo/.deps/openusd-26.8:/work/repo/.deps/sigmf-interop \
    -v "$PWD:/work/repo" -w /work/repo \
    --entrypoint /opt/airsim-rf/.venv/bin/python airsim-rf:p100-modern-gpu "$@"
}
rfpython scripts/basis_launch.py scripts/qualify_usd_geometry.py \
  --pascal-compat --client-mesh --output "$OUT/mesh-probe"
rfpython scripts/basis_launch.py scripts/qualify_usd_geometry.py \
  --pascal-compat --client-mesh --screen --output "$OUT/final-mesh-probe"
rfpython scripts/basis_launch.py scripts/qualify_usd_geometry.py \
  --pascal-compat --client-mesh --turn-screen --output "$OUT/combined-mesh-probe"
rfpython scripts/basis_launch.py scripts/qualify_live_motion.py \
  --pascal-compat --shared-geometry shared-mesh-world \
  --turning-mounts --moving-receiver --reflection --output "$OUT/turning"
rfpython scripts/basis_launch.py scripts/qualify_live_motion.py \
  --pascal-compat --shared-geometry shared-mesh-screen \
  --moving-receiver --occlusion-test --duration-ms 4800 --output "$OUT/obstruction"
rfpython scripts/basis_launch.py scripts/qualify_live_motion.py \
  --pascal-compat --shared-geometry shared-mesh-turn-screen \
  --turning-mounts --moving-receiver --reflection --output "$OUT/combined"
for case in turning obstruction combined; do
  rfpython scripts/analyze_diffuse_iq.py "$OUT/$case"
done
rfpython scripts/analyze_turning_mounts.py "$OUT/turning"
rfpython scripts/analyze_diffuse_iq.py "$OUT/combined" --negative-control
rfpython scripts/qualify_geometry_closure.py "$OUT" --output "$OUT/closure.json"
rfpython -m pytest tests/test_geometry.py tests/test_live.py \
  tests/test_live_motion_analysis.py tests/test_diffuse_iq_analysis.py \
  tests/test_turning_mounts_analysis.py -q -rs
```

Analysis/regression commands are CPU-only and can omit `--gpus` and use
`--network none`. Stop the task-owned server after collecting its logs.
The initial regression run exposed a qualification-test manifest-key typo;
it was corrected to `scene_sha256`. The failed log is preserved, and the final
50-test run passes. No thresholds were relaxed.

## Limits retained after closure

This closes the shared-source geometry milestone in one pinned stack. It does
not extract arbitrary existing Unreal worlds; that remains a separate editor/
offline source adapter. All geometry in the declared shared scenes is selected,
but arbitrary unlisted map objects are not inventoried as RF surfaces.

The I/Q reference shares traced gains/delays/Dopplers, so it validates rendering,
filtering, quantization and recording, not independent Fresnel/material accuracy.
Continuous dynamic obstacles, calibrated RF properties, general terrain coverage,
rendered-camera equivalence, broader upstream-version support, long-run reliability
and the original fleet/rate/budget target remain outside this closure.
