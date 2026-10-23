# Direction Finding RF Skill extraction

The receiver application and its MUSIC numerical implementation are now owned
by [wa200508/DF-Skill](https://github.com/wa200508/DF-Skill). The new package and
container have no simulator, propagation or airsim-rf dependency.

DF-Skill source pin: `270bfacb6ac933f5c60599aab3edf39489978c45`.

- [Initial standalone CI](https://github.com/wa200508/DF-Skill/actions/runs/39995664041)
  passed the real TCP/HTTP/gRPC receiver and exact I/Q archive/replay check, plus
  five numerical/service tests, and published the image.
- [Anonymous-pull verification](https://github.com/wa200508/DF-Skill/actions/runs/39996201636)
  passed, including another complete test/build/publication and anonymous GHCR pull.
- Root license is Apache-2.0, matching the verified public Hello World Starter
  Kit RF skill. Original MIT and upstream Squall Apache attribution are retained
  in DF-Skill. airsim-rf remains MIT licensed.
- Local `skills/music.py`, `processing/music.py` and `dashboard_skill.py`
  are compatibility re-exports, not second implementations.
- Default scenario uses an immutable external image with independent consumer
  revision policy. Simulator/RF revision matching and immutable image-ID pinning
  remain enforced. The old skill build target/tag is a registry-image alias.
- Cross-boundary sample archive tests now import the external receiver class.
  The existing calibrated complex-voltage, timestamp and window-ack contract is
  unchanged; `music_db` remains an observer compatibility field.
- Updated application branding is Direction Finding RF Skill. MUSIC remains
  documented as its current estimator rather than implying a new algorithm.
- Local execution workspace was unavailable during extraction; changes were
  authored through the GitHub connector and tested by repository CI. This report
  does not claim a local GPU/native flight or complete new AMS-GRA conformance.

See [ownership, deployment and migration instructions](../../../docs/direction-finding-skill.md).
