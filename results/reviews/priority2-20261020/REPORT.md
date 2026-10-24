# Priority 2 complete — 20 October 2026

> Documentation note: reported measurements are preserved. Local artifacts absent from this repository are shown as file references rather than download links.

**Passed: a coherent local package for the qualified Python 3.12/Linux/Docker
workflow. Nothing was published, released or delivered.** Priority 2 is crossed
off the readiness list; priority 3 remains the next milestone.

Start with the [shared-scene quickstart](../../../docs/quickstart.md). The
[interface reference](../../../docs/reference/interfaces.md),
[troubleshooting guide](../../../docs/troubleshooting.md) and
[capability matrix](../../../docs/capabilities.md) cover configuration, units,
extension points, expected results and current limits.

## Acceptance evidence

Machine audit (`acceptance.json`; local artifact, not checked in): **17 checks passed**. It independently reads
the real live recording with official SigMF, checks geometry identity,
plan/count agreement, spectrum, ADC clipping, wheel assets and licenses, and
verifies the saved installation/container/test reports.

| Priority-2 criterion | Implemented and checked |
| --- | --- |
| Reproducible setup | `bootstrap.py --geometry` installs source/dependency pins plus OpenUSD 26.8. The Dockerfile was built from a fresh Python base with OS libraries and fresh pinned upstream clones, producing local image `airsim-rf:priority2-local`. Build log (`container-build.log`; local artifact, not checked in), final source-layer rebuild (`container-build-final.log`; local artifact, not checked in), image identity (`container-image-id.json`; local artifact, not checked in). |
| Clean install | A new environment with no inherited Python packages installed the full lock, clean verified source copies and final wheel. `pip check` passed. Imports resolve to site-packages outside the checkout. Fresh install log (`clean-install-final.log`; local artifact, not checked in), nine acceptance checks (`clean-install-final/report.json`; local artifact, not checked in). |
| Complete examples/assets | Packaged ground XML/PLY and nonprimitive shared USD/profile resources. `airsim-rf example` produces waveform, all simulator configs, matching geometry bundle, RF materials, bindings and instructions. Both examples pass, including a copied/relocated shared directory. |
| Preflight/actionable errors | Validates mappings, referenced assets, strict settings, source length, tick overshoot, sample alignment, sample cap and output space. Optional GPU checking loads the configured RF mesh and exercises CUDA/OptiX/CuPy without server contact. The live runner checks the plan before GPU/world initialization. |
| Interfaces/troubleshooting | README routes to one current workflow, configuration/API/units/format reference, waveform/geometry/motion replacement guidance, expected outputs and corrective actions. Legacy workflows and historical evidence remain identified and preserved. |
| Capability/acceptance matrix | Current scope explicitly distinguishes static geometry revisions, DSP/ADC conventions, callbacks/TCP, tested versions and outstanding downstream/reliability/accuracy/performance work. Stale geometry and combined-turn/obstruction statements were reconciled. |
| Real complete example | The installed wheel outside the checkout generated shared inputs, passed GPU preflight, spawned matching Blocks meshes, captured real I/Q, and passed installed inspect/process commands. Live log (`installed-live.log`; local artifact, not checked in), preflight (`live-preflight.json`; local artifact, not checked in), inspection (`live-inspection.json`; local artifact, not checked in), processing (`live-processing.json`; local artifact, not checked in). |
| Ongoing package gate | Docker builds a local wheel. CI now installs it separately, changes out of the checkout and exercises complete examples plus CPU propagation/receiver/consumer interfaces offline. The exact gate passed in the freshly built image: report (`container-wheel/report.json`; local artifact, not checked in), log (`container-wheel.log`; local artifact, not checked in). |

## Validation results

- **Full standard CPU suite: 253 passed, 158 skipped**, no failures.
  Log (`full-standard-cpu-tests.log`; local artifact, not checked in). Skips require CUDA/hardware and are not
  counted as CPU validation. This run used the final installed wheel in the fresh
  environment, without a source-path override.
- **Requested short GPU retry: 3 passed, 132 deselected in 7.00 seconds**.
  Log (`focused-gpu-tests.log`; local artifact, not checked in). Selected cases cover Pascal counters, kernel
  compilation and real private-input CUDA rendering against CPU references.
  The run was bounded to 120 seconds; this is not a full GPU-suite claim.
- **Installed-wheel CUDA preflight passed**, loading Ground, Building and Wall,
  checking a synthetic direct path and CuPy rendering. Maximum renderer error
  against CPU: **3.51e-16**. No simulator contact occurred during preflight.
- **Live example: 240,000 complex samples**, ten 24,000-sample windows,
  **0.120 signal seconds at 2 MS/s**, **960,000 I/Q bytes**. Actual counts match
  the 12 ms tick-overshoot plan. Geometry identity/epoch match in every row;
  no ADC clipping. Peak **149,902.34375 Hz** lies within one **488.28125 Hz** bin
  of the supplied +150 kHz tone.
- Installed processing reports **67.2162 µV RMS complex input-referred voltage**,
  with ADC components −20…21 counts. These are scenario-specific observed levels,
  not calibrated hardware power or a modulated consumer result.
- Official SigMF 1.13.0 reads every actual live sample and agrees with the
  project's volts reader. Data/wheel SHA-256 identities are in `acceptance.json`.

The first broad CPU run in the older P100 image produced five
`JitBackend.Metal` compatibility failures, 248 passes and 158 skips. That image
is the Pascal exception stack, rather than the standard CPU release-test lock.
Its failed log (`full-cpu-tests.log`; local artifact, not checked in) is retained. The complete suite was rerun
against the correct pinned CPU environment and passed; no numerical thresholds
or tests were removed. The earlier clean-install report remains for provenance;
`clean-install-final` identifies the final wheel.

## Package changes and reproduction

`airsim-rf` provides `example`, `preflight`, `inspect` and `process`. Existing
live/USD/radar-worker entry points remain. `airsim-rf-cuda` exposes the active
environment's CUDA wheel libraries before launching Python. Repository example,
inspector and launcher scripts are compatibility wrappers.

Assets use `importlib.resources` and setuptools package data. Wheels include
README metadata, MIT license and third-party notices, without depending on
repository `benchmarks/` or `examples/` paths. Simulator robot/config references,
required TX settings, unknown keys and receiver settings fail explicitly. The
runner rejects accidental source exhaustion and insufficient overshoot caps
before world mutation. Generated I/Q, waveforms, wheels and build directories
are excluded from Docker's build context. Existing pending changes are preserved.

For ordinary use, follow the [quickstart](../../../docs/quickstart.md). To repeat
package acceptance locally with a new output directory:

```bash
OUT=results/reviews/priority2-repeat
mkdir -p "$OUT/local-build"
python -m pip wheel --no-deps --wheel-dir "$OUT/local-build" .
docker build -t airsim-rf:priority2-local .
docker run --rm --network none airsim-rf:priority2-local
docker run --rm --network none airsim-rf:priority2-local \
  python /opt/airsim-rf/scripts/qualify_wheel_overlay.py \
  --wheel /opt/airsim-rf/local-wheel/airsim_rf-0.2.0-py3-none-any.whl \
  --output /work/package-check
```

Full fresh-dependency qualification uses the existing image only as an
OS/source-cache base, and does not inherit its Python dependencies:

```bash
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD:/work/repo:ro" -v "$PWD/$OUT:/evidence" -w /tmp \
  --entrypoint /bin/bash airsim-rf:p100-modern-gpu \
  /work/repo/scripts/qualify_local_package.sh
```

This verifies both upstream commits and cleanliness, installs into an empty
environment, runs `pip check`, installed-package acceptance and the full CPU
suite. Network access supplies dependency wheels. The offline CI overlay gate
instead shares already-tested image dependencies; its helper explicitly handles
nested virtual environments and verifies that the RF package is the wheel copy.

For live acceptance, start a dedicated Blocks server and run
`scripts/qualify_package_live.sh` in the qualified P100 image with GPU/host
networking, checkout read-only at `/work/repo`, evidence writable at `/evidence`,
and only optional USD/SigMF dependency directories on `PYTHONPATH`. The script
verifies an installed-wheel import and reuses the qualified P100 dependencies.
Collect logs and stop the task-owned server afterward.

## Scope and cleanup

Qualified CPU stack: Python 3.12.14, NumPy 2.5.3, SciPy 1.18.1, Sionna RT 2.2.0,
Mitsuba 3.9.1, Dr.Jit 1.5.0, ProjectAirSim client 1.1.0, OpenUSD 26.8 and
SigMF 1.13.0 on the documented Linux native-library base. Live P100 checks use
Mitsuba 3.8.0/Dr.Jit 1.3.1/CuPy 13.6.0 with explicit compatibility. No broader
OS/GPU/upstream-version matrix is implied.

GPU occupancy was initially 3,535 MiB/100%, so CPU work continued without
interruption. At 263 MiB/0%, installed-wheel preflight/capture ran. The user's
later short window passed the focused compatibility tests. Only task-owned
`airsim-rf-priority2-20261020` was started and stopped. Server log (`server.log`; local artifact, not checked in).
Unrelated services remain running. No GPU work or task simulator is left active.

The package/image remain local and changes uncommitted. No upload, release,
publication, registry push or package delivery occurred. The new CI gate was
tested locally; no remote CI/publication run was triggered.

Priority 3 remains open: a known tone does not demonstrate an independent
modulated comms/ESM consumer or EVM/BER/detection result. Sustained operation,
independent physical accuracy and fleet performance retain priorities 4–6.
