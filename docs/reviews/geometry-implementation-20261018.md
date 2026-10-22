# Geometry implementation handoff — 18 October 2026

> Historical implementation snapshot. See the [19 October qualification and handoff](../../results/reviews/usd-geometry-20261019/REPORT.md) for current execution permission, evidence and remaining work.

User direction: implement as much of priority 1 as possible without testing.
OpenUSD is approved as the scene interchange foundation. GPU/process access
remains prohibited during the reserved workload. Package preparation is allowed;
delivery/publication is not.

## Authored in this increment

- `src/airsim_rf/usd_geometry.py`: strict RF profile, optional USD composition,
  triangle import, frame/units conversion, instance-proxy traversal, winding
  handling, explicit exclusions, source hashes and unsupported-feature errors.
- `src/airsim_rf/geometry.py`: extended export bundle with simulator/network
  bindings, source provenance, object identities, load policy and integrity reads.
- `src/airsim_rf/geometry_sync.py`: common-source placement plans, explicit
  spawning, paused pose/scale snapshots, stale static-scene rejection and a CPU
  triangle-ray reference for later independent comparisons.
- `src/airsim_rf/live.py` and `sdr_bridge.py`: opt-in bundle loading without shape
  merging, runtime object-ID check, start/end pose guards and per-window
  provenance. Optional explicit spawn after simulator scene loading; default
  existing-object mode never moves actors.
- `examples/geometry/shared-world.usda` and `.rf.json`: ground, building and
  rotated wall with explicit RF properties and simulator mappings.
- CLI entry points and optional OpenUSD dependency declaration in `pyproject.toml`.
- `scripts/qualify_unreal_geometry.py`: replaced independent cube definitions
  with a shared normalized source for simulator placement and RF export.
- [User workflow](../openusd-workflow.md), scope, failure behavior and closure
  criteria, linked from geometry/live docs and the readiness handoff.

## What was actually done

Read existing source and upstream API documentation, edited source/assets/docs,
and inspected text diffs/status. Small file-authoring scripts wrote example
assets and updated documentation. No new project module was executed or imported.
No tests, linting, compilation, package installation, USD import, simulator
connection, GPU query, benchmark or qualification run was performed. Existing
test-file changes in the worktree predate this increment and were preserved.

## Limits that must remain visible

This is source implementation, not validated behavior. The declared OpenUSD
dependency range is provisional. Static environment with moving radios is the
first supported live scope. Automatic moving-obstacle target updates are not
implemented; changed static actors abort capture. A snapshot can be exported
as a new bundle, but capture does not reload Sionna midstream.

Pose/scale readback checks placement against declared local geometry. It cannot
inspect Unreal collision triangles, detect changes to asset topology/materials,
inventory unlisted runtime obstacles, or detect transient motion that returns
to the same pose between interval endpoints. A matching editor/offline export
and independent collision/ray checks are still required for arbitrary scenes.

The revised cube qualification script has NOT been rerun. Historical success
does not qualify its new code. Future qualification must cover object naming,
material loading, positive/negative transforms, timestamp guards and state
failure behavior as well as actual ray/reflection agreement.

## Priority-1 status

**Remain open.** The implementation path and example are ready for subsequent
review/qualification, but neither geometry equivalence nor the broad dynamic
scene capability is established. Use the closure list in the workflow document.
Do not cross off item 1 merely because code has been authored. Continue with
source work if testing is still withheld; request no GPU/process interruption.

No commit, release or publication was made. Preserve unrelated pending work.
