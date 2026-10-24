# OpenUSD shared-scene qualification — 19 October 2026

> Documentation note: reported measurements are preserved. Local artifacts absent from this repository are shown as file references rather than download links.

**Result: passed for the static shared-box integration scope. Priority 1 remains open.**
The user explicitly authorized GPU use and qualification checks. No package was
published or delivered. Only the task-owned Blocks server was started/restarted
and stopped; unrelated containers were not modified.

## Evidence

- Authoritative machine report (`qualified/report.json`; local artifact, not checked in)
- Raw Unreal observations (`qualified/unreal.json`; local artifact, not checked in)
- Export bundle manifest (`qualified/bundle/manifest.json`; local artifact, not checked in)
- GPU qualification log (`qualification.log`; local artifact, not checked in)
- CPU regression log (`cpu-tests.log`; local artifact, not checked in): **28 passed, 1 skipped**. The skipped test
  requires the optional `sigmf` Python package, absent in this image.
- Server log (`server.log`; local artifact, not checked in)
- [Qualification source](../../../scripts/qualify_usd_geometry.py)

The scene contains a ground slab, building and rotated wall. OpenUSD local
triangles and composed transforms produce both the Unreal actor placements and
Sionna meshes, with explicit RF materials and coordinate conversions. Geometry
is placed 100 metres above the original Blocks environment to isolate this check.
Four stationary probes collect 308 Unreal CPU LiDAR returns across 0.45 simulated
seconds. Their measured directions and distances are compared with an independent
CPU triangle intersection routine and Mitsuba CUDA intersections.

| Check | Observed result |
| --- | --- |
| Maximum Unreal–CPU intersection difference | 0.464 micrometres |
| Maximum Unreal–GPU intersection difference | 8.172 micrometres; gate 1 mm |
| Maximum actor-readback vertex difference | 0.0169 micrometres; gate 10 micrometres |
| Object identities | Ground, Building, Wall preserved in RF scene |
| Direct and first-order ground reflection | Two paths, matching analytic lengths |
| Maximum analytic delay difference | 1.82e-15 seconds |
| Direct path through building | Zero paths |
| Wall moved one metre | Static geometry guard rejected it; restoration accepted |
| RF path gains | Finite |

CPU regressions cover example transforms, bundle tampering, actor placement,
changed epochs, moved geometry, known ray hits, missing USD units, subdivision
and omitted geometry. Capture regressions check start/end guards, preservation
of the start report and rejection before sample generation at either epoch.

## Qualified environment and reproduction

- Tesla P100, existing `airsim-rf:p100-modern-gpu` image.
- Sionna RT 2.2.0, Mitsuba 3.8.0; Pascal compatibility enabled.
- OpenUSD `usd-core==26.8`, isolated in ignored `.deps/openusd-26.8`.
- Existing pinned Blocks Linux 1.0.1 package, null-RHI CPU collision mode.
- Script SHA-256 and geometry identity are in the authoritative report; input
  layer/profile and exported file hashes are retained in the bundle.

Start a dedicated Blocks server using the procedure in
[Unreal geometry integration](../../../docs/reference/unreal-geometry.md). Ensure ports
8989/8990 are available and do not interrupt another user's server. Then run,
from the repository root, with a fresh output directory:

```bash
docker run --rm --gpus device=0 --network host --user 1000:1000 \
  --tmpfs /.drjit:rw,mode=1777 -e HOME=/tmp \
  -e PYTHONPATH=/work/repo/src:/work/repo/.deps/openusd-26.8 \
  -v "$PWD:/work/repo" -w /work/repo \
  --entrypoint /opt/airsim-rf/.venv/bin/python airsim-rf:p100-modern-gpu \
  scripts/basis_launch.py scripts/qualify_usd_geometry.py --pascal-compat \
  --output results/reviews/usd-geometry-repeat
```

Focused CPU suite, with the same Python path and image but no GPU:
`python -m pytest tests/test_geometry.py tests/test_live.py -q -rs`.

The first GPU attempt found a qualification-script type conversion error:
Mitsuba rejected NumPy scalar arguments for Point3f. Explicit conversion to
Python floats fixed it. The incomplete parent-directory artifacts are retained;
`qualified/report.json` is authoritative. The separate `usd-geometry-20261019-final`
directory is an earlier passing run without the added analytic/obstruction gates.

## Limits and next-agent handoff

This is geometry integration evidence for shared primitives in one pinned stack.
It does not establish calibrated material response, independent physical RF
accuracy, render-camera equivalence, arbitrary Unreal mesh equivalence, or a
complete moving-radio I/Q recording with the new bundle. The modified older
single-cube qualification script has not been rerun. Native USD instances and
reflected winding still need dedicated regression coverage.

Next, in order:

1. Complete the shared-scene recorder run with moving radios, recorded geometry
   identity and usable downstream I/Q evidence. Add instance/reflection cases.
2. Establish a reproducible nonprimitive Unreal/editor USD export workflow;
   verify collision topology and environment coverage. Pose readback cannot
   detect mismatched mesh assets or unlisted objects.
3. Define/implement moving-obstacle update and cache-invalidation support if
   required for closure. Current start/end static guards miss transient motion
   that returns to its starting transform during a window.
4. Qualify adapter upgrades separately; the declared USD dependency range is
   not a supported-version matrix.

Keep the user's priority order: geometry, usable package consolidation **without
delivery**, downstream results, sustained operation, independent physical
accuracy, then performance. Primary audience: RF/SDR engineers and algorithm
developers. Standards decisions remain in the ASE/Open Arsenal selection.

The dedicated container `airsim-rf-geometry-20261019` was stopped after collecting
logs. Changes remain local and uncommitted. Preserve earlier pending changes and
historical evidence. Current permission allows qualification and GPU use; it
does not permit interrupting unrelated workloads.
