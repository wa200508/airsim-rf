# P100 legacy profiling harness

**Timing scope:** Mixed scope or architecture/reference document; each workload/table retains its stated timed operation. [Common measurement definitions](../../TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** use **wall seconds per simulated signal second**, not an unlabeled whole-run time. For fixed windows, divide mean service milliseconds by samples/sample-rate × 1,000. Stage costs use their parent window denominator. Geometry-only solves and analytic operation counts have no generated signal duration; a signal-time ratio is **not applicable**, unless an explicit update interval is assumed and labeled as a scheduling estimate. Unrecorded flight costs remain unknown. See [recorded normalized cases](../../SIGNAL_TIME_RESULTS.md).

<!-- END SIGNAL TIME CONTEXT -->


The branch's pinned Sionna RT 2.2 / Mitsuba 3.9.1 / Dr.Jit 1.5 stack rejects
the P100's compute capability 6.0. Intermediate rollbacks also failed native
solves on SM 6.0. Measurements here use **Sionna 0.19.2, Mitsuba 3.5.2,
Dr.Jit 0.4.6, TensorFlow 2.15.1, Python 3.11** and TensorFlow's CUDA 12.2
libraries. This is an experimental compatibility harness, not a change to
production dependencies or a claim of solver equivalence.

## Build

On a Docker host with NVIDIA Container Toolkit, first build the branch image
without starting its incompatible benchmark:

```bash
docker build -f Dockerfile.profiling -t airsim-rf:p100-profile \
  --build-arg PROFILE_SOURCE_REV="$(git rev-parse HEAD)" \
  --build-arg PROFILE_SOURCE_DIRTY=false .
docker build -f scripts/p100_legacy/Dockerfile.legacy -t airsim-rf:p100-sionna-0.19.2 .
docker build -f scripts/p100_legacy/Dockerfile.cuda -t airsim-rf:p100-sionna-0.19.2-cuda .
docker build -f scripts/p100_legacy/Dockerfile.metrics -t airsim-rf:p100-legacy-metrics \
  --build-arg PROFILE_SOURCE_REV="$(git rev-parse HEAD)" .
```

Builds need internet. Exact image/package metadata for the recorded runs is
saved in their result bundles. The measured source was commit
`720c4011522ad25c1e9c5c470bc20f4f34d480c5`; subsequent harness/report commits
do not change that recorded source revision.

## Full service collection

```bash
docker run --rm --gpus device=0 \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
  -v "$PWD/scripts/p100_legacy:/work/harness:ro" \
  -v "$PWD/results/profiling:/work/results" \
  airsim-rf:p100-legacy-metrics /work/harness/launch.py \
  /opt/airsim-rf/scripts/run_gpu_profile.py \
  --run-id p100-legacy-new --output-root /work/results
python3 scripts/p100_legacy/analyze_legacy.py results/profiling/p100-legacy-new
```

The collector retains CPU/CUDA pairs, preflight, separate event profiles,
telemetry and the original SDR example. `sitecustomize.py` activates only for
the named repository entry points. CPU cases hide TensorFlow GPUs before
Sionna imports. Both backends use two Dr.Jit threads. `launch.py` exposes the
installed NVIDIA library directories to the dynamic linker.

## Propagation-only scaling

```bash
python3 scripts/p100_legacy/run_scaling.py \
  --output results/profiling/p100-legacy-scaling-new
python3 scripts/p100_legacy/analyze_scaling.py \
  results/profiling/p100-legacy-scaling-new
```

The scaling runner attempts 1k, 10k, 100k and 1M native transmitters, each
simultaneously in one scene/solve, with one receiver and 1,028 launched rays per
TX. It does not batch transmitters. Signal synthesis, I/Q, filtering, noise,
ADC and full coefficient export are omitted. Trace and RF-field timings fence
device work through scalar reductions; they still include host orchestration
and those reductions. Scene/object setup and first solve are recorded separately.

Each case has a wall-clock timeout and an independent container with a 12 GiB
**host RAM** cap, no host swap, and access to the P100's full **16 GiB VRAM**.
This cap is not a GPU memory cap. Allocation failures, timeout checkpoints and
container OOM state are retained. GPU telemetry samples every 100 ms and includes
other processes. A sampled 100% means GPU busy during the sampling window, not
100% theoretical arithmetic throughput. No driver reset or reconfiguration is
used. A failed large case is a capacity observation, not a valid latency sample.

## Scope

Native legacy Fibonacci tracing replaces the custom first-order sampler;
`num_samples = TX * 1028`, depth 1, LoS/reflection/scattering, scattering keep
probability 1, random scatter phases disabled. The terrain mesh is unchanged;
temporary XML and material adaptation set epsilon_r=5, conductivity=.01,
scattering=.3. Thickness has no legacy equivalent. Full service runs use the
original receiver and waveform chain through a legacy Paths/Doppler adapter.
Scaling uses static positions. Scientific/numerical equivalence is unvalidated.

Dr.Jit event histories exclude TensorFlow CUDA kernels. TensorFlow allocator
peaks exclude other allocators. Sampled whole-GPU memory is not exact per-process
peak allocation. Few-epoch scaling p95 values are smoke statistics. The original
full collection's 100-TX host I/Q cost is useful evidence for signal-rendering
work, but propagation timing does not transfer directly to current Sionna.
