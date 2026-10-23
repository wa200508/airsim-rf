# Bulk receiver I/Q capture and replay qualification

The dashboard now archives exact receiver-facing `cf32_le` complex volts in a
separate, source-neutral `iq/` directory. A standalone reader/replayer feeds the
existing TCP v2 RF-skill interface without a simulator or propagation backend.
See [capture/replay instructions and SDR options](../../../docs/iq-replay.md).

## Evidence

- [Full CPU suite](cpu-tests.txt): 364 passed, 158 skipped, 3 subtests passed.
- [Capture/scenario tests](capture-replay-tests.txt): 20 passed. Tests include
  byte-exact complex samples and timestamps, SigMF schema/library reading,
  corrupted/truncated data, discontinuous timing, channel alignment, interrupted
  disk writes, partial-prefix recovery, paced/subset TCP replay and disk checks.
- The actual Sionna CPU receiver adapter's output is archived and read back
  byte-for-byte. This is a propagated scene fixture, not just a generated tone.
- TCP replay into unchanged MUSIC processing produces identical bearings,
  MUSIC curves, inter-element phase and receiver spectra to the original input.
  That fixture includes continuously evolving sample phase/frequency.
- [Standalone skill container](standalone-skill.json): eight channels, two
  windows at 433 MHz / 1 MS/s, real TCP and result journal. Archived samples
  replay to the unchanged skill with identical bearing outputs. Simulation,
  propagation dependencies and truth are absent from the image.
- [Installed-wheel checks](wheel.json) pass outside the source checkout,
  including the new neutral replay module and packaged scenario discovery.
- [Architecture audit](architecture.json), documentation links and all seven
  JavaScript dashboard presentation tests pass.

Archive capture is enabled by `mission.record_iq` (default true). The prepared
initial window is saved only once. Each complete generated channel group is
journaled before live delivery; consumer success is not a condition for saving
acquisition data. The wider source archive retains scenario inputs separately.

## Scope

This qualifies CPU propagation, persistence, the neutral wire contract and
unchanged MUSIC consumption. It does not claim a new local GPU flight benchmark,
third-party viewer/GNU Radio integration test, physical SDR test, or guaranteed
power-loss durability. Writes are flushed per window but not fsync-ed. A failed
archive requires explicit partial-prefix reading; published corruption fails.

At eight channels / 2 MS/s the lossless format costs 128 MB per simulated second,
or 15.36 GB for the default 120-second mission. No decimation or waveform changes
are used to reduce that size. Storage bandwidth and capture time remain real
costs; the producer records cumulative I/Q write time and bytes separately.
