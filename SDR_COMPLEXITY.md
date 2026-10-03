# Code-derived CPU and GPU runtime model

This analysis uses the current Pluto-class SDR path, the code in main as of
4e29528, and [the recorded CPU benchmarks](SDR_RUNTIME.md). The benchmark
waveforms are continuous tones. LFM recurrence is a proposed extension, not a
measured LFM GPU result. All GPU estimates below are **untested planning
estimates**, with their assumed throughput stated explicitly.

## Work counts and complexity

Use these quantities, not a single ambiguous `n`:

| Symbol | Meaning | 100-TX / one-RX benchmark |
|---|---|---:|
| T | Transmitters processed by a worker | 100 |
| R | Receivers in that worker's solve | 1 |
| S | Diffuse sampling attempts per TX/RX link | 1,028 |
| M | Distinct specular candidate planes | 800 |
| F | Scene triangles | 800 |
| G | Bins per shared antenna proposal table | 8,192 |
| N | Samples processed, including filter warmup | 4,352 |
| P | Total retained paths across the worker's links | mean 42,519.6 |
| C | Candidate path slots, `TR(S+M+1)` | 182,900 |
| Q | Upper bound visibility queries, `TR(2S+2M+1)` | 365,700 |
| D | Padded channel slots, `TR × maximum paths/link` | ≤ C |
| W | Path/sample contributions, `PN` | mean 185,045,299 |

The mapping from code to work is:

| Stage | Code | Work per update |
|---|---|---|
| Platform poses | benchmark `run`; AirSim bridge | O(T+R), plus RPC costs if connected |
| Shared antenna tables | `scattering._AngularProposal.from_patterns` | O(G) for fixed polarization/pattern counts; currently rebuilt each capture |
| Host importance draws | `_AngularProposal.draw`, `_ScatteringCandidates.__call__` | O(G + TRS log G): weighted NumPy choice builds a CDF and searches it; direction arithmetic O(TRS) |
| Direct/specular candidate construction | `single_bounce._PlanarCandidates.__call__` | O(TR(M+1)); exhaustive planes, not random bounce discovery |
| First-hit and visibility tracing | scattering and native image method | Q BVH queries; typically O(Q log F), worst case O(QF) for pathological traversal |
| Jones/material/antenna fields | Sionna `FieldCalculator` | O(C) upper bound at fixed depth and antenna/polarization count; invalid lanes can reduce work |
| Channel packing/export | Sionna `Paths`, `.cir(...num_time_steps=1)` | O(C+D); packing uses counters/scatters, not a required global comparison sort |
| Per-path voltage synthesis | `receiver.synthesize_voltage` | **O(PN)**, a Python path loop with vectorized sample operations |
| Per-link diagnostic filters/power | `sdr.SDRNetworkReceiver.capture` | O(TRN), fixed-order IIR per link |
| Receiver LO, noise, filter, ADC | same `capture` | O(RN), fixed-order filter and component quantization |

For fixed-size patterns and fixed geometry, the useful shorthand is:

```
work/update ≈ O(TR(S+M) log F + PN + TRN)
```

There is also shared table preparation, CDF search, device setup and launch/JIT
cost as detailed above. With approximately constant retained paths per link,
`P ≈ TR × p`, so the dominant sample stage is `O(TR p N)`. In the worst case
`P ≤ C`, giving `O(TR(S+M+1)N)` for synthesis.

Consequently, doubling transmitters alone approximately doubles work; doubling
receivers alone also approximately doubles work. Growing both as `n` gives
O(n²) link work. Doubling I/Q samples doubles synthesis work but **does not
repeat ray tracing**. Increasing terrain detail adds both BVH traversal cost
and potentially M exhaustive specular candidates; the latter grows directly
with distinct planes, even if few specular paths survive.

The cached plane/mesh analysis runs when geometry changes, not on each moving
radio pose. It visits F triangles; exact rational plane canonicalization has
additional coordinate bit-complexity. BVH construction/refitting is a separate
geometry-change cost. These benchmarks move RF mounts over a static scene;
they do not measure moving airframe meshes or dynamic BVH updates.

A practical latency model is a sum of stage costs, not merely Big-O:

```
Lcpu = fixed/JIT cost + pose + tables + draws + queries + fields/packing
       + cIQ·P·N + cfilter·T·R·N + creceiver·R·N
```

The path loop holds only one path's samples at a time, so current synthesis
working memory is O(N), in addition to O(C+D) channel storage and O(RN)
returned blocks. Work is O(PN) without requiring an O(PN) allocation.

## Compare the CPU model with measurements

For the default tones, each path currently performs approximately three complex
exponential evaluations per sample: the tone waveform, TX reference/LO phase,
and Doppler phase. It also performs complex products, accumulation, allocation
and finite checks. The RX LO is evaluated once per receiver/sample vector and
multiplied into each link. The original synthesis uses complex128 arithmetic
and returns complex64. These constants matter much more than the small filter.

Using **means consistently** across the measured timed epochs:

| Case | Mean paths P | Contributions PN | Measured CPU I/Q+receiver | Cost/contribution |
|---|---:|---:|---:|---:|
| 2 TX / 1 RX | 810.9 | 3.529 M | 221.5 ms | 62.8 ns |
| 2 TX / 2 RX | 1,463.4 | 6.369 M | 392.4 ms | 61.6 ns |
| 100 TX / 1 RX | 42,519.6 | 185.045 M | 10,861.1 ms | 58.7 ns |

That is **15.9–17.0 million contributions/s** on the measured two-core-quota
host. Calibrate only on the small one-receiver case:

```
Predicted I/Q+receiver milliseconds = 62.77 × P × N / 1,000,000
```

This predicts 399.8 ms versus 392.4 ms for the two-receiver batch (+1.9%), and
11,615.6 ms versus 10,861.1 ms for 100 TX (+6.9%). The dominant linear work
model agrees with these measurements. The coefficient includes receiver and
diagnostic overhead; it is not an isolated complex-exponential microbenchmark.
These are three workload observations at one sample/ray budget, not a complete
independent parameter-sweep validation. Different callable waveforms change
this coefficient.

Adding each case's **measured** channel cost gives:

| Case | CPU model total | Measured mean service | Measured sustained updates/s |
|---|---:|---:|---:|
| 2 TX / 1 RX | 245.1 ms | 245.1 ms | 4.079 |
| 2 TX / 2 RX | 419.7 ms | 412.4 ms | 2.425 |
| 100 TX / 1 RX | 12,303.2 ms | 11,549.0 ms | 0.087 |

This validates the synthesis model, **not an independent channel-time
prediction**. Channel means were 23.6, 20.0 and 687.6 ms. Shared setup,
vectorization, BVH traversal, packing, synchronization and compilation make
its constant vary; three heterogeneous cases cannot isolate them. In
particular, the smaller channel time for the two-RX batch shows why dividing
batch latency by receiver count is unreliable. These timings concern the
915 MHz dipole SDR fixture and are not interchangeable with the older
24.125 GHz directional-antenna propagation-only benchmark.

The code contains no per-update ray trace for every fast-time sample, and no
exponential bounce tree at the accepted depth of one. The large CPU latency
is explained chiefly by repeatedly evaluating 185 million sample/path terms.

## GPU work, parallel execution and latency

A GPU does **not** change O(PN) work into O(1). At fixed GPU size, large workloads
still scale approximately linearly with contributions. It supplies parallel
execution and different effective throughput. Launch/transfer costs make small
workloads overhead-limited; occupancy and bandwidth matter as work grows.

For a resident implementation, use:

```
Lgpu ≈ Lchannel + Lother + (P·N / effective_contributions_per_second)
```

Here Lchannel includes GPU proposal draws, tracing, material/field evaluation
and channel packing. Lother includes kernel launch/synchronization, output
transfer and receiver diagnostics/noise/filter/ADC. We add stages conservatively
without assuming overlap. RPC, network, queueing and RF skill processing remain
excluded. CUDA availability alone does not implement this pipeline.

### Why the implementation changes the estimate

**Literal sample-wise port:** move the three phase evaluations and products to
GPU kernels. Work remains O(PN) and special-function throughput can dominate.
Launching one Python kernel sequence per path would retain O(P) launch overhead
and is excluded from this estimate: kernels must already be batched/tiled.
The estimates assume FP32 inner synthesis with precision handled separately;
a literal complex128 port can be much slower on a consumer GPU.

**Fused analytic phase:** for tones or an analytic chirp, combine waveform,
clock and Doppler phase before evaluating sine/cosine. This reduces three
sample-wise phasors to one. Work remains O(PN), with a smaller constant.
An arbitrary Python waveform callable cannot automatically use this kernel;
it needs a supported GPU representation and potentially different cost.

**Tiled phase recurrence:** for a tone, each path is
`x_p[n] = c_p exp(jω_p n)`. Compute its initial phase and step once, then use
`x_p[n+1] = q_p x_p[n]`. For LFM, write the phase as
`α_p n² + β_p n + γ_p`; the phase step is itself a rotating phasor:

```
x[n+1] = x[n] · u[n]
u[n+1] = u[n] · exp(j·2α)
```

This is mathematically the same signal for a continuous tone or a quadratic
chirp within its support, including fixed delay, constant clock scale and
narrowband Doppler. Pulsed waveforms additionally need delay/support masks,
and chirp resets need explicit boundaries. It does not change the accepted
propagation physics or remove per-path Doppler.

Reinitialize phases at tile boundaries, then generate short sample tiles and
reduce across paths. Trigonometric setup becomes roughly O(P ceil(N/B)) for
tile length B, while O(PN) complex recurrence/accumulation remains. A simple
tiled implementation has a recurrence dependency of B steps and a path
reduction tree; enough paths/tiles are needed to occupy the GPU. It is not
legitimate to divide CPU latency by CUDA core count.

Finite precision needs separate validation: reduce large absolute phases
accurately before FP32 generation, check recurrence drift and accumulation
error, and preserve weak signals during cancellation. Periodic resets,
pairwise reduction or compensated sums add cost. The current CPU complex128
intermediates cannot be silently replaced while promising identical accuracy.

## Explicit GPU engineering estimate

Reference class: **RTX 4090, one GPU per receiver**, static resident terrain,
compiled warm kernels, GPU-side sampling, compact channels and tiled FP32
synthesis with validated phase handling. This names an estimate anchor, not a
purchase minimum. NVIDIA publishes 16,384 CUDA cores, 2.52 GHz boost and 24 GB
memory [1]. CUDA's instruction table reports 128 FP32 arithmetic results and
16 fast sine/cosine results per SM per clock for compute capability 8.9 [2].
Using 128 SMs gives an idealized ~5.16 billion scalar sine/cosine results/s,
or ~2.58 billion pairs/s before range reduction, other instructions, occupancy
and reduction. This illustrates why quoted FP32 TFLOPS cannot price a
complex-exponential kernel.

The throughput assumptions are:

| Proposed kernel | Assumed completed contributions/s | Basis |
|---|---:|---|
| Three sample-wise phasors | 0.25–0.75 billion | Six sine/cosine results per contribution; below the ideal SFU bound |
| One fused phasor | 0.75–2.5 billion | Two sine/cosine results; upper endpoint close to the ideal fast-intrinsic bound |
| Tiled tone/LFM recurrence | 30–100 billion | Arithmetic rather than one sin/cos pair per contribution; aggressive tiled-kernel engineering target |

The recurrence rates are assumptions, not published benchmark rates. At roughly
16–40 real arithmetic operations per contribution, they imply approximately
0.48–4 TFLOPS, a fraction of this device's theoretical FP32 arithmetic capacity.
Dependencies, memory, registers, reductions and precision handling can still
prevent those rates. Ordinary accurate math functions can also be much slower
than fast intrinsics; validated accuracy is part of the assumption.

For the small worker, assign 0.7–2 ms to channel computation and 0.3–0.8 ms to
other costs. For 100 TX, assign 2–8 ms to the channel and 0.5–2 ms to other
costs. These allowances are **unmeasured**. The large query count alone costs
1.46 ms at an assumed effective 250 M scene queries/s, leaving additional
budget for proposal generation, fields, packing and launch costs. These
allowances require host sampling to be removed: its current 18.8 ms median
already exceeds the entire 120 Hz budget.

Applying the formula produces these local service envelopes:

| Implementation | 2 TX / 1 RX latency | Serial capacity | 100 TX / 1 RX latency | Serial capacity |
|---|---:|---:|---:|---:|
| Literal three-phasor GPU port | ~6–17 ms | ~60–175 Hz | ~250–750 ms | ~1.3–4 Hz |
| Fused analytic-phase GPU | ~2.4–7.5 ms | ~130–415 Hz | ~77–257 ms | ~4–13 Hz |
| Tiled tone/LFM recurrence GPU | ~1–3 ms | ~340–965 Hz | ~4.4–16.2 ms | ~60–230 Hz |

These are endpoint sums and reciprocal service times, **not p50/p95 statistics,
measured sustained rates or real-time guarantees**. They assume the same path
counts as the CPU runs. More retained paths increase the sample stage directly;
more triangles/planes increase the channel stage. A different GPU, waveform,
accuracy requirement or scene requires new coefficients.

Phase fusion and recurrence can also improve a CPU implementation. The CPU
numbers above describe the current code; the recurrence rows compare it with a
proposed algorithm as well as different hardware. They are not a pure GPU
speedup measurement.

A useful central planning point for 100 TX is **about 8 ms / 120 updates/s**:
4 ms channel + 1 ms other + 185 M / 60 billion contributions/s ≈ 8.1 ms.
That has essentially no deadline margin. I would target 120 Hz in development
but would not promise it. A 200 Hz / 5 ms deadline requires the favorable end
of the envelope and additional transport/scheduling margin. It needs measured
latency tails, not just average throughput.

The **current** CUDA option keeps NumPy synthesis and host proposals, so it
still has approximately 218 ms / 10.85 s of median CPU work in these two cases.
The fast table above requires a redesign, not merely `--backend cuda`.

Keep intermediate contributions in registers/shared memory and reduce tiles:
a full 185 M-element complex64 matrix is ~1.48 GB (decimal) before temporary
buffers, while output ADC codes are only 16 KiB per receiver block. Sample-wise
materialization and rereading can make memory traffic the dominant term.
VRAM minimum and the scene BVH footprint remain unmeasured.

For 100 TX / 10 RX, each of ten independent GPUs has the one-RX work above.
Aggregate throughput can increase tenfold on adequate independent resources;
per-receiver latency does not fall tenfold. Latency to all ten outputs depends
on the slowest worker plus coordination, and tail/outlier behavior is unmeasured.
At requested rate f, a serial worker needs `f × mean_service_seconds < 1` for
queue stability. Delivery latency further includes queueing and RPC/transport.
The serial service estimates do not rely on pipelining to hide latency.

## Reproduce the arithmetic

```
.venv/bin/python benchmarks/analyze_sdr_scaling.py
```

This reads the three CPU reports and writes
[the machine-readable model](benchmarks/results/sdr_scaling_analysis.json),
including held-out CPU predictions and each GPU scenario's assumptions.
It does not execute a GPU benchmark or modify the RF implementation.

Code references: [CPU path loop](src/airsim_rf/receiver.py),
[SDR receive chain](src/airsim_rf/sdr.py),
[antenna proposals and diffuse visibility](src/airsim_rf/scattering.py),
[specular candidates and geometry cache](src/airsim_rf/single_bounce.py).
Pinned Sionna 2.2.0 references:
[solver orchestration](https://github.com/NVlabs/sionna-rt/blob/v2.2.0/src/sionna/rt/path_solvers/path_solver.py),
[field calculation](https://github.com/NVlabs/sionna-rt/blob/v2.2.0/src/sionna/rt/path_solvers/field_calculator.py),
[path packing](https://github.com/NVlabs/sionna-rt/blob/v2.2.0/src/sionna/rt/path_solvers/paths.py).

[1] NVIDIA, [GeForce RTX 4090 specifications](https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4090/), accessed 2026-10-03.

[2] NVIDIA, [CUDA C++ Programming Guide 12.6.3: native arithmetic instruction throughput](https://docs.nvidia.com/cuda/archive/12.6.3/cuda-c-programming-guide/index.html#arithmetic-instructions-throughput-native-arithmetic-instructions), and the same guide's [sine/cosine and intrinsic-function discussion](https://docs.nvidia.com/cuda/archive/12.6.3/cuda-c-programming-guide/index.html#arithmetic-instructions), accessed 2026-10-03. Hardware maxima constrain the estimate; they are not measured application throughput.
