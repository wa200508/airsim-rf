# Optimizations with independent transmitter data

**Timing scope:** Mixed scope or architecture/reference document; each workload/table retains its stated timed operation. [Common measurement definitions](TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.



**Runtime context (2026-10-05):** Historical direct-renderer accumulation experiments and bandwidth accounting; preserve independent buffers, but use the current qualified basis measurements for achieved throughput. See [current runtime and wall-clock costs](RUNTIME_STATUS.md) for comparable measurements, hardware, exclusions and ten-minute estimates.

The target remains 100 independent transmitters, 10 receivers, continuous
2 MS/s I/Q and 120 Hz channel updates, retaining full first-order path coverage
and individual narrowband Doppler evolution. The compute ceiling is $5,000.
No transmitter-buffer or transmitter-transform sharing is credited. Separate
receiver workers own private copies of their inputs. Batching jobs means
launching independent work together, not making their input data identical.

The workload has not been qualified at 120 Hz on affordable GPUs. Optimizing
execution must not depend on short delays, low Doppler, fewer rays, a special
waveform family or reduced scene-update cadence.

## First experiment: eliminate contribution buffers

Previously, `render_paths` wrote two FP64 arrays of size
`path_tile * num_samples`, then reduced them across paths. The new experimental
`accumulation="local"` option computes the same contribution, locally combines
lanes with the same output index, and atomically adds to the link's private
output. Dr.Jit implements this local reduction within CPU SIMD packets or CUDA
warps. This removes the explicit path-by-sample buffers and their later
reduction pass. Path coefficients, delays, sample count, precision and per-path
Doppler recurrence are unchanged. It remains O(paths * samples).

This is an intermediate implementation to measure. Atomic updates still touch
memory and may contend; a custom GPU block reduction with register/shared-memory
accumulators is another candidate. Local reduction does not imply that every
sum stays on-chip, nor that removing buffers guarantees a particular speedup.
Atomic summation can have small scheduling-dependent rounding differences.
The default remains `accumulation="partial"` until GPU qualification.

### CPU kernel measurements

[Recorded measurements](research_results/affordable_realtime/accumulation_cpu.json)
use four independent directed-link jobs, each with 1,028 valid paths and 16,667
samples at 2 MS/s. Every link has separately allocated, randomly generated
gains, fractional delays spanning a declared 0–100 microsecond range, and
independent Dopplers in +/-2,500 Hz. No terrain visibility removes paths.
Tone parameters and LFM parameters are different between links. The LFM gate
is identical between implementations; the continuous tone case exercises
contributions throughout the window. The CPU quota is two cores.

| Four private links, 128-path tiles | Original contribution buffers | Local accumulation | Median reduction |
|---|---:|---:|---:|
| Tone | 292.86 ms | 50.26 ms | 5.83x |
| LFM | 182.04 ms | 52.48 ms | 3.47x |

With 1,028-path tiles, local accumulation took 47.38 ms for tone and 47.79 ms
for LFM. Increasing tile size alone made the original buffered implementation
slower here. This illustrates why tile size is a measured hardware choice.
For 128-path tiles, the eliminated contribution arrays occupied 32.55 MiB
per active link; for 1,028-path tiles, 261.44 MiB. The renderer still allocates
outputs, lane/phase state and other runtime memory.

Ten warmed runs per configuration were collected, with synchronous NumPy export
included in timing. The JSON includes every timing, first-call timing, validation
errors and source hashes. These are exploratory timings, not dependable tail
latency estimates. Maximum absolute error against the independent FP64 analytic
reference was below 1e-11; normalized RMS error was below 1.5e-12. Tests also
cover equal-delay paths with different Dopplers, coherent cancellation, pulse
boundaries, split-block phase continuity and the complete SDR frontend.

**This experiment supports analytic tone/LFM only.** It does not benchmark
sampled-waveform interpolation, propagation or continuous stateful receiver
processing. Four links are a kernel diagnostic, not the 1,000-link acceptance
workload. No CUDA execution is available in this workspace. A CPU speedup must
not be multiplied by a guessed GPU scaling factor.

### Complete existing CPU capture case

The same option was compared in the existing 100-TX/1-RX terrain capture,
using 4,096 output samples plus 256 filter-warmup samples, 1,028 attempts/link,
moving poses, independent clocks and the complete noise/filter/ADC chain.
Both runs used the same ten timed scene epochs and retained 42,513–42,526 paths.
These capture windows are the existing test, not a gap-free continuous stream.

| Median stage | [Buffered run](research_results/affordable_realtime/sdr_partial_cpu.json) | [Local run](research_results/affordable_realtime/sdr_local_cpu.json) |
|---|---:|---:|
| Rendering | 355.57 ms | 240.32 ms |
| Channel solve/export | 84.03 ms | 67.97 ms |
| Complete service | 461.36 ms | 330.69 ms |
| Service minus rendering, measured per epoch | 106.38 ms | 90.84 ms |

Complete-service median improved by about 1.40x, substantially less than the
isolated kernel's improvement. The channel timing difference is variability in
a stage unchanged by this rendering option; do not attribute it to accumulation.
The buffered run also had large service spikes (about 1,046 ms empirical p95,
versus 362 ms for local). Ten samples do not qualify tail latency, and these
runs did not diagnose the cause of those spikes. Host proposal draws alone
took approximately 17–18 ms, exceeding the 8.33 ms scene-update budget.
This establishes that reducing rendering buffers alone cannot meet 120 Hz.

The updated local suite passed 97 tests, with nine CUDA cases skipped because
no device was available. GPU qualification remains outstanding.

## Other optimizations to explore

| Change | Why it can help | Required constraint / verification |
|---|---|---|
| Fused sampled-waveform rendering | Interpolate private input samples, evolve each path's Doppler, apply complex gain and accumulate in one kernel instead of writing intermediate tensors | Preserve all valid paths and arbitrary sampled data. Sweep delay/Doppler ranges and interpolation accuracy; retain input history and include any lookahead in latency. The analytic experiment is only the accumulation portion. |
| Device-resident channel and receiver chain | Avoid exporting Sionna paths to NumPy, re-uploading derived arrays, downloading every rendered link and running the coherent sum/filter/ADC on the CPU | Input buffers remain private. Retain independent clocks, calibrated scaling, noise, filter state, ADC and clipping. Download the selected receiver output stream after mandatory processing. |
| Batched independent jobs and stable launches | Reduce Python calls, allocations, synchronization and JIT/launch overhead by scheduling separate link jobs together | Keep separate storage and parameters. Size buckets may pad with invalid lanes but must never truncate valid paths; overflow needs a larger bucket or additional work. Measure first-use compilation separately from warmed deadlines. |
| Private double buffering and streams | Overlap independent input transfer, rendering and output delivery when resources permit | Count the full private input traffic. Overlap does not remove bandwidth cost, and throughput can improve without reducing dependent-sample latency. Queues must stay bounded. |
| GPU proposal sampling | Current diffuse direction draws use NumPy even with CUDA propagation; move sampling/PDF work to the GPU to remove a host stage and direction upload | Preserve both TX and RX proposal components, uniform coverage, all attempts, mixture densities and weights. Validate distribution and RF statistics when the RNG changes. |
| Cache invariant antenna tables | Current code rebuilds body-frame angular gain/PDF tables on each solve, including device-to-host export | Only cache a pattern that is unchanged; rotate directions using current poses and invalidate on pattern changes. Materials, geometry-dependent gains and visibility still update. This does not remove the separate sampling cost. |
| Compile or move frontend processing | Existing per-link diagnostics and receiver processing have CPU/Python overhead | Mandatory RF processing stays. Per-link power diagnostics can be separately timed or explicitly disabled when unused, with equivalence of receiver I/Q verified. No savings are credited until measured. |
| Validated mixed precision | FP32 arithmetic could make consumer GPUs more suitable than the current FP64 kernel | Validate phase continuity, long epochs, weak returns and strong-signal cancellation against FP64, using absolute noise-floor error as well as relative EVM. Do not assume ADC resolution permits FP16/TF32. P100 and consumer RTX have different FP64/FP32 tradeoffs. |

Static geometry acceleration and exact specular plane extraction are already
cached in the current stack. Do not count them again as an entirely new
optimization. Moving platforms still require current geometry, visibility,
antenna orientation, delay, gain and Doppler at the requested update cadence.
Persistent diffuse scatterer identities need separate temporal-correlation
validation; freezing visibility is not a valid substitute.

## Bandwidth accounting without source sharing

At 100 TX, 10 RX and continuous 2 MS/s:

| Traffic | Aggregate payload | Interpretation |
|---|---:|---|
| 100 original independent complex64 source streams | 1.6 GB/s | Data at the source side, before worker replication |
| Private input delivery to all ten receiver workers | 16 GB/s | Each worker owns 100 streams; no reuse credit |
| Current per-link complex128 output downloads | 32 GB/s | If the present per-link export architecture rendered all 1,000 links continuously |
| One final complex64 I/Q stream per receiver | 160 MB/s | Possible output traffic after moving required summation/frontend work to the device |
| Raw FP64 path state at 1,028 paths/link and 120 Hz | 3.95 GB/s | Complex gain plus delay plus Doppler, 32 bytes/path; excludes padding, gates and other solver state |

The output reduction combines the physically required independent signals at
the receiver. It does not share transmitter input buffers. The input traffic
still needs to fit the actual PCIe/network arrangement, or be generated locally
into private buffers with that generation cost measured. If generation moves
on-device, arbitrary recorded streams must still be supported and benchmarked.
A single 10 GbE link cannot carry even one worker's 1.6 GB/s raw input payload.

With 1,028 valid paths per link, direct continuous rendering requires 2.056
trillion path/sample contributions per second. The old temporary write/read
scheme alone accounts for about 65.8 TB/s at 32 bytes/contribution. Removing
that traffic is worthwhile, but interpolation input reads, phase arithmetic,
reduction, ray tracing and private input delivery remain. Neither these operation
counts nor the CPU experiment prove a $5,000 deployment can meet the deadline.

## Run the comparison on a GPU

On the existing profiling branch/environment:

```bash
# Kernel diagnostic; all input/channel arrays are private per directed link.
.venv/bin/python benchmarks/benchmark_render_accumulation.py \
  --backend cuda --links 4 --paths 1028 --samples 16667 \
  --max-delay-us 100 --max-doppler-hz 2500 \
  --iterations 30 --output results/accumulation-gpu.json

# Larger analytic renderer stress; still excludes propagation and receiver DSP.
.venv/bin/python benchmarks/benchmark_render_accumulation.py \
  --backend cuda --links 1000 --paths 1028 --samples 16667 \
  --iterations 10 --output results/accumulation-gpu-1000links.json

# Complete existing SDR capture case with experimental reduction.
.venv/bin/python benchmarks/benchmark_sdr_runtime.py \
  --backend cuda --renderer direct-cuda --accumulation local \
  --tx 100 --rx 1 --samples 4096 --samples-per-link 1028 \
  --iterations 30 --output results/sdr-local-gpu.json
# Repeat with --accumulation partial for the same workload.
```

The kernel diagnostic deliberately retains existing per-link transfers and
launches, so it measures this implementation's overhead rather than assuming
private residency/batching has already been built. The large stress also
retains those costs and can take substantial time. Accuracy is checked against
NumPy on the first four independent links; the correctness suite supplies
additional cancellation/continuity cases. It is not full arbitrary-I/Q validation.
Run unprofiled timings separately from instrumented profiles, record GPU model,
driver and software versions, and compare exactly matching parameters.

Qualification must eventually use arbitrary private sample streams across all
1,000 links, declared channel ranges and the complete moving-scene/frontend
pipeline. Report achieved sustained rate, chunk delivery latency, p95/p99,
missed deadlines and dropped samples. A whole 8.33 ms chunk can add buffering
delay before computation; smaller delivery chunks trade that latency against
more launches without reducing the total physical workload.

The immediate next priorities are GPU measurement of accumulation and a general
sampled-waveform fused kernel, followed by device-resident channel/frontend
processing and proposal sampling. The complete 120 Hz goal remains unproven.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [research_results/affordable_realtime/sdr_local_cpu.json](research_results/affordable_realtime/sdr_local_cpu.json) — Local RF service | unprofiled_benchmark | 10 | 2.048000 | 0.020480 | 3.290627 | 160.675 |
| [research_results/affordable_realtime/sdr_partial_cpu.json](research_results/affordable_realtime/sdr_partial_cpu.json) — Local RF service | unprofiled_benchmark | 10 | 2.048000 | 0.020480 | 6.317350 | 308.464 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->
