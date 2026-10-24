# Priority 1 pause and resume — 19 October 2026

> Historical handoff. The user resumed on 20 October and priority 1 is now
> [complete for static shared environments](../../../results/reviews/priority1-20261020/REPORT.md).
> The pause and next-action text below records the earlier state.

**Paused at the user’s request.** Resume when the user returns; no weekend job
or reminder has been scheduled. Priority 1 is still open. Latest completed
qualification is [the shared-box report](../../../results/reviews/usd-geometry-20261019/REPORT.md).

## Latest request and estimate

Remaining-effort estimates for all six priorities are now saved in the
[readiness review](project-readiness-20261017.md#estimate-assumptions-and-uncertainty--19-october-2026).
This documentation-only update leaves project execution paused.

The user asked to continue until priority 1 closes, then asked for an estimate.
Estimated 2–4 hours of active work if the existing client-mesh API works, potentially
a day or more if a simulator rebuild is needed. The user then explicitly paused
work until the weekend. Do not continue experiments while paused.

GPU use and qualification checks were authorized for this session. On resumption,
check resource availability and do not interrupt unrelated workloads. Do not
publish or deliver the package. Primary audience remains RF/SDR engineers and
algorithm developers. Preserve the six-priority order in the readiness review.

## Findings during this continuation

No production code was changed and no new qualification was run.
Read the saved criteria: shared geometry, explicit transforms/materials/revisions,
independent intersections, moving turns, obstruction and first-order reflections,
and a defined object-change policy. Do not silently substitute narrower criteria.

A promising route removes the requirement for prepackaged primitive assets:
ProjectAirSim `World.spawn_object_from_file(name, "gltf", bytes, True, pose,
scale, enable_physics)` accepts GLB meshes from the client. The existing pinned
Blocks WorldSimApi source implements this through Assimp and procedural meshes.

Pinned upstream files were read with `git show HEAD:<path>` from the existing
`.deps/ProjectAirSim-runtime` checkout (missing Git blobs fetched). Copies are
in `results/reviews/priority1-20261019-paused/`:

- `airsim-AssimpToProcMesh.cpp`: rotates left-handed glTF by +90 degrees around X
  for Unreal Z up and requests collision creation on the procedural mesh.
- `airsim-ProcMeshActor.cpp`: creates procedural mesh sections with collision.

Existing `.deps/blocks-linux-1.0.1/WorldSimApi.cpp`, lines around 564–630, uses
Assimp scale 100 (metres to centimetres), MakeLeftHanded, then the above adapter.
The candidate inverse mapping from actor-local NED to glTF is `(x, -z, y)`.
**This mapping is inferred from source and is not yet runtime-qualified.**

The official [glTF specification](https://github.com/KhronosGroup/glTF/blob/main/specification/2.0/Specification.adoc)
was consulted for GLB layout and metre/Y-up coordinate conventions. OpenUSD
remains the interchange foundation; GLB would be a simulator-specific output
adapter, not a replacement standard.

## Next actions

Use the [usage-aware work plan](token-budget-plan-20261019.md): one bounded
deliverable at a time, prepared unattended numerical jobs, and before/after
allowance readings. Earlier hour estimates are not token-calibrated.

1. Implement and independently probe a generated GLB from shared triangles,
   using the client-mesh API. Test asymmetric/nonprimitive geometry, transforms,
   collision topology, and RF intersections. Verify the RPC truly creates an
   object: the upstream function can return a name even when parsing fails.
2. Qualify the full recorder with moving/turning radios in the shared scene,
   first-order reflections and obstruction, retaining geometry provenance and I/Q.
3. Add native USD instance and reflected-winding regression coverage.
4. Implement/document a safe geometry-revision boundary: stale geometry rejects
   capture; new snapshots/bundles require rebuilding RF geometry and invalidating
   caches. Continuous dynamic obstacles are not implemented. The saved criterion
   says to define object-change behavior; be explicit about supported scope.
5. Review acceptance evidence, update workflow/capability status, and only close
   priority 1 when its criteria are met. General existing-world editor export may
   remain a separate adapter if the shared nonprimitive source route is qualified;
   document that distinction clearly rather than claim arbitrary-world extraction.

## Resource lifecycle

At the start of this continuation the P100 showed 263 MiB used and 0% utilization.
Unrelated containers were `comfyui`, `gitlab-runner`, and
`immich_machine_learning`; none was modified.
The task-owned `airsim-rf-priority1-20261019` Blocks container was started with
null-RHI on localhost ports 8989/8990. It is stopped as part of this pause;
its log is saved in the paused evidence directory. No GPU compute job was launched.
