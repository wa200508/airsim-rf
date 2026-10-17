# Unreal-backed primitive alignment — 16 October 2026

A real packaged Unreal Blocks server passed a controlled coordinate, scale and
visibility check against CUDA RF geometry. **81 CPU LiDAR surface points** match
RF ray intersections within **0.00000764 m**. Moving the cube out of the beam
removes LiDAR returns and restores the direct RF path.

This is a shared primitive check. It does not establish arbitrary Unreal mesh
export, rendered-image alignment or a complete RF model of the Blocks map.

## Physical construction

The non-physics probe sits at NED (0, 0, −100) m, corresponding to RF (0, 0, 100)
m, above the map's ground objects. A packaged `Cube` is spawned at NED (5, 0,
−100) m with scale (2, 2, 2). Its measured near face is 4 m ahead of the probe.
The matching RF mesh has local corners ±1 m and is translated to (5, 0, 100) m.
An RF receiver lies at (10, 0, 100) m, behind the cube.

The probe uses one-channel generic CPU cylindrical LiDAR, range 20 m and a narrow
±5° horizontal field of view. The first phase advances ten 30 ms intervals,
covering 0.300 simulated seconds. Received sensor-relative NED points are mapped
to RF by `(x, -y, -z)` and translated by the probe origin. GPU ray intersections
with the RF cube reproduce those points within the 1 mm acceptance threshold.
The direct path is absent, as expected.

The cube is then moved to NED (5, 3, −100) m, mapped to RF (5, −3, 100) m, and
another 0.300 simulated seconds are advanced. New LiDAR messages have no returns
in the narrow view; the RF direct path returns. Sensor subscription delivery is
asynchronous: the saved points are the received measurement subset, not a promise
that every possible LiDAR scan was delivered. This check generates no I/Q stream,
so its 0.600 simulated seconds must not be reported as rendered signal duration.

## Environment and reproduction

The upstream [v1.0.1 Blocks Linux package](https://github.com/iamaisim/ProjectAirSim/releases/tag/v1.0.1)
is checksum-pinned in [release.json](release.json). It runs inside the existing
CPU image with `-nullrhi -nosound -unattended`: the Unreal world and CPU collision
queries execute, while camera/rendering output is disabled. No Unreal editor or
engine build was needed. The RF intersection/visibility checks use the explicit
P100-compatible Sionna stack. This upstream packaged server differs from the
pinned source-built standalone Runtime used for earlier flight tests.

See [Unreal setup and limits](../../../docs/unreal-geometry.md) for commands.
The [qualification script](../../../scripts/qualify_unreal_geometry.py) records
actual object pose/scale and LiDAR messages, then builds the independent RF cube.
No mesh is exported from the running Unreal process.

Evidence: [checks](report.json), [raw measurements](unreal.json),
[RF scene](cube.xml), [RF mesh](cube.ply), [client log](client.log), simulator
configuration under `sim/`. The initial API probe required the SDK's explicit
pose `frame_id`; adding it resolved the request error. All reported checks use
the successful final run.

## Remaining scope

The two representations are explicitly authored from the same primitive, and
measured collision surfaces confirm their alignment. A general exporter still
needs vertex/triangle extraction, consistent transforms/units, material mapping,
instancing and scene updates. Static-mesh collision and render meshes can differ;
this result does not equate them for arbitrary assets. Camera images, complex
terrain, moving imported meshes and RF material calibration remain unqualified.
