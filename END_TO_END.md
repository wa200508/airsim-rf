# End-to-end RF tests

On `profiling/p100`, the optimized CPU/CUDA basis renderer is connected to
`SDRNetworkReceiver`. The end-to-end runner exercises **moving-platform truth
→ AirSim mount bridge → real terrain multipath → private arbitrary sampled
waveforms → all-path Doppler rendering → thermal noise → persistent receiver
filter → 12-bit ADC → SC16 serialization → HTTP consumer → file readback**.
Every channel is recomputed each update. No scene paths are cached across
updates, discarded by strength, or replaced with synthetic stress-test paths.

## Run the tests

```bash
git switch profiling/p100
.venv/bin/python -m pytest tests/test_end_to_end.py tests/test_sdr.py tests/test_distributed.py -q
```

The integration tests compare the scene-derived basis output with the direct
all-path renderer over several moving epochs. A separate split/unsplit test
checks receiver filter continuity. Another test runs real terrain propagation,
two independent transmitters, two receivers and four consecutive receive
windows through an actual localhost HTTP consumer, validates the SC16 records,
and checks that no samples are skipped or duplicated.

The distributed tests separately exercise the existing radar worker’s native
AMS-GRA gRPC control, UDP data and coordinator. **The new continuous SDR/basis
pipeline is not yet connected to that distributed worker protocol.** Neither
suite stands in for a live AirSim + distributed continuous-SDR fleet test.

## Collect complete RF-pipeline timings

```bash
# Complete requested fleet: 100 independent TX, ten RX; CPU propagation/rendering.
.venv/bin/python benchmarks/benchmark_end_to_end.py \
  --tx 100 --rx 10 --iterations 30 --warmup 3 \
  --output results/end_to_end/cpu-100tx-10rx

# Your smaller flight configuration: ten TX, four RX.
.venv/bin/python benchmarks/benchmark_end_to_end.py \
  --tx 10 --rx 4 --iterations 30 --warmup 3 \
  --output results/end_to_end/cpu-10tx-4rx

# On the P100: same full scene-to-consumer pipeline, CuPy rendering.
.venv/bin/python scripts/basis_launch.py benchmarks/benchmark_end_to_end.py \
  --renderer basis-cuda --tx 100 --rx 10 --iterations 30 --warmup 3 \
  --output results/end_to_end/p100-100tx-10rx
```

Use the profiling container’s Python instead of `.venv/bin/python` where
appropriate. Run the P100 command with the container entrypoint overridden to
`python` and `--gpus all`, using the existing CUDA-enabled profiling image setup
in [P100_BASIS_PROFILING.md](P100_BASIS_PROFILING.md). The selected rendering
backend fails explicitly if CUDA is unavailable; it never silently falls back.

Each output directory must be new. It contains `measurements.json`, `REPORT.md`,
and local `captures/*.sc16` files. Publish the JSON and Markdown, rather than
all raw I/Q. `REPORT.md` puts processing steps in columns with median ± sample
standard deviation and a separate p95 table. The synchronized outer timer
includes source generation, mount snapshot mapping, path solving/export,
rendering, receiver processing, serialization, loopback transport,
acknowledgement and consumer write/readback. Writes are not fsync-ed. The first
capture is recorded separately; warmup and setup are excluded from steady-state
statistics. The runner does not assert that latency is below 8.333 ms: it reports
actual deadline misses and wall/simulated-time ratio.

At 2 MS/s and 120 Hz, windows alternate **16,667 / 16,666 / 16,667 samples**.
Their timestamps follow cumulative integer sample counts, so the stream is
continuous. Receiver filter state persists; it is not restarted with a synthetic
warmup for each capture. Input buffers retain actual overlapping history and
lookahead. A new private sampled buffer is allocated for every directed link;
no input transforms are shared between receiver jobs. Receiver jobs execute
**sequentially on one device**, so the measurements credit no unmeasured
one-GPU-per-receiver parallelism.

The propagation budget is **1,028 diffuse attempts per directed link**, drawn
from both antenna patterns, plus LoS/specular candidates. Occlusion and ray
misses determine the number of physical paths. JSON records those counts for
every receiver and epoch. This differs from the renderer stress test’s **1,028
valid paths per link**. The scene has 800 terrain triangles and the documented
synthetic dielectric/scattering material; no extra bounce depth is introduced.
Channels stay fixed over a window, with narrowband Doppler phase evolving at
every sample. Both basis backends retain their declared 100 µs delay bound,
±2,500 Hz Doppler bound, 32 interpolation taps and 2,048-sample blocks.
Paths outside those limits fail instead of being clipped. Source/receiver clocks
are nominally equal; clock-rate resampling remains unqualified.

**Sionna propagation runs on LLVM CPU, including in the P100 command.** The
installed Sionna/Dr.Jit GPU backend cannot run on the P100. Therefore this is a
hybrid CPU-propagation/GPU-rendering measurement, not a GPU-only fleet claim.

## Run with actual ProjectAirSim physics and RPC

By default, the runner uses a deterministic curved-trajectory source exposing
the same paused-world/robot API that `AirSimSDRBridge` consumes. It executes the
real RF pipeline and consumer, but **does not exercise the AirSim executable,
physics engine or network RPC**.

Start a ProjectAirSim server and install the optional ProjectAirSim Python
client. Supply a JSON mapping every `txN` and `rxN` to a live drone:

```json
{
  "address": "127.0.0.1",
  "scene": "scene_config.jsonc",
  "sim_config": "/path/to/ProjectAirSim/client/python/example_user_scripts/sim_config",
  "robots": {"tx0": "Drone1", "rx0": "Drone2"}
}
```

```bash
.venv/bin/python benchmarks/benchmark_end_to_end.py \
  --tx 1 --rx 1 --iterations 30 --warmup 3 \
  --airsim-config live-radios.json \
  --output results/end_to_end/live-airsim
```

The live server must advance and pause at each requested RF epoch on the 500 ns
sample grid. The runner rejects an overshoot or gap rather than dropping I/Q.
A server configuration whose physics ticks cannot pause at those epochs needs
truth interpolation/scheduling integration before this live test can pass.
The RF terrain must also agree with the AirSim scene coordinates; this runner
does not import the AirSim world geometry. Drone flight controllers and paths
must be configured in the live scene. Live mode has not been run in this cloud
workspace; it fails without a server and never substitutes trajectory data.

An end-to-end distributed AirSim/AMS-GRA continuous-I/Q demonstration still
requires those live scheduling and SDR-worker integrations. This document names
that remaining scope rather than calling the automated RF test a completed
simulation-plane deployment.
