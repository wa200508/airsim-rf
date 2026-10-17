# Unreal geometry integration

The normal Runtime starter is sufficient for API/physics integration, but it
cannot establish that an Unreal world matches the RF mesh. A real headless
Blocks package now passes a [controlled cube alignment check](../results/reviews/unreal-geometry-20261016/REPORT.md).
This establishes primitive coordinates, scale and visibility through CPU LiDAR
and GPU RF intersections; general mesh export remains open.

## Run the controlled check

Prepare the tested [CPU and GPU images](setup.md), then fetch the checksum-pinned
upstream package (about 584 MB compressed):

```bash
python scripts/prepare_unreal_blocks.py
```

Ensure the task's standalone Runtime server is stopped before using the same
8989/8990 ports. Start Blocks without display rendering:

```bash
docker run --rm -d --name airsim-rf-blocks \
  -p 127.0.0.1:8989:8989 -p 127.0.0.1:8990:8990 \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/.deps/blocks-linux-1.0.1/extracted:/blocks" -w /blocks \
  --entrypoint /blocks/Blocks/Binaries/Linux/Blocks-Linux-Shipping \
  airsim-rf:p100-profile Blocks -nullrhi -nosound -unattended
```

In the CUDA environment run:

```bash
python scripts/qualify_unreal_geometry.py --output recordings/unreal-geometry-new
```

Use `scripts/basis_launch.py` and `--pascal-compat` for the P100 stack. The script
loads its own scene and owns simulation stepping; use a dedicated server. It
compares a known cube at altitude 100 m before and after a lateral move. Stop the
task server afterward with `docker stop airsim-rf-blocks`.

`-nullrhi` disables rendering; this is an Unreal world/collision test, not rendered
camera qualification. The package's harmless `xdg-user-dir` warning does not
prevent the tested API and CPU LiDAR operations. No local Unreal editor is needed.

## What a general scene handoff must contain

Keep these requirements with the scene assets, rather than relying on a screenshot:

- The Unreal asset/world revision and the exported RF vertices/triangles, including
  instances and every applied transform. Record whether collision or render geometry
  was exported; do not silently treat them as identical.
- Units, origin and axis mapping. API NED meters map to RF `(x, -y, -z)`. Raw Unreal
  coordinates use a different handedness and commonly centimeters; establish the
  world-to-NED transform before applying the RF conversion.
- Explicit RF materials and their assumptions. Unreal visual textures are not
  dielectric permittivity, conductivity or measured roughness.
- Measured control points and ray intersections on multiple nonparallel surfaces,
  plus an obstruction transition checked independently in both representations.
- A documented policy for moving objects: update the RF geometry at each channel
  snapshot and invalidate cached meshes when geometry changes.

The present server APIs expose object poses/scales and asset spawning. The inspected
world API does not provide a general triangle-export endpoint. An editor/offline
export or a deliberately shared geometry asset is still needed for arbitrary maps.
The cube check is a reproducible first contract, not a substitute for that exporter.
