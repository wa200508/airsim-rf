[Documentation](../README.md) · [Scenarios](../../scenarios/README.md) · [Run dashboard](../dashboard.md)

# Extensible geometry bridge

The [ASE/Open Arsenal selection](../archive/reviews/ase-standards-selection-20261018.md)
sets the external integration boundaries: AMS GRA RF MEL, OMS/UCI through CAL,
and DIS truth. OpenUSD is a supplementary asset format, not the mission bus or
an established ASE requirement. Include explicit entity/aperture identity and
NED/ECEF/RF frame mappings as this provisional contract evolves.

The [open-standards review](../archive/reviews/geometry-standards-20261018.md) recommends
OpenUSD as the external scene foundation, with a documented RF profile and
version-specific adapters. The JSON format below remains a provisional internal
snapshot. The [OpenUSD workflow](openusd-workflow.md) now has an importer,
RF profile, placement/readback APIs and optional live guard implemented in source.
The common-source nonprimitive path is now
[qualified](../../results/reviews/priority1-20261020/REPORT.md), including matching
collision surfaces, moving/turning radios, obstruction, first-order reflections,
I/Q and revision boundaries. Static environments are supported; arbitrary-world
extraction and continuous obstacle updates remain separate adapters/capabilities.

The bridge separates source adapters (AirSim/Unreal or shared assets), a
versioned geometry document, and RF export adapters. Neither upstream runtime
is imported by `airsim_rf.geometry`. An upstream upgrade should require changes
to its adapter and qualification evidence, rather than changes to every consumer.

## First implementation: offline schema v1

The [example document](../../examples/config/shared-geometry.json) describes the
cube used in the earlier controlled alignment experiment. It is a common data
description, not evidence that an AirSim adapter has loaded it.

```bash
PYTHONPATH=src python -m airsim_rf.geometry examples/config/shared-geometry.json \
  --output recordings/shared-geometry-export
```

This command needs Python and NumPy, does not connect to a simulator, and does
not import Sionna/Mitsuba or access a GPU. The output directory must be new.
It produces `geometry.json`, per-object PLY meshes, `scene.xml` and a manifest
of content hashes. The manifest is written last; interrupted exports without
it must not be consumed. Runtime loading was qualified for the shared-box OpenUSD example.

The strict schema contains:

- `schema_version`, `scene_id`, and `revision` to identify the contract and scene.
- `source`: adapter/version, source asset/revision, and `geometry_kind` explicitly
  distinguishing collision, render and deliberately shared geometry.
- `materials`: explicit relative permittivity, conductivity in S/m and a written
  assumption. These are simple constant material parameters, not visual texture
  mappings or calibrated frequency-dependent models.
- `objects`: stable ID, material reference, local vertices, triangular faces,
  and a nonsingular affine `local_to_ned_m` matrix. Matrices multiply column
  vectors; their output is world NED in metres. Scale/unit conversion belongs
  in this matrix. Export bakes NED into RF `(x, -y, -z)` and corrects triangle
  winding under negative-determinant transforms.

Unknown fields and versions fail explicitly. Source adapters must convert their
native coordinates into this declared convention; raw Unreal coordinates are
not assumed to be NED. One material per object is supported; split multi-material
meshes into stable subobjects. Full snapshots are supported. The OpenUSD adapter and optional live guard add
static environment placement/readback; incremental target updates, skeletal or
deforming geometry and texture-derived RF material inference remain unsupported.

## Upgrade and synchronization policy

Keep adapters named and versioned independently of the interchange schema.
Record upstream versions and source asset revisions in provenance. Add an
explicit schema migration if semantics change; never reinterpret old documents
silently. Export hashes change with vertices, topology, transforms or material
assignments. The live workflow preserves these identities per recording window. A changed
static actor rejects capture. A new revision requires a new bundle, simulator
placement, RF scene and receiver; this discards geometry-dependent caches and
continuous DSP state. The exporter does not hot-update a running receiver.

Qualification should cover source coordinates and ray intersections separately
from target loading and RF behavior. Recheck each adapter when its upstream
dependency changes. Passing document validation establishes structural validity,
not matching world geometry or physical RF accuracy.

## Qualified workflow

The [OpenUSD workflow](openusd-workflow.md) documents preparation, packaged-asset
and generated-GLB placement, recording, and the required revision/reload boundary.
The [closure report](../../results/reviews/priority1-20261020/REPORT.md) retains the
independent collision/ray checks and moving-radio I/Q evidence. The source route
supports nonprimitive shared triangles without requiring a general Unreal editor
exporter. Actor pose readback still cannot inspect arbitrary collision meshes or
infer RF properties from visual materials.
