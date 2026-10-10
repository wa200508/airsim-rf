# Setup

- [Reproduce](#reproduce)
- [Container](#container)
- [P100 Profiling](#p100-profiling)
- [P100 Basis Profiling](#p100-basis-profiling)

<a id="reproduce"></a>

## Reproduce airsim-rf at home



To use Docker instead of installing Python dependencies, follow
[the pull-and-test container guide](setup.md#container).

This standalone repository contains the RF models, I/Q generation, Python
AirSim adapter, tests and benchmarks. `sources.json` pins the external
ProjectAirSim and Sionna RT source commits. Setup downloads them into ignored
`.deps/` directories; their source and Git history are not checked into this
repository. The ProjectAirSim dependency uses a sparse checkout of its Python
client and example configuration files.

### Linux quick start

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

### Measure your GPU and scene

```bash
.venv/bin/python benchmarks/benchmark_rf.py --backend cuda --targets 2 --fft --iterations 1000 --output benchmark_cuda.json
.venv/bin/python benchmarks/benchmark_rf.py --backend cuda --rf-scene builtin:simple_street_canyon --targets 2 --fft --output benchmark_cuda_street.json
```

An unavailable CUDA backend produces an error rather than silently timing CPU.
Use `--rf-scene path/to/aligned_scene.xml` for your own exported RF scene. See
[PERFORMANCE.md](archive/planning.md#performance) for measurement scope and the distinction
between a 120 Hz physics clock and RF update deadlines.

### Live ProjectAirSim

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

<a id="container"></a>

## Run the tests in a container



For the GPU profiling branch, [P100_PROFILING.md](setup.md#p100-profiling) provides
a pinned-base profiling image, host launcher and results-publication helper.

The CPU image bundles Python 3.12, LLVM 19, the pinned Sionna RT and ProjectAirSim
Python SDK, and this project's code and tests. Tests run as an unprivileged user
and require no GPU, running AirSim instance, or network access. This is the RF
test environment; a native AirSim/Unreal simulator is installed separately.

### Pull and test

After the repository's **Test and publish container** workflow succeeds:

```bash
docker pull ghcr.io/wa200508/airsim-rf:latest
docker run --rm --network none ghcr.io/wa200508/airsim-rf:latest
```

The default command runs the entire pytest suite and returns a nonzero exit code
on failure. Published images currently target Linux x86-64 (`linux/amd64`).
Docker Desktop supports this image; ARM hosts may need `--platform linux/amd64`
and emulation, which has not been tested here. Container timing under emulation
should not be used to judge real-time RF performance.

GitHub may initially create a private package even for a public repository.
For anonymous pulls, set the `airsim-rf` package's visibility to **Public** in
your GitHub package settings. If it stays private, authenticate with
`docker login ghcr.io` using a token with `read:packages`.

Each published build also gets a `sha-<full repository commit>` tag. Use that
tag, or the registry digest, to reproduce a particular image rather than the
moving `latest` tag.

### Examples and benchmarks

Override the default command to generate radar I/Q. Mount a writable output
directory to keep the recording and plot after the container exits:

```bash
mkdir -p output
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/output:/work" ghcr.io/wa200508/airsim-rf:latest \
  python /opt/airsim-rf/examples/distance2gol_radar.py

docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/output:/work" ghcr.io/wa200508/airsim-rf:latest \
  python /opt/airsim-rf/benchmarks/benchmark_rf.py \
  --backend cpu --targets 2 --fft --iterations 1000 --output /work/timing.json
```

These bind-mount commands use a Linux/macOS shell. On Docker Desktop, adapt the
host path for your shell and omit `--user` if needed. The image includes the
CPU backend; NVIDIA/CUDA operation is outside this container's validated scope.
See [PERFORMANCE.md](archive/planning.md#performance) for timing limitations.

The [COTS SDR lab](architecture.md#cots-sdr-lab) runs two beacons and two passive receivers
through shared terrain propagation, a Pluto-class front end and I/Q export:

```bash
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/output:/work" ghcr.io/wa200508/airsim-rf:latest \
  python /opt/airsim-rf/examples/pluto_esm_drones.py --output-dir /work/pluto_esm
```

### Build locally

```bash
git clone https://github.com/wa200508/airsim-rf.git
cd airsim-rf
docker build -t airsim-rf:test .
docker run --rm --network none airsim-rf:test
```

Builds need internet access to download the exact external source commits and
Python dependencies. Running the tests afterward needs no downloads. An optional
BuildKit secret named `proxy_ca` lets an HTTPS inspection proxy supply its CA
bundle during dependency installation without putting it in the image.

### Automatic publishing

`.github/workflows/container.yml` builds on pull requests, pushes to `main`,
version tags (`v*`), and manual dispatch. It runs offline tests and the radar
example before pushing the same image to GHCR. Pull requests only build and
test. Main publishes `latest` and a commit tag; version tags publish their tag
and a commit tag. Publishing uses the workflow's `GITHUB_TOKEN` with
`packages: write`; no stored registry password is needed.
## Distributed simulation

The same image can run `airsim-rf-worker` and `airsim-rf-coordinator`.
See [DISTRIBUTED.md](architecture.md#distributed) for the offline two-worker demonstration,
one-GPU-per-receiver deployment, and the AMS-GRA MEL integration.

<a id="p100-profiling"></a>

## Run and publish P100 profiling measurements



**Runtime context (2026-10-05):** The older current-stack/legacy collectors have separate propagation and renderer scopes. Use the optimized basis collection for the current comparable continuous-I/Q timing. See [current runtime and wall-clock costs](archive/runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

For the **updated Doppler-basis FFT test on `profiling/p100`**, use
[the CuPy/CUDA 12.2 P100 guide](setup.md#p100-basis-profiling). Its one-command run
measures 100 private transmitter streams, all-valid paths and complete 120 Hz
sample windows. The current Dr.Jit stack rejects SM 6.0; the new renderer
therefore uses CuPy directly. The general current-stack/legacy guides below
remain separate propagation and older renderer references.

Branch: **`optimization/direct-path-renderer`**. This branch extends the
profiling kit with [direct path LLVM/CUDA recurrence](rendering.md#direct-path-rendering).
The collector compares NumPy, direct and [batched rendering](rendering.md#batched-rendering),
and separately measures private arbitrary sampled I/Q. Receiver filtering and
ADC remain CPU work; the batched backend groups transfers across independent
jobs. Defaults keep per-link diagnostics enabled.

### Measured P100 compatibility and results

The pinned Sionna RT 2.2 / Mitsuba 3.9.1 / Dr.Jit 1.5 stack does **not** run
on this P100 (compute capability 6.0). The standard launcher below retains those
pins and is not a working P100 recipe. An isolated legacy stack was needed:
Sionna 0.19.2, Mitsuba 3.5.2, Dr.Jit 0.4.6, TensorFlow 2.15.1 and Python 3.11.

- [Initial compatibility failure](../results/profiling/p100-quick-20261003-2005/REPORT.md)
- [Full legacy profiling collection](../results/profiling/p100-legacy-full-20261003/REPORT.md)
- [Propagation-only simultaneous transmitter scaling](../results/profiling/p100-legacy-scaling-20261003/REPORT.md)
- [Legacy harness and reproduction instructions](../scripts/p100_legacy/README.md)

These measurements use legacy native propagation in place of the branch's
custom solver. The full collection retains the original host I/Q/receiver
chain; scaling removes that chain. They establish execution and performance,
not physical or numerical equivalence to the current solver. Production code
and dependency locks are unchanged. Large I/Q files and profiler traces remain
local under ignored `raw/` directories; reports, small metrics and logs are
committed.

### One command on the Docker host

Requires Linux x86-64, Docker with NVIDIA Container Toolkit, a P100 visible to
the host, and git. Host driver libraries are supplied by the NVIDIA runtime;
installing a CUDA toolkit alone does not expose a GPU to a sandbox.

```bash
git clone --branch optimization/direct-path-renderer --single-branch https://github.com/wa200508/airsim-rf.git
cd airsim-rf
nvidia-smi
bash scripts/run_p100_docker.sh --run-id p100-20261004
```

Choose a unique run ID. Existing directories are never overwritten. The launcher
builds a small profiling layer over an immutable, already-published dependency
image, overlays this branch's code, and installs pinned `nvtx==0.2.13`. It mounts
`results/profiling` writable and runs as your host UID/GID. No privileged Docker
mode, Docker socket bind mount or NVIDIA driver reconfiguration is requested.
Builds require internet; the measurement runner itself downloads nothing.

Default GPU is device 0. Select another physical index or UUID with
`RF_PROFILE_GPU=... bash scripts/run_p100_docker.sh ...`.
CPU quota and memory limits actually seen inside the container are recorded.
The default Dr.Jit thread count is two; change with `--threads` if appropriate.

The full run can take **15–30 minutes or longer**, because the comparison also runs the original 100-TX
NumPy renderer. A shorter initial check is:

```bash
bash scripts/run_p100_docker.sh --quick --run-id p100-quick-20261004
```

`--quick` reduces epoch counts, not the default 1,028 diffuse attempts/link or
4,096 output samples. The resulting few-epoch p95 is a smoke statistic, not a
reliable latency-tail measurement. Use a different run ID for the full run.

### If Sol is already inside a GPU sandbox

If the sandbox already has GPU passthrough and the pinned Python environment,
run the collector directly rather than starting nested Docker. For a new
checkout, use the existing bootstrap (Python 3.12 and the native libraries
listed in Dockerfile are required):

```bash
python3.12 scripts/bootstrap.py
.venv/bin/python scripts/run_gpu_profile.py --run-id p100-20261004
```

For a container built from this branch with the project at `/opt/airsim-rf`:

```bash
python /opt/airsim-rf/scripts/run_gpu_profile.py \
  --output-root /work/results --run-id p100-20261004
```

Bind `/work/results` to the host checkout's `results/profiling`. Without a bind
mount, the artifacts disappear with a disposable container. If `nvidia-smi`
cannot see the GPU inside the sandbox, its host must expose it first using
`--gpus` and `NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics`; installing
Python packages cannot fix missing device passthrough.

The P100 is Pascal / compute capability 6.0 and has no RT cores. If adding a
CUDA toolkit, choose a Pascal-compatible CUDA 12.x version; CUDA 13 removes
Pascal offline compilation support. The scripts leave pinned dependencies and
driver settings unchanged and verify a real CUDA/OptiX terrain solve. A
successful `dr.has_backend(CUDA)` check alone is insufficient.

### What is collected

The runner performs these tasks sequentially:

1. Hardware/runtime/source metadata, installed package versions, source file
   SHA-256 hashes and optional one-second `nvidia-smi` telemetry.
2. A real first-order terrain CUDA/OptiX smoke solve with kernel-history proof
   of CUDA and OptiX execution, finite coefficients and retained paths.
3. Renderer correctness tests, including CUDA analytic-equation and continuous
   Doppler checks when GPU preflight succeeds.
4. Paired **unprofiled CPU and CUDA** one-receiver benchmarks for 2 and 100 TX,
   for NumPy, direct LLVM/CUDA recurrence and batched replay.
   Defaults: 20 warmups / 200 epochs for 2 TX, and 5 warmups / 30 epochs for
   100 TX. Same terrain, sample/ray budgets, clocks and waveform definitions.
5. Separate instrumented runs: 3 warmups / 5 timed epochs, Dr.Jit CUDA-event
   history and optional NVTX. `--quick` uses 1 warmup and 3/2 unprofiled epochs
   for small/large cases, with 2 timed epochs in each profile.
6. Optional short Nsight Systems runs and kernel/API/NVTX statistics.
7. The default two-beacon/two-receiver Pluto example, including I/Q and plots.
8. Separate sampled-input renderer stress cases (1,028 valid paths per link,
   4,096 outputs by default, 32 interpolation taps), without scene tracing or
   receiver DSP. Use `--samples 16667` for approximately one 120 Hz interval.
9. Aggregation into `REPORT.md`, JSON summaries and artifact checksums.

Service latency includes local pose writes, synchronized channel export,
waveform summation, diagnostic per-link filtering, receiver noise/filtering and
ADC conversion. It excludes AirSim RPC/physics, network transport, queueing,
RF skill processing and disk/plotting work. The example's plotting is not
counted as RF service time. First capture is separate from warmed epochs;
existing disk JIT caches are not purged.

The report contains median/p95/max latency, sustained serial update rate,
120/200 Hz deadline misses, channel versus I/Q/front-end time, separate rendering latency, paired CPU/CUDA
ratios, retained path counts, device-event summaries, host ranges, compilation
and cache metadata, telemetry and task failures. Events are measured through
Dr.Jit CUDA events. Nested host ranges are inclusive and no per-range
synchronization is inserted. CUDA operation-time sums are not critical-path
latency; unprofiled runs establish throughput.

### Nsight is optional; CUDA-event profiling is automatic

If `nsys` is installed on the Docker host, the launcher resolves its executable
and mounts the specific installation directory read-only. Override unusual
layouts with `NSYS_BIN=/path/to/nsys NSYS_INSTALL_DIR=/specific/install/root`.
Both the executable and its sibling libraries must be accessible. A current
Nsight build may not support Pascal: use a P100-compatible version if available.
Nsight Compute is not required and does not support the P100.

Nsight captures use CUDA/NVTX/OS runtime tracing with CPU sampling/context-switch
collection disabled. No hardware GPU-metrics sampling is requested. If toolkit
compatibility or profiler permissions still prevent tracing, the failure log is
preserved and the device-event profiles remain available. Missing Nsight is an
optional warning, not a false claim that a timeline was produced. The script
never changes host profiling-permission settings automatically.

`CUDA_LAUNCH_BLOCKING` must be unset or zero. The collector refuses performance
collection when it is enabled. Profiled runs are labelled and cannot enter the
unprofiled report table.

### Artifacts and publishing back

After collection:

```
results/profiling/<run-id>/
  REPORT.md                   ready-to-review Markdown
  environment.json            hardware, source hashes, runtime settings
  installed_packages.json     package versions without credential-bearing URLs
  manifest.json               exact commands, outcomes and logs
  metrics/*.json              unprofiled CPU/CUDA measurements
  profiles/*.json             preflight and instrumented event metadata
  profile_summary.json        timing/cache/operation summaries
  telemetry_summary.json      sampled per-device maxima
  checksums.json               small-artifact SHA-256 hashes
  logs/*.log                  benchmark, compatibility and Nsight statistics
  raw/                        ignored large traces, telemetry CSV, example I/Q/plots
```

The large raw directory is deliberately excluded from git. Keep `.nsys-rep`
files locally or attach them to a release separately if needed. Small JSON and
logs retain enough measurements to analyze this run here. Sampled memory is
not an exact per-process allocation or guaranteed peak VRAM measurement.

Run this **in the host git checkout** with working GitHub push authentication:

```bash
python3 scripts/publish_gpu_results.py results/profiling/p100-20261004 --push
```

This regenerates the report, creates `profiling/results/p100-20261004`, stages
only the report bundle's Markdown/JSON/logs, commits, and pushes that new branch
using normal git authentication. It refuses existing tracked/staged changes,
symlink artifacts and files over 20 MiB. It does not stage raw traces, amend
commits, force-push, or merge results into main. Without `--push`, it makes the
local commit and prints the exact push command. A failed push leaves that
commit intact. GPU compatibility failures are also publishable and clearly
labelled **FAILED / INCOMPLETE**.

Give the resulting branch name to the main Codex session. It can fetch that
branch, inspect `results/profiling/<run-id>/REPORT.md` and the underlying JSON,
and compare measured P100 behavior with [the complexity model](archive/planning.md#sdr-complexity).

To regenerate a report without rerunning benchmarks:

```bash
python3 scripts/aggregate_gpu_profile.py results/profiling/p100-20261004
```

Collection exits zero when required tasks succeed (or in explicit CPU-only
validation mode), and 20 when GPU preflight/required tasks fail. Optional Nsight
failures are recorded without discarding successful benchmark/event results.
Even a nonzero run writes a report if the collector started successfully.
Missing NVIDIA Container Toolkit can prevent Docker from starting at all; that
host-level error must be resolved before collection can produce a report.

Additional controls: `--tx 2` for a small worker only, `--no-example`,
`--no-nsys`, `--no-telemetry`, `--samples`, `--samples-per-link`, `--threads`,
`--output-root`, `--renderers numpy direct`. Changing sample/ray budgets changes the workload and is
recorded. The fixed receiver count is one; the example still uses two receivers.

### Validation performed on this branch

CPU-only reduced collection, real LLVM event profiling and report regeneration
were exercised locally, including the CUDA-unavailable failure path. Publication
selection is tested in an isolated temporary git repository. The profiling image
was built and its CPU collection path exercised offline with NVTX installed.
GPU/OptiX/P100 execution and Nsight capture remain untested here because this
workspace has no GPU. CI additionally runs the test suite and a reduced CPU
collector smoke test; CPU validation is not GPU compatibility validation.

<a id="p100-basis-profiling"></a>

## Updated P100 test: Doppler-basis FFT rendering



**Runtime context (2026-10-05):** Collection instructions and renderer-only qualification. GPU compatibility and 120 Hz capacity must be read with the tested workload and excluded stages. See [current runtime and wall-clock costs](archive/runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

For actual P100 CUDA/OptiX propagation plus GPU rendering, use the
[new explicit GPU pipeline mode](archive/planning.md#p100-gpu-pipeline):

```bash
bash scripts/run_p100_docker.sh --end-to-end --p100-gpu --run-id p100-gpu-full
```

The original commands below retain their documented renderer-only or hybrid
scope.

Branch: **`profiling/p100`**. This branch includes the newer architecture and
preserves the previously published P100/legacy Sionna results.

The [full optimized collection](../results/profiling/p100-basis-optimized-full-20261004/FINDINGS.md)
passed all required checks: 100-TX median 56.167 ms over 30 windows, versus
122.671 ms previously. The oscillator phase bug has now been fixed and the extended CUDA qualification
passes all 76 tests. [Projection and filter experiments](../results/profiling/p100-basis-optimization-20261004/README.md)
retain the original failed runs and document the qualified replacements. Warp
projection with 100 links per batch reduces the 100-TX renderer call from about
122 ms to 55 ms in ten-window comparisons, with all paths and FP64/complex128
precision retained. Sorting/FFT ablations and five block sizes did not improve
on this configuration. Defaults retain the original gather control; select the
qualified faster configuration explicitly:

```bash
bash scripts/run_p100_docker.sh --doppler-basis --projection warp \
  --batch-links 100 --block-samples 2048 --run-id p100-basis-optimized-full
```

The optional `--delay-map single` skips redundant sorting (dense projection
requires no path sorting), and `--fft-inplace` overwrites disposable FFT buffers.
These pass correctness checks but have no demonstrated throughput gain on this
P100 workload. `nvidia-cublas-cu12` supplies the alternate dense FP64 projection.

The [2026-10-04 P100 collection](../results/profiling/p100-basis-full-20261004/REPORT.md)
completed all six CPU/GPU timing cases, but **failed correctness qualification**:
six device-suite tests passed and split captures at Unix-scale timestamps failed.
See [findings and scope](../results/profiling/p100-basis-full-20261004/FINDINGS.md).

The updated test uses **CuPy 13.6, CUDA 12.2, FP64/complex128**, and a native
projection/reconstruction kernel compiled for the actual GPU. The current
Dr.Jit 1.5/Mitsuba 3.9 stack rejects the P100's SM 6.0, as the existing
[P100 diagnostic](../results/profiling/p100-quick-20261003-2005/logs/cuda_compatibility_diagnostic.log)
shows. This renderer therefore executes without Dr.Jit CUDA or OptiX. It does
not claim that current Sionna propagation works on a P100. No production
dependency rollback or implicit CPU fallback is performed.

### Run on the Docker host

Requires Linux, Docker with NVIDIA Container Toolkit, a P100 visible to
`nvidia-smi`, and internet for the build. User-space CUDA libraries are installed
from [pinned wheels](../requirements-p100-cuda.txt); the host supplies its driver.
You do not need to install a host CUDA toolkit.
Use a Linux NVIDIA driver compatible with CUDA 12.2 (535.54.03 or newer);
the previously recorded P100 used 580.178.04.

```bash
git clone --branch profiling/p100 --single-branch https://github.com/wa200508/airsim-rf.git
cd airsim-rf
nvidia-smi
bash scripts/run_p100_docker.sh --doppler-basis --quick \
  --run-id p100-basis-quick
bash scripts/run_p100_docker.sh --doppler-basis \
  --run-id p100-basis-full
```

For an existing checkout, fetch and fast-forward `profiling/p100` first. Run
from a clean checkout so source provenance is unambiguous. Use a unique run ID:
existing result directories are not overwritten. Choose another GPU with
`RF_PROFILE_GPU=...`; the container sees the selected device as device zero.
CuPy and driver caches use writable temporary directories, so the host UID/GID
used by the Docker launcher does not need access to the image user's home.
The launcher also gives LLVM reference kernels a writable Dr.Jit cache and
sets `DRJIT_LIBCUDA_PATH` to an absent library path to disable Dr.Jit's
unsupported CUDA initialization. CuPy uses the actual NVIDIA driver separately;
its CUDA preflight must still pass. This avoids a startup hang observed when
the CPU direct reference initialized Dr.Jit after other numerical libraries.

Default cases: **1, 4 and 100 independent transmitters, one receiver, 1,028
valid paths per link, 16,667 outputs at 2 MS/s**. Delay range 0–100 microseconds,
Doppler range +/-2,500 Hz, 32 input interpolation taps, internal processing
blocks of 2,048 samples, GPU groups of eight independent links, and temporal
tolerance 1e-10. All path arrays change between synthetic channel epochs.
Input waveforms are independent random complex samples occupying 90% of the
sample-rate bandwidth. Each job pays for separate storage and FFT processing.

Quick collection uses one warmup and two timed windows per case; full collection
uses three warmups and thirty timed windows. **Quick retains all default paths
and samples**; its percentiles are smoke statistics. Full runs also include CPU
basis comparisons and numerical references, so they can take several minutes.
The CPU references are not CUDA fallback measurements.

### What is measured and checked

1. Real CUDA preflight: execute FP64 path projection, temporal construction,
   FFT filtering and reconstruction, then compare synchronized output to CPU.
   A driver/library/device error produces a failed report and nonzero exit.
2. Correctness tests on the actual device: independent jobs, changing data,
   different interpolation supports, padded path counts, coherent cancellation,
   split windows, finite transmission boundaries and Unix-scale timestamps.
3. Paired unprofiled CPU/CuPy wall timing, including host validation and packing,
   private uploads, fresh channel construction, filtering, receiver sum and
   final synchronized output download. Startup/JIT is recorded separately.
4. Full all-receiver output comparison against CPU basis reconstruction. Initial
   and final sample prefixes include every path of every transmitter in the
   direct reference. First/last transmitters of each receiver also receive a
   complete all-path direct-output check. Failed accuracy invalidates timings.
5. A separate instrumented capture: CUDA-event stage spans, NVTX ranges and
   allocator snapshots. These spans can contain host submission/idle time and
   are not pure kernel execution time. Nsight, when installed, additionally
   captures a timeline and kernel/API/NVTX statistics in separate logs.
6. GPU telemetry, hardware/runtime/source hashes, package versions, Markdown
   report and checksums. Large profiler traces remain in ignored `raw/`.

The CUDA temporal basis is built with a sampled Chebyshev transform and FFTs
on-device, not CPU Bessel evaluation. The rank uses half the requested tolerance
to budget both the omitted tail and transform aliasing. Host tests check these
coefficients against Bessel values and the original phase equation. Projection
gathers the complete contributing path interval for each delay/basis coefficient;
it uses sorted delay starts and register accumulation rather than contended
atomic writes. Reconstruction evolves the basis in registers in one kernel.
No paths or individual Dopplers are dropped or averaged. See
[the mathematical model and citations](rendering.md#doppler-basis-fft).

The original development check compiled the kernels for `compute_60` using
CUDA 12.2 NVRTC without a GPU. The linked P100 collection now verifies actual
CUDA execution and records performance, while retaining the failed timestamp
accuracy test. Compilation, execution and complete correctness qualification
remain separate outcomes.

### Read and publish the results

```bash
cat results/profiling/p100-basis-full/REPORT.md
python3 scripts/publish_gpu_results.py results/profiling/p100-basis-full --push
```

The publisher creates `profiling/results/p100-basis-full`, commits only small
reports/JSON/logs, then pushes normally. Reported quantities include median,
p95/p99/max synchronized window latency, achieved windows/s, output samples/s,
120 Hz deadline misses and the remaining mean-latency factor to 120 Hz.
Report aggregation preserves accuracy failures and excludes instrumented
Nsight timings from throughput comparisons.

### Explore the limits

```bash
## Only the target one-receiver case, with a different group size.
bash scripts/run_p100_docker.sh --doppler-basis --tx 100 --batch-links 16 \
  --run-id p100-basis-batch16

## Wider Doppler, preserving paths, bandwidth and continuous output count.
bash scripts/run_p100_docker.sh --doppler-basis --tx 100 \
  --max-doppler-hz 25000 --run-id p100-basis-high-doppler

## Ten receivers sequentially on ONE P100: 1,000 private link jobs.
bash scripts/run_p100_docker.sh --doppler-basis --tx 100 --rx 10 \
  --run-id p100-basis-ten-receivers
```

The last case is a one-device capacity stress, not a ten-GPU fleet measurement.
Every receiver gets private waveform copies; transforms are not shared. Hardware
memory/compute limits and failures must be reported, not addressed by reducing
paths or sample budgets. Increasing delay or Doppler ranges grows work/memory.

### Already inside a sandbox

If NVIDIA passthrough is already available, run without nested Docker:

```bash
.venv/bin/python -m pip install -r requirements-p100-cuda.txt
.venv/bin/python scripts/basis_launch.py scripts/run_doppler_basis_profile.py \
  --quick --run-id p100-basis-quick
```

This requires the project's pinned CPU environment as well. The launcher exposes
wheel CUDA library/include paths before Python starts. If GPU passthrough is
missing, installing packages cannot provide it.

### Scope of the 120 Hz result

The target renderer deadline is **8.33 ms per output window**. Mandatory RF
receiver processing, source generation/delivery, scene propagation, clock
resampling, AirSim and network/queueing are excluded. Sample clocks are equal;
independent oscillator offsets are included. These are synthetic channel
updates, not scene/pose-driven propagation.

The renderer exports a whole preloaded window. Live input accumulation can add
up to the window duration (8.3335 ms by default), plus interpolation lookahead
(up to 8 microseconds), processing and transport. A sustained renderer rate of
120 Hz is a necessary milestone, not complete simulation-plane qualification
or an established live-stream delivery latency. Persistent receiver state is exercised by the end-to-end collector below;
clock-rate resampling remains unqualified.

### Complete RF pipeline: fill every stage row

Use the updated `profiling/p100` branch and the new end-to-end Docker mode:

```bash
git switch profiling/p100
git pull --ff-only
bash scripts/run_p100_docker.sh --end-to-end --run-id p100-end-to-end-full
cat results/profiling/p100-end-to-end-full/REPORT.md
```

This is the **scene-to-consumer RF test**, including the moving-platform mount
bridge, private continuous arbitrary input samples, terrain multipath, Doppler
rendering, persistent filtering/noise/ADC, actual loopback HTTP delivery and
consumer write/readback. It uses a deterministic trajectory source, not live
AirSim physics or AMS-GRA distributed SDR workers. Sionna tracing is **LLVM
CPU** on the P100; rendering uses CuPy. Receivers execute serially on one device.

The collector runs **2 TX / 2 RX, 10 TX / 4 RX and 100 TX / 10 RX** on both
CPU and CUDA, with 30 timed windows and three warmups each. GPU scenarios run
a second, separate RF fleet-update capture series with repeated CUDA-event
profiling. Both series retain all scene paths, 1,028 diffuse attempts per
link, 2 MS/s and 120 Hz contiguous sample accounting. There is no synthetic
path padding, sharing of link transforms, or favorable-workload shortcut.

One `REPORT.md` contains configuration rows and processing-step columns:

- Unprofiled RF fleet-update median ± sample standard deviation and p95.
- Separate instrumented RF fleet-update wall-time tables.
- Repeated GPU stage median ± standard deviation and p95 for packing/upload,
  delay mapping, temporal coefficients, path-to-filter projection, private
  FFT filtering, reconstruction/sum and output download.

GPU event spans include dispatch gaps; they are not pure kernel times. They
are summed across blocks/batches/receivers within each window before statistics
are computed. Instrumented measurements never enter the unprofiled throughput
rows. Every required scenario, capture count, pipeline timing and CUDA stage
is validated. A missing step or failed CUDA preflight leaves the collection
incomplete instead of filling a cell with zero or declaring success.

For a sandbox that already exposes the P100:

```bash
.venv/bin/python scripts/basis_launch.py scripts/run_end_to_end_profile.py \
  --run-id p100-end-to-end-full
```

Use `--backend cuda` to collect only the hybrid CPU-tracing/CUDA-rendering
rows, or `--scenarios 100x10` to select the full target fleet. These select
configurations without changing path attempts, sample rate or cadence. At
least two timed captures are required to report standard deviation; 30 is the
default. This fleet run can take several minutes, especially the CPU comparison.

Publish the combined report, nested measurement JSON, logs, environment record
and checksums using the updated publisher; large SC16 captures stay local:

```bash
python3 scripts/publish_gpu_results.py \
  results/profiling/p100-end-to-end-full --push
```

The result branch is `profiling/results/p100-end-to-end-full`. After importing
the published results, `python3 scripts/update_profiling_breakdown.py` discovers
nested complete-pipeline JSON and fills the corresponding tables in
`docs/archive/runtime.md` automatically. It preserves the actual hardware labels
and keeps instrumented GPU events separate from unprofiled latency.


## Regenerate documentation figures on the P100

The checked-in figure data were regenerated on 2026-10-09 with CUDA/OptiX
propagation and the direct CUDA I/Q renderer. Use the isolated P100-compatible
image described above, then run from the checkout:

```bash
bash scripts/regenerate_p100_figures.sh
```

The script uses `airsim-rf:p100-modern-gpu` by default; override
`RF_P100_GPU_IMAGE` when using an equivalent qualified image. It preserves all
published sample/path budgets, stages recordings under `recordings/`, and copies
PNG/SVG, JSON and NPZ assets into `docs/figures`. Plotting, matched filtering,
spectral analysis and receiver filter/noise/ADC remain host work. CUDA is required;
there is no fallback. [Generation provenance and checksums](../results/figures/p100-20261009/manifest.json).

These are sampled snapshot demonstrations, not continuous flight or throughput
measurements. The 32 waterfall epochs span 3.1 s but generate only 384 µs of I/Q
per scene. The 91-point terrain scan spans 18.03 s with 273 µs of I/Q per scene/
bandwidth configuration. The twelve SDR captures span 5.5 s and contain 24.576 ms
of signal per receiver, with gaps between captures. Figure-generation channel
milliseconds exclude rendering/plotting and do not measure a complete pipeline.
