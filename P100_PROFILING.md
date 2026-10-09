# Run and publish P100 profiling measurements

**Timing scope:** Mixed scope or architecture/reference document; each workload/table retains its stated timed operation. [Common measurement definitions](TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.



**Runtime context (2026-10-05):** The older current-stack/legacy collectors have separate propagation and renderer scopes. Use the optimized basis collection for the current comparable continuous-I/Q timing. See [current runtime and wall-clock costs](RUNTIME_STATUS.md) for comparable measurements, hardware, exclusions and ten-minute estimates.

For the **updated Doppler-basis FFT test on `profiling/p100`**, use
[the CuPy/CUDA 12.2 P100 guide](P100_BASIS_PROFILING.md). Its one-command run
measures 100 private transmitter streams, all-valid paths and complete 120 Hz
sample windows. The current Dr.Jit stack rejects SM 6.0; the new renderer
therefore uses CuPy directly. The general current-stack/legacy guides below
remain separate propagation and older renderer references.

Branch: **`optimization/direct-path-renderer`**. This branch extends the
profiling kit with [direct path LLVM/CUDA recurrence](DIRECT_PATH_RENDERING.md).
The collector compares NumPy, direct and [batched rendering](BATCHED_RENDERING.md),
and separately measures private arbitrary sampled I/Q. Receiver filtering and
ADC remain CPU work; the batched backend groups transfers across independent
jobs. Defaults keep per-link diagnostics enabled.

## Measured P100 compatibility and results

The pinned Sionna RT 2.2 / Mitsuba 3.9.1 / Dr.Jit 1.5 stack does **not** run
on this P100 (compute capability 6.0). The standard launcher below retains those
pins and is not a working P100 recipe. An isolated legacy stack was needed:
Sionna 0.19.2, Mitsuba 3.5.2, Dr.Jit 0.4.6, TensorFlow 2.15.1 and Python 3.11.

- [Initial compatibility failure](results/profiling/p100-quick-20261003-2005/REPORT.md)
- [Full legacy profiling collection](results/profiling/p100-legacy-full-20261003/REPORT.md)
- [Propagation-only simultaneous transmitter scaling](results/profiling/p100-legacy-scaling-20261003/REPORT.md)
- [Legacy harness and reproduction instructions](scripts/p100_legacy/README.md)

These measurements use legacy native propagation in place of the branch's
custom solver. The full collection retains the original host I/Q/receiver
chain; scaling removes that chain. They establish execution and performance,
not physical or numerical equivalence to the current solver. Production code
and dependency locks are unchanged. Large I/Q files and profiler traces remain
local under ignored `raw/` directories; reports, small metrics and logs are
committed.

## One command on the Docker host

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

## If Sol is already inside a GPU sandbox

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

## What is collected

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

## Nsight is optional; CUDA-event profiling is automatic

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

## Artifacts and publishing back

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
and compare measured P100 behavior with [the complexity model](SDR_COMPLEXITY.md).

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

## Validation performed on this branch

CPU-only reduced collection, real LLVM event profiling and report regeneration
were exercised locally, including the CUDA-unavailable failure path. Publication
selection is tested in an isolated temporary git repository. The profiling image
was built and its CPU collection path exercised offline with NVTX installed.
GPU/OptiX/P100 execution and Nsight capture remain untested here because this
workspace has no GPU. CI additionally runs the test suite and a reduced CPU
collector smoke test; CPU validation is not GPU compatibility validation.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** use **wall seconds per simulated signal second**, not an unlabeled whole-run time. For fixed windows, divide mean service milliseconds by samples/sample-rate × 1,000. Stage costs use their parent window denominator. Geometry-only solves and analytic operation counts have no generated signal duration; a signal-time ratio is **not applicable**, unless an explicit update interval is assumed and labeled as a scheduling estimate. Unrecorded flight costs remain unknown. See [recorded normalized cases](SIGNAL_TIME_RESULTS.md).

<!-- END SIGNAL TIME CONTEXT -->
