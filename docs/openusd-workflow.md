# OpenUSD shared-scene workflow

**Priority 1 complete for static shared environments with moving radios, 20 October 2026.**
The [closure report](../results/reviews/priority1-20261020/REPORT.md) qualifies
nonprimitive USD triangles sent to Blocks as generated GLB collision meshes,
independent CPU/GPU intersections, turning radios, obstruction and first-order
reflections together, recorded I/Q, and explicit geometry revision boundaries.
The qualified stack is OpenUSD 26.8, pinned Blocks 1.0.1, Sionna RT 2.2.0 and
Mitsuba 3.8.0 on the P100 compatibility stack. Other versions need qualification.

The primary users are RF/SDR engineers and algorithm developers. Prepare one
scene, explicitly assign RF properties, derive simulator placement and RF meshes
from it, then consume I/Q through the existing recorder. OpenUSD is the asset
standard; AMS GRA RF MEL, OMS/UCI and DIS remain separate integration boundaries.

## What is included

- `airsim_rf.usd_geometry`: optional OpenUSD importer using `pxr` composition.
- `airsim_rf.geometry`: validated normalized snapshot and PLY/XML export bundle.
- `airsim_rf.geometry_sync`: offline placement planning, explicit spawning,
  paused actor readback and a static-scene capture guard.
- [Original shared-box scene](../examples/geometry/shared-world.usda) and
  [RF profile](../examples/geometry/shared-world.rf.json): ground slab, building
  and rotated wall. All three use explicit triangles and a centered box asset.
- [Nonprimitive shared scene](../examples/geometry/shared-mesh-world.usda) and
  [profile](../examples/geometry/shared-mesh-world.rf.json), with a sloping roof
  and rotated wall. The [combined turning scene](../examples/geometry/shared-mesh-turn-screen.usda)
  adds an elevated narrow obstruction; its matching `.rf.json` profile selects
  every surface. The separate `shared-mesh-screen` scene covers straight flight.
- Live recorder opt-in through `geometry_bundle`, with per-window geometry
  provenance and shape merging disabled.

## 1. Prepare assets and RF profile

The example scene uses metres, Z up, X north and Y west. The profile explicitly
maps this into NED; the RF exporter maps NED into the project's north/west/up
frame. For a differently oriented source, change the profile rather than guessing
the transform from an up-axis flag. Its geodetic anchor is WGS-84 ellipsoid height.
Configure AirSim's world origin consistently; this importer does not rewrite
the simulator's geographic origin or transform a world already running elsewhere.

Each profile object provides:

- A stable ID and exact USD prim path, with one explicit RF material assignment.
- A simulator object name and either a packaged asset path or `generated:glb`.
- `local_to_actor_m`: maps the USD mesh's local coordinate numbers into the
  actor's unscaled local metre coordinates, including pivot and axis conversion.
- Written asset provenance: identify the matching packaged mesh and collision
  representation. Readback of pose/scale cannot establish triangle equivalence.
- Optional DIS entity, OMS system/subsystem and RF aperture identities. These
  are mapping metadata, not newly implemented network publishers. Static walls
  normally have no such network identities.

The original box example expects Unreal's packaged `Cube` to be a centered one-metre box with
matching collision geometry. Confirm this for the selected server build. The
profile's local frame conversion produces the scale/rotation/translation used by
the placement API. Unsupported actor shear or reflected scale is rejected.

For a shared nonprimitive asset, set `simulator.asset_path` to `generated:glb`.
The placement adapter bakes each selected mesh's affine linear transform into
its vertices and keeps translation on a unit-scale, unrotated actor. This supports
nonuniform scale, shear and reflected transforms without asking Unreal actor
transforms to represent them. Triangle winding is corrected for reflections.
`local_to_actor_m` remains required by profile v1 but is derived from the mesh
transform for this route; it is used directly only for packaged assets.

`airsim_rf.glb_geometry` encodes a self-contained glTF 2.0 binary mesh in metres,
with flat normals and no external buffers/textures. The pinned Blocks adapter
uses actor-local NED `(x,y,z)` → glTF `(x,-z,y)`. OpenUSD remains the source
standard; GLB is the simulator adapter output. Visual material defaults have no
RF meaning. Explicit RF properties come only from the RF profile.
The spawn routine checks actor inventory/readback because the upstream loader
can return a name when mesh parsing fails. Independent collision qualification
is still required for adapter upgrades.

Importing an existing Unreal scene still requires an editor/offline USD export
of the intended collision or render geometry and a corresponding profile. This
implementation cannot extract arbitrary triangles through the World pose API.
Do not treat all visible objects in a running environment as automatically covered.

## 2. Export offline

The `geometry` package extra declares `usd-core>=24.8,<27`. This is a candidate
dependency range, **not a tested version matrix**. OpenUSD 26.8 was installed
in an isolated dependency directory and used for qualification. Use an isolated
CPU environment with NumPy/SciPy and the OpenUSD Python bindings.

```bash
PYTHONPATH=src python -m airsim_rf.usd_geometry \
  examples/geometry/shared-mesh-world.usda \
  --profile examples/geometry/shared-mesh-world.rf.json \
  --output recordings/shared-world-bundle

PYTHONPATH=src python -m airsim_rf.geometry_sync \
  recordings/shared-world-bundle \
  --output recordings/shared-world-placement.json
```

Installed entry points are `airsim-rf-import-usd` and
`airsim-rf-geometry-plan`. Both are offline; neither imports Sionna, Mitsuba,
CuPy or ProjectAirSim. They do not require a GPU or server. Output locations must
be new, protecting previous exports from accidental replacement.

The bundle contains:

| File | Purpose |
| --- | --- |
| `geometry.json` | Validated internal snapshot: local triangles and local-to-NED matrices |
| `scene.xml`, object `.ply` files | Current Sionna/Mitsuba adapter output in RF world coordinates |
| `bindings.json` | USD-to-simulator/network identities and geodetic anchor |
| `source.json` | USD version, source layer/profile hashes, units, axis and explicit exclusions |
| `manifest.json` | File hashes, geometry identity, object names and load policy; written last |

`read_bundle()` checks the manifest and hashes before consumption. Hashes detect
changed files; they are not a signature or evidence of physical accuracy.
An interrupted export without a manifest is incomplete. Re-export a new bundle
for geometry, material or transform changes; do not patch individual output files.

## 3. Place or bind objects in a dedicated simulator

No recorder command implicitly spawns, moves or deletes actors. Either prepare
the matching actors in the simulator editor, or explicitly apply a placement
plan using an already-created, dedicated paused World handle:

```python
from airsim_rf.geometry import read_bundle
from airsim_rf.geometry_sync import (
    AirSimGeometryBinding, placement_plan, spawn_placements,
)

geometry, manifest, bindings = read_bundle("recordings/shared-world-bundle")
plan = placement_plan(geometry, bindings)  # offline
# Only in a dedicated paused world whose lifecycle you own:
created_names = spawn_placements(world, plan)
binding = AirSimGeometryBinding(geometry, bindings)
report = binding.require_static_match(world, int(world.get_sim_time()))
```

The spawn API disables physics on these environment objects. Name collisions
and partial failures raise errors with the created names; it never silently
overwrites actors or removes them during cleanup. It does not connect to, load,
pause or advance a world itself. The caller owns those lifecycle operations.

Readback obtains actual pose and scale from each named actor at one paused
epoch and compares every transformed mesh vertex to the exported snapshot.
The default tolerance is 10 micrometres, a provisional configurable API value,
not a measured guarantee for Unreal's precision. Change tolerances deliberately
and record them when qualifying a particular environment scale.

## 4. Opt into the live recorder guard

Add these keys to the existing live configuration, relative to that file:

```json
{
  "geometry_bundle": "shared-world-bundle",
  "rf_scene": "shared-world-bundle/scene.xml"
}
```

By default `geometry_placement` is `"existing"`: actors must be part of the
loaded simulator scene. The live runner loads its configured AirSim scene, which
can discard objects spawned by an earlier client. For these shared examples,
explicitly set `"geometry_placement": "spawn"` to apply the bundle's placement
plan **after** loading and pausing that scene. Use this only on a dedicated server
you own; it changes the simulator world. It never overwrites colliding names or
automatically removes objects. The lower-level `record()` API can instead use an
already-prepared World without loading it again.

The complete live configuration still needs its normal server, simulator,
radio, source waveform and receiver settings. The recorder checks bundle
integrity, keeps individual Sionna object IDs, and verifies actor poses/scales
before capture. Each radio snapshot checks the environment at the same paused
epoch; an additional check after physics advancement rejects a changed static
environment before generating samples. Recorded rows retain the starting epoch's
geometry identity and maximum vertex-placement errors.

Legacy configurations without `geometry_bundle` keep their existing workflow.
No geometry-match guarantee is inferred for them. All live modes still use the
existing GPU-backed RF renderer; only preparation/import/plan work is CPU-only.

## Scope of profile v1

Supported: local file-backed composed USD layers, triangle Mesh prims, static
affine transforms, native instance proxies, explicit handedness correction and
one RF material per selected mesh. Every active geometry prim needs an explicit
selection or exclusion reason. Visual visibility and visual material shaders
do not determine RF participation or material properties.

Rejected: non-triangle faces, subdivision surfaces, mesh holes, selected analytic
primitives/point instancers, skinning, time-sampled attributes on selected meshes
or their ancestors, resolver-only layers and unsupported actor transforms.
Triangulate/bake explicitly upstream. Multi-material meshes need splitting and
separate simulator objects under this first one-object/one-mesh binding profile.

The current live path supports **static environment geometry with moving radios**.
Readback can produce a new complete geometry snapshot, but automatic moving-
obstacle updates inside Sionna are not implemented. Start/end checks cannot
detect an object that moves and returns within a physics interval. Asset
topology changes, collisions different from the declared asset, or unlisted
runtime objects also cannot be discovered through pose/scale readback.

## Geometry changes and cache lifetime

The supported policy is a **static environment during each recording**. The
operator owns the dedicated world and must not issue environment edits during
capture. Radios move and turn normally. Pose/scale guards run at both endpoints
of every physics interval and reject a stale actor before I/Q generation.
They cannot detect transient move-and-return motion, topology/material edits or
unlisted objects; continuously moving/deforming obstacles are unsupported.

Change an environment at a recording boundary:

1. Stop capture. For pose/scale edits, use `binding.snapshot(world)` while paused
   to obtain a complete observed document, and assign a new nonempty `revision`.
   For topology/material edits, revise the source USD/profile and re-import it.
2. Export a **new directory** with `export_sionna_geometry`, including matching
   bindings and provenance. Keep the prior bundle immutable. The content hash
   changes with geometry, transforms, revision or RF material definitions.
3. Start a new recording with that bundle. Reload the simulator scene and spawn
   the revised shared meshes, or explicitly prepare matching existing actors.
   Generated meshes bake affine terms, so respawn them when those terms change.
4. Load a fresh Sionna scene and construct a fresh `SDRNetworkReceiver` and
   geometry binding, as each live CLI invocation does. This discards scattering,
   candidate, render and continuous-DSP state; begin a new timestamped recording.
   No midstream reload or stitching across a revision is supported.

The closure check moves a wall, verifies rejection by the old binding, exports a
new snapshot, accepts the new binding, and independently ray-checks the new RF
scene. It also verifies plane-cache rebuilding for a different scene and a
fresh solver's own cache. Updating only actor poses or only RF files is invalid.

## Qualification and reproduction

The [20 October closure report](../results/reviews/priority1-20261020/REPORT.md)
contains acceptance evidence and exact commands for independent collision probes,
combined turning/reflection/obstruction recording, CPU I/Q consumption, negative
controls, and focused regressions. Native USD instances, unit conversion,
reflected winding and baked shear/reflection are covered by CPU regressions.
All included source geometry is selected; the original Blocks map is isolated
100 metres below these controlled scenes and is outside the declared RF domain.

Priority 1 is closed for this common-source workflow in the pinned environment.
Arbitrary existing-world/editor extraction remains a separate source adapter;
pose APIs do not expose its triangles. Camera rendering, continuous dynamic
obstacles, calibrated RF materials, broader version support and fleet performance
are not established by this qualification.

## API references used during implementation

- [USD transform cache](https://openusd.org/24.08/api/class_usd_geom_xform_cache.html)
- [USD instance traversal](https://openusd.org/release/api/_usd__page__scenegraph_instancing.html)
- [USD units](https://openusd.org/release/api/group___usd_geom_linear_units__group.html)
- [Sionna scene loading](https://nvlabs.github.io/sionna/rt/api/scene.html)
- The pinned ProjectAirSim `world.py` in the local source checkout for
  `spawn_object`, `get_object_pose` and `get_object_scale`.
