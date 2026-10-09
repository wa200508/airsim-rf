# SDR runtime: update rate and latency

**Timing scope:** Mixed scope or architecture/reference document; each workload/table retains its stated timed operation. [Common measurement definitions](TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.



**Runtime context (2026-10-05):** Historical scene-to-ADC tone captures contain only 4,096 output samples (2.048 ms at 2 MS/s), with scene-dependent surviving paths. Later arbitrary-I/Q GPU rendering is measured separately. See [current runtime and wall-clock costs](RUNTIME_STATUS.md) for comparable measurements, hardware, exclusions and ten-minute estimates.

See [the code-derived scaling model](SDR_COMPLEXITY.md) for stage-by-stage
complexity, CPU prediction checks and explicit GPU implementation estimates.

Measured 2026-10-03 against the Pluto-class receiver introduced in commit
279787aa181172fe5d95c14aaa5f61c729e9f701. These measurements include finished ADC
I/Q. Earlier propagation-only reports do not measure this complete pipeline.
**The present CPU implementation is suitable for offline simulation. Selecting
CUDA alone cannot make its CPU I/Q synthesis run at 120 or 200 Hz.** This older scene-to-ADC pipeline has not been fully ported to GPU.
The separate basis renderer now has qualified P100 measurements; see
[RUNTIME_STATUS.md](RUNTIME_STATUS.md).

## What the two numbers mean

* **Service latency:** wall time from starting local pose writes to completed
  I/Q blocks. Includes synchronized propagation/export, waveform synthesis,
  per-link diagnostic filtering, receiver noise/filtering and ADC conversion.
* **Update rate:** sustained serial captures per wall-clock second, measured
  over the timed loop. A two-receiver batch produces two receiver blocks per
  update. This is distinct from ADC sample rate and from AirSim physics rate.
* **End-to-end delivery latency:** service latency plus pose acquisition,
  dispatch/transport, queueing and downstream processing. Those additional
  costs are not measured by this offline benchmark.

The scene uses 915 MHz, ideal vertical dipoles, the 21×21 DEM / 800 triangles,
1,028 attempted diffuse samples **per TX/RX link**, both TX- and RX-pattern
proposals, direct/specular/diffuse paths and at most one surface interaction.
The channel is computed once per capture, not once per fast-time sample.
Clock error and narrowband Doppler evolve analytically within the block.
Each receiver produces 4,096 samples at nominal 2 MS/s: **2.048 ms of RF data**,
plus 256 discarded filter warmup samples. The 1 MHz approximate receive filter,
chosen 10 dB noise figure and signed 12-bit conversion are enabled.

For 2 TX, positions/powers/clock errors match [the COTS lab](COTS_SDR_LAB.md);
one-worker timing uses listener A. For 100 TX, transmitters occupy x=0,
y=−25…25 m, z=10 m and move at 1 m/s along x. They use −30 dBm each,
tones spanning ±250 kHz, reference errors spanning ±20 ppm and distinct phases.
Listener A starts at [−30, −10, 14] m and moves at 3 m/s along x.
This is a measured expanded SDR workload, not the earlier 24.125 GHz radar
fixture or a tested AMS-GRA distributed run. The second receiver is omitted
in the per-worker tests, not obtained by dividing a batched result.

## Measured CPU results

AMD EPYC 9V74 host; container quota **two CPU cores**, 8 GiB memory limit,
Dr.Jit two threads; LLVM polarized backend. Sionna RT 2.2.0, Mitsuba 3.9.1,
Dr.Jit 1.5.0. No CUDA backend is available. Cases ran sequentially to avoid
benchmark contention; host scheduling and JIT/cache behavior still vary.

| Workload | Median service latency | p95 service latency | Sustained updates/s | Median channel | Median CPU I/Q + receiver |
|---|---:|---:|---:|---:|---:|
| 2 TX → 1 RX worker | 240.9 ms | 259.3 ms | 4.079 Hz | 23.1 ms | 217.7 ms |
| 2 TX → 2 RX batch | 410.4 ms | 446.7 ms | 2.425 Hz | 19.6 ms | 389.7 ms |
| 100 TX → 1 RX worker | 11522.8 ms | 11730.0 ms | 0.087 Hz | 681.6 ms | 10846.5 ms |

The two-receiver batch yields 4.85 receiver blocks/s,
but only 2.42 scene updates/s. Independent workers on separate
resources can increase aggregate throughput; that does not divide any one
receiver's service latency. Per-stage medians need not sum to total medians.

Small tests use five warmups and 30 timed moving epochs; the large test uses
two warmups and ten timed epochs. P95 values describe these short runs,
not certified tail latency. All timed captures missed both 8.33 ms (120 Hz)
and 5 ms (200 Hz) service budgets. First captures took
610.2, 401.2 and
11657.3 ms respectively. These are new processes
with existing disk JIT caches, not cache-cleared startup measurements.
Imports and scene/receiver preparation are excluded from service timing;
preparation is reported separately in the JSON.

With a 200 Hz requested update stream and one serial worker, utilization is
`200 × mean_service_seconds`. It exceeds one for all these CPU cases, so FIFO
queueing grows without bound. Running AirSim independently at 120 Hz remains
possible, but RF results will lag unless simulation time is slowed, captures
are dropped/coalesced, or service capacity improves. No scheduler or network
latency was measured here.

At 200 Hz, 4,096 samples/capture supply 819,200 samples/s per receiver:
40.96% capture duty at 2 MS/s. At 120 Hz, that is 491,520 samples/s and 24.576%
duty. This benchmark therefore does **not** demonstrate continuous 2 MS/s
RF coverage. Continuous coverage would require more samples or overlapping
processing. The documented plots use sparse epochs, not a measured live 200 Hz
stream.

## GPU: current code versus a future implementation

The current CUDA selection changes Sionna/Mitsuba propagation. Antenna-aware
proposal draws still use NumPy on the host; compact gains/delays/Doppler are
exported to NumPy; waveform summation, noise, filtering and quantization remain
CPU operations. Every retained path evaluates the callable waveform, LO error
and Doppler over the sample block. That cost grows roughly as
`retained_paths × (samples + warmup)`; propagation work instead grows with
attempted paths, surface candidates and visibility queries.

For the **unchanged current hybrid implementation on this same CPU**, even
instantaneous propagation would leave these measured median host stages:

| Workload | CPU I/Q + receiver floor | Inverse median host time |
|---|---:|---:|
| 2 TX → 1 RX | ~217.7 ms | ~4.59 updates/s |
| 100 TX → 1 RX | ~10846.5 ms | ~0.092 updates/s |

These are conditional bounds using measured CPU stages, **not measured GPU
latencies or promises about a different host**. Actual current hybrid latency
also includes host proposal preparation, GPU fields/compaction, launches,
synchronization and transfers. The plausible improvement from faster rays
alone is small because I/Q dominates. CPU clock/vectorization, waveform type,
path counts and thermal/scheduling behavior change the host cost.

For a GPU-resident redesign, ray counts provide a useful sensitivity calculation:

| Per receiver | Maximum visibility queries/update | Ray time if effective scene throughput is 100 M queries/s | At 250 M queries/s | At 1 G queries/s |
|---|---:|---:|---:|---:|
| 2 TX, DEM | 7,314 | 0.073 ms | 0.029 ms | 0.007 ms |
| 100 TX, DEM | 365,700 | 3.657 ms | 1.463 ms | 0.366 ms |

Those rates are **hypothetical whole-scene query rates**, not vendor RT-core
specifications or measured results. They cover ray queries only, excluding
material/polarization field evaluation, compaction, I/Q, transfers and launch
costs. Small scenes can be dominated by overhead even when ray counts are low.
For 100 TX, the host proposal draws alone measured
18.8 ms median per worker;
those draws must also move off the CPU or be substantially optimized.

The actual largest retained-path counts in these runs were 812 (2 TX)
and 42,526 (100 TX), yielding 3.53 million and
185.07 million path/sample contributions per receiver capture.
To fit synthesis alone into 5 ms requires respectively
0.71 and 37.01 billion completed contributions/s;
for 8.33 ms, approximately 0.42 and
22.21 billion/s. A contribution includes waveform/delay,
Doppler/clock phase and accumulation, not merely one multiply-add.
All other stages must fit into the same budget, so these are necessary rates,
not sufficient rates or hardware sizing claims.

A tone-specific analytic specialization could avoid repeatedly evaluating its
waveform/clock exponentials; a general waveform backend still needs efficient
batched evaluation or equivalent frequency-domain processing. Keep compact
channels and synthesis on the GPU and tile/reduce contributions instead of
materializing a giant path×sample tensor. Validate the numerical equivalence
and target-GPU latency before claiming a supported real-time rate.

For the original **100 TX / 10 RX deployment**, each of ten GPU workers must
handle all 100 TX. Ten GPUs increase fleet parallelism; each receiver still
needs its own complete 5 ms / 8.33 ms pipeline. AirSim scene truth, dispatch,
RF processing and transport need explicit latency budgets. No specific GPU
model, minimum VRAM or end-to-end GPU update rate is established by this CPU
benchmark; host RSS is not device memory. This is the missing measurement,
not evidence that GPU-resident RF simulation is infeasible.

## Reproduce and inspect

```bash
.venv/bin/python benchmarks/benchmark_sdr_runtime.py --tx 2 --rx 1 \
  --iterations 30 --warmup 5 --output benchmarks/results/sdr_cpu_2tx_1rx.json
.venv/bin/python benchmarks/benchmark_sdr_runtime.py --tx 2 --rx 2 \
  --iterations 30 --warmup 5 --output benchmarks/results/sdr_cpu_2tx_2rx.json
.venv/bin/python benchmarks/benchmark_sdr_runtime.py --tx 100 --rx 1 \
  --iterations 10 --warmup 2 --output benchmarks/results/sdr_cpu_100tx_1rx.json
```

Use `--backend cuda` in a properly provisioned CUDA environment to benchmark
the current hybrid path; it rejects unavailable CUDA instead of falling back.
The existing CPU container does not supply a tested CUDA runtime.

Raw results:

* [2 TX / 1 RX](benchmarks/results/sdr_cpu_2tx_1rx.json)
* [2 TX / 2 RX](benchmarks/results/sdr_cpu_2tx_2rx.json)
* [100 TX / 1 RX](benchmarks/results/sdr_cpu_100tx_1rx.json)

Timing boundaries are in [the benchmark](benchmarks/benchmark_sdr_runtime.py).
The channel export and CPU receive chain are in [sdr.py](src/airsim_rf/sdr.py);
the per-path waveform loop is in [receiver.py](src/airsim_rf/receiver.py).
See [GPU planning](GPU_RUNTIME.md) for earlier channel-only work estimates;
those figures exclude this SDR synthesis and receive chain.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [benchmarks/results/sdr_cpu_100tx_1rx.json](benchmarks/results/sdr_cpu_100tx_1rx.json) — Local RF service | historical | 10 | 2.048000 | 0.020480 | 115.490185 | 5639.169 |
| [benchmarks/results/sdr_cpu_2tx_1rx.json](benchmarks/results/sdr_cpu_2tx_1rx.json) — Local RF service | historical | 30 | 2.048000 | 0.061440 | 7.354236 | 119.698 |
| [benchmarks/results/sdr_cpu_2tx_2rx.json](benchmarks/results/sdr_cpu_2tx_2rx.json) — Local RF service | historical | 30 | 2.048000 | 0.061440 | 12.371171 | 201.354 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->
