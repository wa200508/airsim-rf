# Active radar TX/RX correction — 2026-10-23

The extracted radar skill had been a receive-only processor. It now owns the
FMCW operating mode and commands both transmission and reception through a
hardware-neutral transceiver adapter. Its mode is separate from scene physics,
and the simulator does not import the skill or detector.

## Behavior

- Scenario operating parameters are together in radar-mode.json: waveform,
  conducted TX power, PRI, ADC gate and IF gain. radios.json retains physical
  antenna, filter, noise, ADC transfer and target/RCS settings.
- The external skill validates its requested mode, configures the radio over
  real HTTP, verifies configuration identity, then enables TX and RX.
- A new adapter starts disabled. Commands apply at window boundaries. TX off
  with RX on removes target echoes while retaining noise/ADC behavior; RX off
  pauses acquisition. Configuration changes require a new stream session.
- Normal skill termination requests TX and RX off. Explicit --replay rejects
  active-control options and issues no transmitter commands.
- The same contract supports physical adapters, but no TI/DCA1000 hardware
  driver or native AMS-GRA MEL transmit binding is implemented.

## Evidence

- Standalone NumPy-only environment: **13 tests passed**, including actual
  HTTP configure/start/mute/stop, TCP I/Q, result files, exact recording/replay
  and verification that replay sends no radio commands.
- [Standalone source CI](https://github.com/wa200508/Radar-skill/actions/runs/40022751846): passed.
- [Public immutable active-skill image release](https://github.com/wa200508/airsim-rf/actions/runs/40022797722):
  passed; offline qualification, fresh anonymous pull and pulled-image replay.
- Focused source/skill/scenario/dashboard checks: **55 passed**, including
  actual Sionna target echoes, a commanded **35 MHz sweep at 78 GHz** overriding the
  model's default, range/Doppler detection, and exact recorded samples.
- Actual radio capture with TX off and noise disabled: zero analog echo power.
  A conducted TX increase from 6 to 12 dBm gives the expected 3.981x echo power.
- Full available CPU suite: **358 passed, 189 skipped, 3 subtests passed**,
  95.35 s, exit 0. GPU/SDK-dependent checks are among the skips. An initial run
  hit a native shutdown SIGSEGV after its passing summary; the baseline and
  unchanged full rerun exited cleanly. This is not GPU flight qualification.
- [Cross-repository CPU Sionna CI](https://github.com/wa200508/Radar-skill/actions/runs/40023501548): passed with actual propagation and TX/RX commands.
- **9 dashboard JavaScript tests**, architecture import walls and maintained
  documentation links passed.

## Dashboard release qualification

The preceding dashboard pipeline failed its camera/body timestamp comparison:
body poses were sampled only at 120 ms stepping endpoints, while camera frames
could fall 27 ms between them. The qualifier now subscribes to native timestamped
actual_pose telemetry at physics cadence. It preserves the existing 3 ms
camera/body comparison threshold and does not interpolate or relax that check.
The native software-rendered CI gate must verify this change; no successful
new full GPU/native flight is asserted by the CPU tests above.

The first release of the final RF tree timed out before tests while downloading
GNU Radio packages from the hosted runner's Azure HTTP mirror. CI now uses
Ubuntu HTTPS mirrors, caches the downloaded packages, and allows 25 minutes for
the unchanged stock GNU Radio interoperability gate. No test is bypassed.
