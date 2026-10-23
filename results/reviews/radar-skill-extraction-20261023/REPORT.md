# Radar RF Skill extraction — 2026-10-23

The receiver application, FFT math, neutral transport and sample replay adapters
are maintained in [wa200508/Radar-skill](https://github.com/wa200508/Radar-skill).
The acquisition repository keeps the scenario, radar/target physics, Sionna
propagation and observer; the local skill module is only a compatibility import.

Pinned independent source/image:
`ed36dffc23e716e24d7bf3ed084c0358d1d12e18`.

## Evidence

- Local standalone NumPy-only container build: passed.
- Actual TCP/HTTP/journal, physically absent AirSim/Sionna/DF-Skill: passed.
- Exact recording and replay into a fresh unchanged radar consumer: passed,
  with identical range/Doppler results.
- Local skill suite: **6 passed**.
- Shipped dashboard JavaScript suite before workspace disconnect: **9 passed**.
- Independent repository CI: build, offline qualification, six installed-package
  tests and container publication all passed. Its final anonymous-pull gate
  initially failed because the repository/package were private.
- Cross-repository acquisition/consumer tests remain in
  `tests/test_radar_scenario.py`, importing the external package directly.
  The architecture guard now rejects simulator imports of either `df_skill`
  or `radar_skill`.
- No full native two-drone rendered GPU mission or new throughput claim was
  measured during extraction.

## Deployment gate

The integration must not become the default until the pinned source archive
and container are publicly accessible. They are direct dependencies of fresh
checkout/container builds. Publishing a private image is not anonymous-pull
qualification. Existing simulator/RF revision matching remains mandatory;
only the independently released receiver uses `revision_policy: independent`.

## Public release path

The canonical Radar-skill package continued to reject anonymous manifests after
the source repository became public. The release workflow now builds the same
pinned external repository/Dockerfile directly and publishes
`ghcr.io/wa200508/airsim-rf:radar-skill-sha-ed36dffc23e716e24d7bf3ed084c0358d1d12e18`
through airsim-rf's existing public registry package. It performs offline
independence/replay qualification before publication and repeats it after a
fresh anonymous pull. Scenario and Docker alias use that artifact with the
independent radar source revision. The receiver implementation stays solely
in Radar-skill.

## Verified deployment gate

The deployment gate above is satisfied by the public release path:
[anonymous pull and pulled-image offline replay passed](https://github.com/wa200508/airsim-rf/actions/runs/40015010036),
and the [merged-main release rerun passed](https://github.com/wa200508/airsim-rf/actions/runs/40015774738).
The source archive is public. No registry authentication is needed to launch
the pinned radar receiver.

The [standalone repository CI](https://github.com/wa200508/Radar-skill/actions/runs/40015998544)
also passed after its quickstart and release checks were aligned with this image.
Cross-repository focused validation passed **41 Python tests**, with two
Sionna-only checks skipped in the CPU environment; the **9 JavaScript tests**,
source architecture checks and **50 maintained Markdown files** passed.
The earlier full container run passed 367 tests and exposed one old HTTP
assertion that omitted scenario-selector metadata; that assertion was corrected
and both actual host HTTP tests passed in the focused rerun.

[Integration PR #1](https://github.com/wa200508/airsim-rf/pull/1) is merged.
The longer dashboard/GPU-image pipeline remains a separate qualification; these
results do not assert a completed native GPU flight.
