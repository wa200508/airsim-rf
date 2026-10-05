# Canonical AMS-GRA starter-kit compatibility

**Runtime context (2026-10-05):** Protocol/model compatibility is separate from real-time execution and complete distributed flight qualification. See [current runtime and wall-clock costs](RUNTIME_STATUS.md) for comparable measurements, hardware, exclusions and ten-minute estimates.

Checked on 2026-10-03 against the sources supplied for this integration:

- Documentation: https://open-arsenal.gitlab.io/ams-gra/hello-world-sk/getting-started/
- Component group: https://gitlab.com/open-arsenal/ams-gra/hello-world-sk
- Release: `v2026.09.01` (published 2026-09-30).

The GitLab URL is a **group of repositories**, rather than a single Git repository.
`sources.json` now records canonical GitLab URLs and individual commit pins for
the components. The earlier GitHub umbrella snapshot is retained as provenance.

The canonical Squall source at `b3d4aa780de954e39bf2c6dbd7b0121f699822b4`
matches the originally tested GitHub source at
`b1015728f904c799fa0c07489fce48e78f67845f` for these eight integration files:

| Boundary | Compared files |
| --- | --- |
| gRPC control | `crates/rf/proto/squall_rf.proto`, `SquallGrpcClient.cc` |
| Native I/Q delivery | `SquallDataMEL.cc` |
| RX job and discovery behavior | `SquallC2MEL.cc`, `SquallVADB.h` |
| Deployment configuration | `compose.yaml`, `config/couloir.toml`, `config/squall-rf-mel-profile.json` |

The C++ files are under `interfaces/squall-rf-mel-impl/src/`. SHA-256 digests are
recorded in `sources.json` under `ams_gra.canonical_audit`. The RF MEL, common MEL,
AMS VITA and AMS math interface repositories also have identical commit IDs to
the headers used for the native interoperability check. No RF runtime changes or
protobuf regeneration are needed for this canonical source revision.

The published MFA tutorial illustrates VITA packetization as pseudocode. The
checked Squall runtime sends bare little-endian interleaved SC16 UDP datagrams,
and its native MEL decoder expects that format. Our backend follows that tested
implementation. gRPC/UDP compatibility with Squall is an implementation-level
integration check; it does not establish full AMS-GRA IDD conformance.

The getting-started install script and Worldview manifest have changes relative
to the GitHub snapshots: image identification in the installer and map style/file
settings in Worldview. The upstream installer requires Podman and podman-compose.
[DISTRIBUTED.md](DISTRIBUTED.md) gives a separate Docker image-loading and Compose
procedure, loads the canonical bundle's `.env`, and preserves its current map
settings. The Docker overlay was validated using all seven canonical component
Compose manifests. This validation checks configuration, not a running full kit.

The existing validation remains: 28 Python tests, a real native C++ MEL callback
through Couloir, and a three-container CPU simulation with 42 timestamped I/Q
blocks. Live AirSim, GPU deadlines, full platform UCI reporting and Podman GPU
deployment remain unvalidated or unimplemented as described in the distributed
guide.
