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
