# Reproduce airsim-rf at home

**Timing scope:** Mixed scope or architecture/reference document; each workload/table retains its stated timed operation. [Common measurement definitions](TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.



To use Docker instead of installing Python dependencies, follow
[the pull-and-test container guide](CONTAINER.md).

This standalone repository contains the RF models, I/Q generation, Python
AirSim adapter, tests and benchmarks. `sources.json` pins the external
ProjectAirSim and Sionna RT source commits. Setup downloads them into ignored
`.deps/` directories; their source and Git history are not checked into this
repository. The ProjectAirSim dependency uses a sparse checkout of its Python
client and example configuration files.

## Linux quick start

Use Python 3.12, Git, and either LLVM for CPU ray tracing or a compatible NVIDIA
GPU/driver for CUDA. Ubuntu 24.04 provides Python 3.12. Install `python3-venv`
and LLVM if they are missing. Follow
[Mitsuba's installation guidance](https://mitsuba.readthedocs.io/en/stable/src/getting_started/installation.html)
for the selected backend. Setup uses pip by default and uv when installed.

```bash
git clone https://github.com/wa200508/airsim-rf.git
cd airsim-rf
python3.12 scripts/bootstrap.py
.venv/bin/python -m pytest -q
.venv/bin/python examples/distance2gol_radar.py
.venv/bin/python benchmarks/benchmark_rf.py --backend cpu --targets 2 --fft --iterations 1000
```

The public clone requires no GitHub authentication. The bootstrap installs
both Python source packages editable alongside the RF package, using the
exact dependency versions in `requirements-lock.txt`. Existing dependency
checkouts must match their clean source pins; the script leaves modified
checkouts for you to resolve instead of resetting them.

Outputs are `distance2gol_radar.npz`, `distance2gol_radar.png`, and
`benchmark_rf.json`. The first contains raw complex IF and ADC I/Q samples;
the benchmark JSON includes every latency sample and machine/backend metadata.
The standalone radar example and benchmark need no running AirSim simulator.

On Windows, use `py -3.12 scripts/bootstrap.py` and
`.venv\Scripts\python.exe` for subsequent commands. Install the selected
Mitsuba/Dr.Jit backend's requirements. The bootstrap is portable, but fresh
installation was verified on Linux with the LLVM CPU backend.

## Measure your GPU and scene

```bash
.venv/bin/python benchmarks/benchmark_rf.py --backend cuda --targets 2 --fft --iterations 1000 --output benchmark_cuda.json
.venv/bin/python benchmarks/benchmark_rf.py --backend cuda --rf-scene builtin:simple_street_canyon --targets 2 --fft --output benchmark_cuda_street.json
```

An unavailable CUDA backend produces an error rather than silently timing CPU.
Use `--rf-scene path/to/aligned_scene.xml` for your own exported RF scene. See
[PERFORMANCE.md](PERFORMANCE.md) for measurement scope and the distinction
between a 120 Hz physics clock and RF update deadlines.

## Live ProjectAirSim

The bootstrap installs the Python client and sample configs. Build or download
a simulator separately using the upstream
[runtime guide](https://github.com/iamaisim/ProjectAirSim/blob/cfb865f29f255b15ef28ec8fdcfaa01a6b66497f/samples/projectairsim_runtime/README.md)
or [source-build guide](https://github.com/iamaisim/ProjectAirSim/blob/cfb865f29f255b15ef28ec8fdcfaa01a6b66497f/docs/development/use_source.md).
To expand the downloaded SDK checkout into full source for a native build:

```bash
git -C .deps/ProjectAirSim sparse-checkout disable
```

That downloads additional upstream assets into the external dependency
directory. The RF repository itself continues to track only its own source.

With your scene and drone running, capture one FMCW ramp:

```bash
.venv/bin/python examples/airsim_lfm_radar.py \
  --model distance2gol --scene scene_drone_sensors.jsonc \
  --sim-config .deps/ProjectAirSim/client/python/example_user_scripts/sim_config/ \
  --robot Drone1 --target-ned 10 0 -2 0.1 --target-ned 14 0 -2 0.4
```

This command loads the specified scene and leaves it paused. Those target
ranges assume the drone is at NED `(0,0,-2)` and faces north. The adapter captures
its current ground-truth antenna pose and velocity. Point targets and RF
geometry remain explicit inputs. Live AirSim execution has not been tested here,
and native RF sensor publication remains future work. The current integration
uses the Python sensor adapter.

For a sequence, control paused simulator stepping between
`AirSimRadarBridge.capture(targets)` calls and save the captures using
`save_frame()`. Preserve actual sim timestamps. Constant-velocity extrapolation
in the standalone RF frame example does not advance AirSim physics.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** use **wall seconds per simulated signal second**, not an unlabeled whole-run time. For fixed windows, divide mean service milliseconds by samples/sample-rate × 1,000. Stage costs use their parent window denominator. Geometry-only solves and analytic operation counts have no generated signal duration; a signal-time ratio is **not applicable**, unless an explicit update interval is assumed and labeled as a scheduling estimate. Unrecorded flight costs remain unknown. See [recorded normalized cases](SIGNAL_TIME_RESULTS.md).

<!-- END SIGNAL TIME CONTEXT -->
