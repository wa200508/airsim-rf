# Updated P100 test: Doppler-basis FFT rendering

**Runtime context (2026-10-05):** Collection instructions and renderer-only qualification. GPU compatibility and 120 Hz capacity must be read with the tested workload and excluded stages. See [current runtime and wall-clock costs](RUNTIME_STATUS.md) for comparable measurements, hardware, exclusions and ten-minute estimates.

Branch: **`profiling/p100`**. This branch includes the newer architecture and
preserves the previously published P100/legacy Sionna results.

The [full optimized collection](results/profiling/p100-basis-optimized-full-20261004/FINDINGS.md)
passed all required checks: 100-TX median 56.167 ms over 30 windows, versus
122.671 ms previously. The oscillator phase bug has now been fixed and the extended CUDA qualification
passes all 76 tests. [Projection and filter experiments](results/profiling/p100-basis-optimization-20261004/README.md)
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

The [2026-10-04 P100 collection](results/profiling/p100-basis-full-20261004/REPORT.md)
completed all six CPU/GPU timing cases, but **failed correctness qualification**:
six device-suite tests passed and split captures at Unix-scale timestamps failed.
See [findings and scope](results/profiling/p100-basis-full-20261004/FINDINGS.md).

The updated test uses **CuPy 13.6, CUDA 12.2, FP64/complex128**, and a native
projection/reconstruction kernel compiled for the actual GPU. The current
Dr.Jit 1.5/Mitsuba 3.9 stack rejects the P100's SM 6.0, as the existing
[P100 diagnostic](results/profiling/p100-quick-20261003-2005/logs/cuda_compatibility_diagnostic.log)
shows. This renderer therefore executes without Dr.Jit CUDA or OptiX. It does
not claim that current Sionna propagation works on a P100. No production
dependency rollback or implicit CPU fallback is performed.

## Run on the Docker host

Requires Linux, Docker with NVIDIA Container Toolkit, a P100 visible to
`nvidia-smi`, and internet for the build. User-space CUDA libraries are installed
from [pinned wheels](requirements-p100-cuda.txt); the host supplies its driver.
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

## What is measured and checked

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
[the mathematical model and citations](DOPPLER_BASIS_FFT.md).

The original development check compiled the kernels for `compute_60` using
CUDA 12.2 NVRTC without a GPU. The linked P100 collection now verifies actual
CUDA execution and records performance, while retaining the failed timestamp
accuracy test. Compilation, execution and complete correctness qualification
remain separate outcomes.

## Read and publish the results

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

## Explore the limits

```bash
# Only the target one-receiver case, with a different group size.
bash scripts/run_p100_docker.sh --doppler-basis --tx 100 --batch-links 16 \
  --run-id p100-basis-batch16

# Wider Doppler, preserving paths, bandwidth and continuous output count.
bash scripts/run_p100_docker.sh --doppler-basis --tx 100 \
  --max-doppler-hz 25000 --run-id p100-basis-high-doppler

# Ten receivers sequentially on ONE P100: 1,000 private link jobs.
bash scripts/run_p100_docker.sh --doppler-basis --tx 100 --rx 10 \
  --run-id p100-basis-ten-receivers
```

The last case is a one-device capacity stress, not a ten-GPU fleet measurement.
Every receiver gets private waveform copies; transforms are not shared. Hardware
memory/compute limits and failures must be reported, not addressed by reducing
paths or sample budgets. Increasing delay or Doppler ranges grows work/memory.

## Already inside a sandbox

If NVIDIA passthrough is already available, run without nested Docker:

```bash
.venv/bin/python -m pip install -r requirements-p100-cuda.txt
.venv/bin/python scripts/basis_launch.py scripts/run_doppler_basis_profile.py \
  --quick --run-id p100-basis-quick
```

This requires the project's pinned CPU environment as well. The launcher exposes
wheel CUDA library/include paths before Python starts. If GPU passthrough is
missing, installing packages cannot provide it.

## Scope of the 120 Hz result

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

## Complete RF pipeline: fill every stage row

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
a second, separate full-pipeline capture series with repeated CUDA-event
profiling. Both series retain all scene paths, 1,028 diffuse attempts per
link, 2 MS/s and 120 Hz contiguous sample accounting. There is no synthetic
path padding, sharing of link transforms, or favorable-workload shortcut.

One `REPORT.md` contains configuration rows and processing-step columns:

- Unprofiled full-pipeline median ± sample standard deviation and p95.
- Separate instrumented full-pipeline wall-time tables.
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
`RUNTIME_STATUS.md` automatically. It preserves the actual hardware labels
and keeps instrumented GPU events separate from unprofiled latency.
