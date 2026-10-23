# Live AirSim-to-SDR recording

For receiver applications use `on_samples(SampleBlock)` or the neutral TCP
contract. The legacy full-capture callback is simulation instrumentation. See
the [simulation/skill boundary](skill-boundary.md) for the separation from
recording, truth and algorithm evaluation.

Start with the [shared-scene quickstart](quickstart.md) for the current complete
installed-package workflow. The [scenario-to-I/Q walkthrough](scenario-to-iq.md)
adds propagation choices, CPU processing and a live callback.

`airsim-rf-live` connects to ProjectAirSim, snapshots paused robot kinematics,
traces scene paths on CUDA/OptiX, renders private sampled inputs on CUDA, and
writes continuous timestamped I/Q with receiver noise, filtering and signed
12-bit ADC codes. It requires a running ProjectAirSim server and the optional
Python client. [Setup and supported execution environments](setup.md).

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
service timer includes live physics/RPC, writes and any processing callback, unlike the trajectory-source
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

**Diffuse temporal-coherence limitation:** configurations without an explicit
propagation section retain `diffuse-angular`, which includes
first-order diffuse paths sampled by antenna-relative angular rays. As radios
move, those rays can hit different surface points even with the same seed.
Continuous sample timestamps and persistent receiver-filter state do not imply
persistent diffuse scatterers or physically qualified temporal speckle. The
[measured diffuse audit](../results/reviews/diffuse-stability-20261012/REPORT.md)
found substantial phase changes beyond the previous snapshot's local-Doppler
continuation. Direct/specular qualification does not cover this behavior; avoid
interpreting moving diffuse Doppler spectra as validated sensing observables.
New generated starters explicitly use `specular`. The opt-in `diffuse-surface`
mode now passes a [controlled moving I/Q check](../results/reviews/moving-iq-20261014/REPORT.md)
against a coherent path sum and continuous filter. This checks rendering of the
traced paths, not physical diffuse statistics. See [mode choices](scenario-to-iq.md).

CUDA is required for both propagation and rendering; there is no silent CPU
fallback. Out-of-range delays/Dopplers remain errors. Experimental trimming,
FFT-shape and precision controls are not part of this workflow.

The paused-world contract, overshoot handling, continuity and recording format
are tested offline. A real pinned **ProjectAirSim Runtime container** with two
stationary non-physics robots has now passed the P100 live smoke test: ten windows,
240,000 complex samples and 0.120 signal seconds. [Qualification evidence](../results/reviews/project-quality-20261009/live-server/REPORT.md).
A subsequent [moving-flight qualification](../results/reviews/live-motion-20261011/REPORT.md)
passed with the real Fast Physics controller: approaching and receding TXs,
0.480 signal seconds per run, and within-window direct-path Doppler checked
against actual velocity. A [phase/cadence and ground-reflection follow-up](../results/reviews/live-phase-20261011/REPORT.md)
checked boundary I/Q against the piecewise-channel model at 6–48 ms intervals.
Small pose-refresh phase corrections remain and grow with longer windows; exact
phase continuity under acceleration is not guaranteed. A [two-drone follow-up](../results/reviews/moving-receiver-20261011/REPORT.md)
also passed direct/specular checks with independent TX and RX motion, including
lateral RX velocity. A [moving-I/Q follow-up](../results/reviews/moving-iq-20261014/REPORT.md)
checks fixed-surface diffuse rendering and direct-path disappearance/return behind
an RF-only screen. A [turning-mount check](../results/reviews/turning-mounts-20261015/REPORT.md)
also passes for two yawing drones with nonzero radio offsets and direct paths.
[Directional pattern rotation](../results/reviews/directional-turns-20261015/REPORT.md)
also passes a matched-flight gain check. [Combined multipath turns](../results/reviews/turning-multipath-20261016/REPORT.md)
pass controlled specular and directional fixed-surface cases. The [shared geometry closure](../results/reviews/priority1-20261020/REPORT.md)
now qualifies matching nonprimitive collision/RF meshes and combined turning,
obstruction and first-order reflections. General diffuse transitions and arbitrary
existing-world extraction remain open.
The measured workloads are slower than real time; controlled stepping does not
promise live wall-clock streaming.

The motion qualification helper accepts `--duration-ms` to set total capture
time, provided it is divisible by `--window-ms` (6, 12, 24 or 48 ms). It defaults
to 480 ms, matching the cited motion reports. Longer captures also extend the
flight command and source waveform, and can expose long-run timing or channel
stability issues that a short integration check cannot. The helper uses CUDA for
RF propagation and rendering; `scripts/inspect_live_recording.py` and the
recording analyzers can inspect completed captures on CPU.

A [4.8-second two-drone specular capture](../results/reviews/longrun-20261017/REPORT.md)
now passes 400-window continuity, coherent I/Q and boundary checks, extending the
short-flight evidence by ten times. The inspector and coherent-I/Q analyzer
process sample data one window at a time; channel and recording metadata still
grow with capture length. A [longer turning and screen follow-up](../results/reviews/longrun-turns-20261017/REPORT.md)
adds a 9.6-second direct-path turn with offset mounts and a separate 4.8-second
screen capture. The analyzer now checks each path-count transition individually,
so aggregate boundary error cannot hide a bad disappearance or return. These
earlier controlled cases do not qualify diffuse-path transitions or arbitrary
terrain. Combined turning/obstruction with specular reflection is now qualified
by the shared-geometry closure linked above.

## Complete two-radio first run

Install [the CUDA environment](setup.md#live-cuda-dependencies), or use the
P100-compatible image in [setup](setup.md#p100-profiling). The first smoke scene
uses two stationary, non-physics robots and a flat ground plane: NED
`(-20, 0, -20)` and `(20, 0, -20)` become RF `(-20, 0, 20)` and `(20, 0, 20)`.
It tests the real server/API clock and RF recording, not vehicle dynamics.

Create all inputs in a new directory:

```bash
python examples/prepare_live_example.py --output recordings/live-inputs
python -m airsim_rf.live --config recordings/live-inputs/radios.json --check-config
```

The generator writes a unit-power +150 kHz complex CW waveform: 500,000 samples
at 2 MS/s, covering 0.25 s; `radios.json`; a ground XML/PLY; and two robot/scene
configuration files. The RF material is synthetic. The waveform duration leaves
margin for ten requested 10 ms steps with the scene's 3 ms physics-clock ticks.
`--check-config` requires neither GPU nor server. The newer
`airsim-rf preflight` also checks the planned capture counts, source duration,
physics-clock alignment and optional output space. The live runner performs that
plan check before connecting. It checks finite source values,
frequency bounds and local files, and prints source/geometry/configuration hashes.

The standalone **ProjectAirSim Runtime** uses the actual ProjectAirSim server and
client APIs without Unreal. It provides a flat ground host; Sionna separately
traces that matching RF plane on the GPU. Use Unreal only when rendered sensors
or detailed simulator-world geometry are required. Such geometry must also be
exported/aligned in the RF scene. [Pinned Runtime source instructions](https://github.com/iamaisim/ProjectAirSim/blob/cfb865f29f255b15ef28ec8fdcfaa01a6b66497f/samples/projectairsim_runtime/README.md).

```bash
scripts/build_airsim_runtime.sh
docker run --rm -d --name airsim-rf-runtime \
  -p 127.0.0.1:8989:8989 -p 127.0.0.1:8990:8990 airsim-rf:airsim-runtime
```

With the server running, record ten updates. In the P100 image, mount this
checkout and use host networking to reach the loopback-published server ports:

```bash
docker run --rm --gpus device=0 --network host --tmpfs /.drjit:rw,mode=1777 \
  --user "$(id -u):$(id -g)" -v "$PWD:/work/repo" -w /work/repo \
  -e PYTHONPATH=/work/repo/src -e MPLCONFIGDIR=/tmp/matplotlib \
  --entrypoint /opt/airsim-rf/.venv/bin/python airsim-rf:p100-modern-gpu \
  scripts/basis_launch.py -m airsim_rf.live --pascal-compat \
  --config recordings/live-inputs/radios.json --output recordings/live-first-run \
  --updates 10 --advance-ns 10000000
```

Success means `manifest.json` has `status: complete`, ten rows, increasing
continuous timestamps and sample offsets, and one receiver data/metadata pair.
At 3 ms tick overshoot, a requested 10 ms step can become 12 ms: 24,000 samples
per update, 240,000 total and 0.120 signal seconds. Inspect actual elapsed time
rather than requiring that count for every simulator clock implementation.
Values are signed 12-bit codes in little-endian int16 I/Q pairs. Convert back
to input-referred volts using each window's recorded volts-per-count.

The manifest now hashes waveform files, RF XML/mesh and simulator configuration
files alongside dependency/backend versions. Relative `sim_config` and RF/source
paths resolve beside `radios.json`. Keep server logs with the recording evidence.
After inspection, stop the smoke server with `docker stop airsim-rf-runtime`.


Inspect the finished recording in the scientific Python environment:

```bash
python scripts/inspect_live_recording.py recordings/live-first-run
```

The inspector verifies byte/sample counts, signed ADC range, per-window metadata
and timestamp continuity. It also reports the final-window spectral peak. For
the +150 kHz smoke input, compare the peak with 150,000 Hz within its reported FFT
bin spacing; this is a spectral sanity check, not calibrated analog validation.

## Optional shared OpenUSD geometry

The [OpenUSD geometry workflow](openusd-workflow.md) describes an optional
`geometry_bundle` configuration alongside `rf_scene`. It adds bundle integrity,
simulator pose/scale readback, preserved RF object identities and per-window
geometry provenance. It is restricted to static environment geometry with moving
radios. The [geometry closure qualification](../results/reviews/priority1-20261020/REPORT.md)
passes nonprimitive collision/RF intersections and complete moving/turning
recordings with first-order reflection and obstruction together. Generated GLB
meshes use the same USD triangles as RF. Environment edits require a new bundle,
scene and receiver at a recording boundary; continuous dynamic obstacles remain
unsupported. Actor creation requires explicit `geometry_placement: "spawn"` or a
separate placement call; the default mode only reads existing actors.
