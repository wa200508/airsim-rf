# Live AirSim-to-SDR recording

`airsim-rf-live` connects to ProjectAirSim, snapshots paused robot kinematics,
traces scene paths on CUDA/OptiX, renders private sampled inputs on CUDA, and
writes continuous timestamped I/Q with receiver noise, filtering and signed
12-bit ADC codes. It requires a running ProjectAirSim server and the optional
Python client. [Setup and the explicit P100 environment](setup.md).

Copy [the configuration example](../examples/config/live-radios.json), edit the
server address, ProjectAirSim scene/config paths, radio-to-robot mappings and
RF scene XML. The `World` constructor loads the specified simulator scene;
this command pauses and advances simulation and leaves it paused on exit.
The RF geometry must use the same origin and scale as AirSim. AirSim NED poses
and body-frame mount offsets are converted to RF coordinates `(x, -y, -z)`.
Every radio maps to a drone handle; other robot types require an adapter.

Each transmitter supplies a finite **one-dimensional complex `.npy` waveform**,
its power in watts and declared baseband frequency bounds in hertz. Samples are
used at the receiver's configured nominal rate and begin at the initial AirSim
epoch. Amplitudes are preserved; choose unit-power samples if the configured TX
power should represent average emitted power. Outside the file, the signal is
explicitly zero. Files are not looped or silently normalized. Provide enough
samples for the intended simulation duration and interpolation lookahead.
All relative paths resolve beside the configuration file.

```bash
# Run inside the CUDA-enabled environment with ProjectAirSim client installed.
python -m airsim_rf.live --config examples/config/live-radios.json \
  --output recordings/live-run --updates 10 --advance-ns 10000000

# P100: use the isolated compatibility versions and wheel-library launcher.
python scripts/basis_launch.py -m airsim_rf.live \
  --pascal-compat --config examples/config/live-radios.json \
  --output recordings/p100-live-run --updates 10 --advance-ns 10000000
```

The output directory must be new. Each receiver produces `<name>.sigmf-data`
(interleaved little-endian int16 I,Q) and `<name>.sigmf-meta`. Metadata gives the
sample offset, AirSim start timestamp, carrier, volts per count and clipping
fraction for every window. `manifest.json` records completion/failure, window
sample counts, wall milliseconds and **wall seconds per signal second**. Its
service timer includes live physics/RPC and writes, unlike the trajectory-source
benchmark. First-use compilation is included. Final metadata/checkpoint writes
are excluded; writes are not fsync-ed. A failed run retains completed recordings
and a failure label. It is not a native AMS-GRA stream or physical SDR driver.

Each update freezes geometry at the paused start epoch, then advances physics.
**Actual elapsed physics time** determines output sample count, including tick
overshoot. Narrowband Doppler evolves within that start-pose channel window;
the next window snapshots the new pose. There is no sample gap from overshoot.
The actual interval must land on an integer sample count. Otherwise recording
fails with an actionable error; choose compatible physics ticks/sample rate.
Nominal radio clocks are required. The default cap is two million samples per
update; use `--max-samples` to choose a tighter limit. Overshoot beyond the cap
stops before allocating I/Q. Large intervals also freeze geometry longer, so
select update cadence for the motion and channel dynamics.

CUDA is required for both propagation and rendering; there is no silent CPU
fallback. Out-of-range delays/Dopplers remain errors. Experimental trimming,
FFT-shape and precision controls are not part of this workflow.

The paused-world contract, overshoot handling, continuity and recording format
are tested offline. **A real ProjectAirSim server session has not been qualified
in this workspace.** First verify a small two-radio session and inspect its
manifest/recordings before expanding the scene. The measured P100 workload is
currently slower than real time; this workflow advances simulation in controlled
steps and does not promise live wall-clock streaming.
