# RF skill / simulation boundary audit

This review found and corrected real coupling. The simulator previously waited
on MUSIC-specific HTTP epochs and read skill diagnostics to publish combined
recording frames. The skill also imported source-format/offline helpers, and its
container inherited the simulator runtime. Separate processes alone did not
establish the requested boundary.

The resulting contract is **source → receiver samples → application**. Source
telemetry/camera and application results are independently journaled and meet
only in the dashboard observer or held-out evaluation. The source waits for a
generic transport commit, not a MUSIC result or detection. This changes software
ownership and flow control; it does not alter terrain, waveform, path physics,
receiver sensitivity or the dashboard's 120 ms window.

## Comprehensive inventory

The [machine-readable audit](audit.json) classifies **68 package modules** and
**208 Python files** including scripts, examples, benchmarks and tests. All
package modules have an explicit role; no package module was left unclassified.
The maintained guides, container stages/mounts, skill manifest, launcher and CI
workflow were also reviewed. This is an architectural/code audit, not a proof
of arbitrary third-party behavior or a complete security assessment.

| Area | Review and disposition |
| --- | --- |
| Dashboard producer, source synchronization and recording | Removed application HTTP polling/result reads. Source emits neutral sample frames, validates generic commits and saves source-only telemetry/camera. Stop, timeout and processing failure cannot advance an unacknowledged window. |
| Receiver application and reusable processing | `skills/music.py` uses only the receiver contract, calibrated samples, own-array configuration, receiver-only math and independent result I/O. MUSIC/PSD, fusion/tracking, range analysis and measured-I/Q ambiguity/waterfall operators now live under `processing/`. |
| Truth and oracle analysis | Held-out tracking scores and oracle clock correction moved under `evaluation/`. No deployed skill imports them. |
| Transport, recordings and examples | Added `SampleBlock.timestamp_ns` and v2 neutral wire metadata. Legacy v1/SigMF translations stay at source-format adapters. New processing examples use neutral blocks; full capture callbacks remain explicitly documented instrumentation. |
| Propagation, renderers, SDR/radar generation and AirSim/geometry bridges | Generation remains source-owned. It has no MUSIC, tracking, held-out score or result-compositor imports. Legacy radar diagnostic export and old math imports are narrowly scoped API shims; generation never invokes them. |
| Distributed worker/coordinator, AMS device and DIS | Private simulation coordination may use scene/pose/path state. RF receiver data uses SC16 UDP and separate control/status; it exposes no truth to an RF skill. Device status uses receiver-facing `sc16_receiver`. The coherent MUSIC stream is a separate documented project extension. |
| Dashboard observer / replay | Only this plane joins producer telemetry, application measurements and matching camera images. Old schema-v1 combined archives remain readable; schema-v2 source/results are independent. Source computation progress does not require a result to arrive. |
| Container and launcher | Skill built from independent slim Python base with an allowlist. Only receiver config is mounted read-only, with a separate results output mount. No source `/run`, scene bundle, Docker socket, GPU or simulator assets are needed by the skill. Rootless mapping and rootful service ownership are preserved. |
| Repository entry points and compatibility | Root package uses lazy simulation exports. CLI, plotting helpers and scenario examples are orchestration/adapters, not deployed receiver applications. Old import/callback/diagnostic APIs are described as compatibility surfaces in the boundary guide. |
| Benchmarks, fixtures, figures and historical research | May deliberately join generation, estimates and truth for qualification. They are not packaged in the standalone skill. Historical reports describe the earlier implementation; current guides link this replacement. |

The import guard rejects source dependencies from receiver code and receiver
algorithms/results/evaluation from source code. It handles normal imports,
relative module aliases and literal dynamic imports. Legacy diagnostic exports
are permitted only inside their named compatibility wrappers. Tests inject
forbidden dependencies to check the guard. Computed dynamic imports remain
outside AST guarantees.

## Executed validation

| Check | Result / scope |
| --- | --- |
| Full supported CPU suite | **325 passed, 170 skipped, 3 subtests passed**; see [CPU test output](cpu-tests.txt). Optional CUDA/OptiX and unavailable dependency cases are skipped; this is not a full GPU-flight run. |
| Optional receiver/math and real service checks | [13 passed](receiver-tests.txt): MUSIC detection/calibration, noise rejection, tracking/fusion and actual neutral TCP → eight-channel MUSIC → generic commit → stubbed flight advance. |
| Standalone skill image, networking disabled | [Passed](qualification.json). The actual service receives eight channels over real loopback TCP for two windows, writes results, commits and finishes. The container contains no source dependencies or simulation modules. |
| Standalone configuration independence | 433 MHz / 1 MS/s, 8192 samples/window, two windows: different from the dashboard's 915 MHz / 2 MS/s. Both arrays detect the expected 20° bearing within 0.2°. gRPC status reflects configured carrier/rate and actual block size; unsupported acquisition control is rejected. |
| Observer HTTP and browser presentation | Two standard-library HTTP tests and four JavaScript presentation tests pass, including delayed images, out-of-order results and backward playback. |
| Architecture, compatibility and record joins | [27 final callback/architecture regressions pass](boundary-regressions.txt), including five architecture guards and the final legacy-scope regression; v1/v2 sample equivalence, forbidden metadata rejection, callback allowlist, generic delayed consumer, failure/stop/timeout, source/results mount separation, late results and old archive replay exercised. |
| Maintained documentation | Link/fragment checks pass; code-map algorithm links now point at the independent receiver modules. |

Qualification buffers are synthesized **hardware-like inputs**, not measurements
from physical hardware. The independent-image check uses no repository bind
mount; the optional receiver regression harness separately mounts the source
checkout to exercise adapters and a stubbed world. These are distinct tests.

## Reproduce the boundary checks

```bash
python3 scripts/check_architecture.py --output audit.json
docker build -f Dockerfile.dashboard --target skill -t airsim-rf:independent-skill .
docker run --rm --network none --entrypoint python airsim-rf:independent-skill \
  scripts/qualify_skill_boundary.py
```

CI runs the import guard and independent-image qualification before publishing
the service images. The standard CPU image runs the full test suite; the
dashboard runtime supplies the optional tracking stack for its service tests.

Remaining qualification work: a real coherent SDR adapter, native AMS-GRA
deployment/data-plane conformance and full GPU mission execution on deployment
hardware. The architecture now permits those adapters without changing MUSIC
or teaching the simulator which application consumes its I/Q. See the
[boundary guide](../../../docs/skill-boundary.md) for exact code ownership and
compatibility limits.
