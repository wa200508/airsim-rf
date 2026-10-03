# Runtime assessment: 100 transmitters, 10 receivers

Assessed 2026-10-03 against application commit
`557bf23ab87b3a552d1f79378cc26aebc4beabe4`, Sionna RT 2.2.0 at
`15b5ee036917a4c2a9b6420e05570b77717e2fcc`, Mitsuba 3.9.1 and Dr.Jit 1.5.0.
The accompanying benchmark scripts/results were added during this assessment.

The repository is a tested distributed radar prototype: all 28 Python tests
pass. It is ready for performance investigation. It is not yet a general
AMS-GRA RF simulation plane. The deployed worker is one monostatic FMCW radar
with direct-path point-target echoes; Sionna can model independent radio links,
but the application needs a general channel-to-I/Q backend.

No GPU or live AirSim server is available here. CPU numbers below are measured.
GPU timing tables are conditional arithmetic, not measured GPU performance.

## Assumptions and scope

- 100 independent transmitting platforms, 10 physical receiver front ends,
  initially one GPU per receiver handling all 100 transmitters.
- 120 Hz world truth, with separately scheduled propagation refresh and I/Q.
- One RF band and one antenna per node initially. A Sionna scene has one carrier
  frequency; multiple bands and heterogeneous antenna responses require more work.
- Receiver bandwidth is unspecified. Use **20 MS/s complex I/Q** as an initial
  arithmetic example, plus narrower/wider cases. This is not a user-confirmed
  requirement. Complex sample rate approximately equals occupied bandwidth at
  ideal Nyquist; practical filters generally require margin.
- Network sizing below assumes transmitter waveforms can be generated locally
  on RF GPUs from shared specifications/seeds. External skills streaming raw
  transmitter I/Q require much larger ingress/fanout capacity, calculated below.
- Ray density, interaction depth, path retention, scene geometry/materials,
  motion and acceptable signal error must be specified. "Full scene" needs
  convergence criteria, including clutter and weak paths, at finite depth.
- RadarSimPy can be a skill/reference tool; it is not required by the plane or
  included in this hardware estimate.

## Code audit

| Code | Existing behavior | Work needed |
| --- | --- | --- |
| `distributed/worker.py:_initialize` | Instantiates fixed-profile `FMCWRadar` | Independent transmitters, waveform registry and general receiver backend |
| `fmcw.py:capture` | Fresh solve per chirp, `max_depth=0`, virtual RX per point target | General reflected TX–RX channels; 100 point targets are not 100 emitters |
| `receiver.py:RFReceiver.capture` | Asserts one TX/RX; CIR expanded to ADC time and exported to NumPy | Compact multi-TX channels, GPU signal synthesis |
| `receiver.py:synthesize_voltage` | Complex128 promotion/copy, CPU loop per path | Bounded GPU blocks or equivalent efficient filtering |
| `ams/backend.py:TuneRf` | Accepts only fixed radar frequency/sweep/ADC rate; rejects gain/AGC changes | Functional tuning/configuration for broad RF skills |
| `distributed/coordinator.py:run_simulation` | RF cadence comes from radar PRI; pauses physics for every barrier | Separate truth, propagation and sample schedules |
| `distributed/coordinator.py:AirSimSource.snapshot` | Separate sequential RPC per robot | Bulk/subscribed truth for about 110 platforms |
| `distributed/protocol.py` | Compressed NPZ with several sample representations; 8 MiB response limit | Efficient continuous sample transport and backpressure |
| `distributed/worker.py:capture` | One SC16 UDP datagram per capture | Packetization, sequence/timing and loss policy for wideband streams |

Native MEL interoperability remains useful, but tests cover the exercised radar
contract. Configuring 120 Hz simulation time does not establish 120 wall-clock
updates/s. Offline execution preserves timestamps while slowing wall time.

## New measurements

`benchmark_network_paths.py` constructs actual independent Sionna radios;
it does not use the radar shortcut. Endpoints move between solves, while meshes
remain static. It times endpoint updates, synchronized propagation and one-epoch
NumPy CIR export. Waveforms, IF/ADC, mesh/BVH updates, AirSim and transport are
excluded. Host: two-core CPU quota, 8 GiB memory limit, no usable CUDA backend.

The street scene contains **five objects and 74 triangles**. Depth is three,
with specular reflection/default refraction. Diffraction is disabled. The
diffuse case sets an artificial material scattering coefficient of 0.3;
built-in canyon materials otherwise have zero diffuse scattering.

| Independent radios | Rays/TX | Median | Valid paths | Peak host RSS | Timed iterations |
| --- | ---: | ---: | ---: | ---: | ---: |
| 100 TX, 1 RX, empty LoS | No bouncing | 310 ms | 100 | 188 MiB | 20 |
| 100 TX, 1 RX, street | 1,000 | 142 ms | 1,304–1,306 | 980 MiB | 5 |
| 100 TX, 1 RX, street | 10,000 | 351 ms | 1,477–1,482 | 1,076 MiB | 10 |
| 100 TX, 1 RX, street | 100,000 | 2,299 ms | 1,589 | 2,041 MiB | 3 |
| 100 TX, 1 RX, street, batches of 10 TX | 10,000 | 927 ms | 1,479–1,483 | 284 MiB | 10 |
| 100 TX, 10 RX together, street | 10,000 | 817 ms | 15,275–15,276 | 2,058 MiB | 5 |
| 100 TX, 1 RX, street, diffuse | 1,000 | 153 ms | 6,643–6,647 | 1,019 MiB | 5 |

These are short screening runs, not reliable tail-latency estimates. Independent
runs differ in JIT/cache state and cloud scheduling: the slower LoS case does
not imply reflections are cheaper. Host RSS is a process high-water mark, not
GPU VRAM. Exact arguments/distributions are in `benchmarks/results/network_cpu_*.json`.

Batching reduced memory but made this CPU run about 2.6 times slower. Shared
10-RX tracing cost about 2.3 times the 1-RX tracing, showing possible source-ray
reuse; this does not compare one GPU against ten GPUs. Higher ray counts still
found paths. Stable aggregate channel power is insufficient to establish
complex I/Q convergence, and a non-saturated output does not prove a candidate
cap never discarded useful paths.

`benchmark_signal_sum.py` exercises the actual NumPy voltage synthesizer with
1,000 synthetic paths, one tone and 4,096 samples. At 20 MS/s the block represents
**0.2048 ms**, but median compute was **106.9 ms**, about **522 times slower than
real time**. Throughput was 38 million path/sample contributions/s. Tracing,
coefficient generation, filtering, ADC and transport are excluded. This is a
microbenchmark, not an implemented multi-transmitter simulation.

## Tracing work and conditional GPU time

Sionna launch width is `num_sources * samples_per_src`. At each bounce the
solver also loops over receivers for visibility queries. Image-method path
validation and field calculation add further work. BVH traversal avoids a
brute-force ray-times-triangle loop, but geometry affects traversal cost.

For 100 TX on one receiver GPU, S rays/TX and depth three, the rough work is:

```
launched rays                = 100 * S
primary + visibility queries ~ up to 2 * 100 * S * 3
```

Early termination reduces the count. This estimate excludes image-method
validation, hashing, fields, allocation and dynamic geometry updates.

| Rays/TX | Rays/RX GPU | Approximate queries/refresh | Rate needed at 120 Hz | At assumed 100 M queries/s | At assumed 1 B queries/s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 100,000 | 600,000 | 72 M/s | 6 ms | 0.6 ms |
| 10,000 | 1,000,000 | 6,000,000 | 720 M/s | 60 ms | 6 ms |
| 100,000 | 10,000,000 | 60,000,000 | 7.2 B/s | 600 ms | 60 ms |
| Default 1,000,000 | 100,000,000 | 600,000,000 | 72 B/s | 6 s | 600 ms |

The assumed rates are sensitivity points, not RTX specifications or measured
Sionna rates. Peak vendor ray rates omit RF field calculation and control flow.
An unconditional GPU frame-time prediction would be unjustified.

The planning hypothesis to test is milliseconds to tens of milliseconds for
bounded sparse-path scenes at 1,000–10,000 rays/TX, and tens to hundreds of
milliseconds or more as density/clutter increases. This is **unverified**.
Fresh high-density full tracing every 8.33 ms should not be assumed feasible.
Cached channels with continuous phase and event-driven refresh are a stronger
real-time candidate.

Receiver sharding repeats primary shooting ten times. Source-sharded tracing
with 10 TX and all 10 RX on each of ten GPUs needs roughly 3.3 million queries/GPU
at 10,000 rays/TX versus 6 million for receiver sharding. It would distribute
compact channels to receiver synthesis workers. Compare the simpler receiver
sharding and shared/source-sharded tracing before buying a large cluster.

## Memory findings from source

Sionna defaults rays/TX **and candidate capacity/TX** to 1,000,000. Candidate
capacity is allocated across all sources before shrinking to actual paths.
`PathsBuffer` declares approximately `28 * max(1,depth) + 32` bytes/candidate,
excluding validity masks, coefficients, diffraction and temporaries. At depth
three it is about 116 bytes:

| Candidate cap/TX, 100 TX | Declared candidate payload |
| --- | ---: |
| 1,000 | 11.6 MB |
| 10,000 | 116 MB |
| Default 1,000,000 | 11.6 GB |

These are logical capacities; JIT materialization/lifetimes affect actual peak
allocation. Independently, shooting/bouncing uses **two uint32 hash-counter
arrays**, each with at least 1,000,000 entries/TX. Combined payload is **800 MB
for 100 TX**, even with small path caps, or 80 MB for a 10-TX batch. Clearing
800 MB at 120 Hz represents 96 GB/s of writes/GPU before useful field work.

Sample history holds about 28 bytes/ray/interaction: its logical payload at
default density/depth three is another 8.4 GB. It can use register/local
storage; this is not a measured global VRAM allocation. Geometry, acceleration
structures, fields, intermediate copies and waveforms add memory. Default
settings can stress a 24 GiB GPU; configure budgets and measure peak VRAM.

## Signal generation and host transfers

Direct summation needs approximately `100 * P * Fs` path/sample contributions/s
per RX, where P is retained paths/TX and Fs is complex sample rate. Independent
emitters need separate waveforms, powers and oscillator references. Sum all
signals before receiver noise, filtering, clipping and ADC; add noise once per
physical front end. Deliver **ten mixed streams**, not 1,000 separated links.

For P=10 and Fs=20 MS/s the cost is **20 billion contributions/s/RX**, 200 billion
across ten receivers. Ten paths is only an arithmetic example: the measured
specular canyon averaged about 15/TX, the synthetic diffuse case about 66/TX.

Expanding `cir(num_time_steps=N, out_type="numpy")` across ADC time produces:

| Fs, 100 TX × 10 padded paths/TX | Complex64 coefficients/RX per 8.33 ms | Continuous coefficient GPU-to-host traffic |
| --- | ---: | ---: |
| 1 MS/s | 66.7 MB | 8 GB/s |
| 20 MS/s | 1.33 GB | 160 GB/s |
| 100 MS/s | 6.67 GB | 800 GB/s |

CPU complex128 promotion/indexing adds copies. Padding follows the maximum
path count, so mean valid paths can underestimate memory. PCIe 4.0 x16's
theoretical roughly 32 GB/s, or PCIe 5.0 x16's roughly 64 GB/s, cannot sustain
the 20 MS/s coefficient transfer. A larger GPU does not fix that architecture.

Keep compact gains, delays, Doppler, path identities and waveform buffers on
GPU; generate/mix bounded blocks and transfer final I/Q. Aggregate delay/Doppler
models or FFT convolution may reduce dense diffuse-path work, provided they
preserve required accuracy. Fractional delay, arbitrary waveforms and motion
need correct treatment. Use relative block time to preserve precision at high
sample rates rather than large Unix-epoch float seconds.

## Transport and world simulation

SC16 uses four bytes/complex sample; complex64 uses eight. Rates assume one
consumer stream/RX and omit headers/duplicate delivery.

| Fs/RX | SC16/RX | SC16 across 10 RX | Complex64 across 10 RX |
| --- | ---: | ---: | ---: |
| 0.1 MS/s | 0.4 MB/s | 4 MB/s | 8 MB/s |
| 1 MS/s | 4 MB/s | 40 MB/s | 80 MB/s |
| 20 MS/s | 80 MB/s | 800 MB/s (6.4 Gbit/s) | 1.6 GB/s (12.8 Gbit/s) |
| 100 MS/s | 400 MB/s | 4 GB/s (32 Gbit/s) | 8 GB/s (64 Gbit/s) |

The current radar averages only 128 × 200 = 25,600 samples/s/RX. Its transport
test does not characterize continuous wideband streaming. Recording all ten
SC16 streams for one hour needs 2.88 TB at 20 MS/s or 14.4 TB at 100 MS/s.
Noise-like I/Q compresses poorly; provision sustained throughput or bounded
recordings. Skill/control results require much less bandwidth.

The table sizes **receiver output**, not raw transmitter input. If 100 external
skills each stream a continuous 20 MS/s transmitter waveform, input alone is
8 GB/s SC16 (64 Gbit/s), or 16 GB/s complex64 (128 Gbit/s), before distributing
those waveforms to ten receiver workers. If every worker needs every raw
waveform, each worker has that ingress rate and total switch egress is ten times
larger. Multicast can reduce source uplink duplication but cannot eliminate
receiver ingress or switch fanout. Prefer local generation from shared emission
descriptions/seeds when possible; arbitrary external I/Q playback must have an
explicit placement/distribution plan. Co-locating a skill with its GPU worker
can also avoid shipping its receiver output through a central collector.

The NPZ response includes multiple representations of a sample; at 100 MS/s
an 8.33 ms block would exceed the 8 MiB cap before compression. One UDP datagram
can hold only about 16,376 SC16 samples even before avoiding IP fragmentation.
Implement appropriate streaming/MTU-aware packetization, timing and loss
handling. The native bare-SC16 boundary needs an agreed separate timing contract
if its wire format is retained.

Current AirSim truth collection would make about 110 sequential robot RPCs.
At assumed 0.1 ms/RPC that alone is 11 ms, or 55 ms at 0.5 ms/RPC, before
physics/clock calls. These are sensitivity examples, not measured AirSim latency.
Batch/publish all platform truth. Actual 110-platform physics, moving mesh/BVH
updates and rendering remain untested. The planning workload does not include
cameras on every platform.

## Hardware to evaluate

No purchase minimum has been validated. These are practical starting allocations.

| Resource | Development baseline | Why |
| --- | --- | --- |
| Receiver GPU | NVIDIA RTX class with 24–32 GiB, e.g. RTX 4090/5090 class | CUDA/OptiX tracing and GPU sample generation; one card tests a whole RX shard |
| Larger scene GPU | 48 GiB RTX workstation class, e.g. RTX 6000 Ada class | More geometry/candidate/clutter capacity; does not cure compute/launch bottlenecks |
| RF host CPU/RAM | Start with 8 physical cores and 32 GiB/GPU; 64 GiB preferred | Control, packetization, staging and geometry; measure shared-host contention |
| World host | Start around 16 physical cores/64 GiB, separate rendering GPU when needed | Benchmark 110-platform physics and selected sensors independently |
| Output network, 20 MS/s | 2.5/10 GbE per RX; 10 GbE aggregate for SC16, 25 GbE preferred | Payload is 6.4 Gbit/s aggregate SC16 or 12.8 Gbit/s complex64 |
| Output network, 100 MS/s | 10 GbE/RX; 50/100 GbE aggregate SC16, 100 GbE complex64 | Payload is 32/64 Gbit/s aggregate |
| External raw TX I/Q, 20 MS/s each | Separately size 100/200 GbE-class ingress per RX or redesign placement/distribution | All 100 sources are 64/128 Gbit/s payload per worker before headroom |
| Software | Native Linux x86-64, tested Python 3.12/pinned dependencies, NVIDIA Container Toolkit | Current container/Compose target |

[Mitsuba 3.9.1 requirements](https://github.com/mitsuba-renderer/mitsuba3/blob/v3.9.1/README.md#requirements)
specify NVIDIA driver >=535; newer cards can require newer drivers. Verify CUDA
and OptiX inside the actual container. Installing a toolkit alone is insufficient.
None of these GPUs has been tested here; AMD/Apple are outside the current backend.
Ray traversal, FP32 throughput, bandwidth and VRAM matter more than advertised
tensor/AI throughput. Ten GPU memories are not one shared pool.

## Engineering and acceptance gates

1. Independent emissions and configurable receivers driven by AMS control;
   modulation/detection/radar processing live in skills, with mixed I/Q from the plane.
2. Aligned RF/world geometry, moving meshes, bulk truth/BVH updates, and a
   land-cover material/clutter layer with defined fidelity.
3. Compact persistent channels and GPU waveform application. Validate amplitude,
   delay, phase, oscillator offsets, Doppler, sample continuity, noise and ADC.
4. Independent truth, channel-refresh and I/Q block schedules. Cached channels
   need amplitude/delay evolution, phase continuity and invalidation on changes
   to visibility, acceleration, materials or moving scatterers. Frozen CIR plus
   Doppler rotation is insufficient for every condition.
5. Ray/path convergence tests, efficient streaming and backpressure.
6. Real-scene GPU measurements first at 100 TX/1 RX, then ten workers with actual
   AirSim and skills. Measure sustained throughput, max-worker latency, VRAM,
   throttling and long-run tails.

The existing coordinator performs 200 RF epochs/s plus 120 truth steps/s, so
each chirp does not get an 8.33 ms wall-time budget. A general pipeline can
allow bounded latency different from 8.33 ms if the skill/test contract permits;
buffering cannot cure sustained throughput shortfall. An initial integrated
budget could reserve about 5 ms/epoch for propagation, with remaining time for
world/transport work, but this must come from integrated measurement.

Ten independent workers each meeting a deadline 99% of the time would all meet
it only `0.99^10 = 90.4%` of epochs. Measure tails and correlations, not just
median kernels. Offline runs remain valid when timestamps/physics are preserved.

## Reproduction

From the repository root after bootstrap:

```bash
.venv/bin/python benchmarks/benchmark_network_paths.py --backend cpu --tx 100 --rx 1 --rays 10000 --path-cap 1000 --iterations 10 --warmup 3 --output network_cpu.json
.venv/bin/python benchmarks/benchmark_signal_sum.py --paths 1000 --samples 4096 --sample-rate 20000000 --iterations 10 --output signal_cpu.json
```

On a GPU host, first measure the receiver shard, then compare shared tracing
and a diffuse scene. Sweep rays through 1,000/10,000/100,000 and TX batches
through 10/25/100; keep path caps explicit.

```bash
CUDA_VISIBLE_DEVICES=0 .venv/bin/python benchmarks/benchmark_network_paths.py --backend cuda --tx 100 --rx 1 --rays 10000 --path-cap 1000 --iterations 200 --warmup 20 --output network_gpu.json
CUDA_VISIBLE_DEVICES=0 .venv/bin/python benchmarks/benchmark_network_paths.py --backend cuda --tx 100 --rx 10 --rays 10000 --path-cap 5000 --iterations 200 --warmup 20 --output network_gpu_shared.json
CUDA_VISIBLE_DEVICES=0 .venv/bin/python benchmarks/benchmark_network_paths.py --backend cuda --tx 100 --rx 1 --rays 1000 --path-cap 5000 --diffuse --iterations 200 --warmup 20 --output network_gpu_diffuse.json
```

Scripts ship under `/opt/airsim-rf/benchmarks/` in the next container build.
Use GPU Compose's driver capabilities (`compute,utility,graphics`) or equivalent.
The script synchronizes timings and records GPU/driver inventory; collect peak
VRAM separately. Use `--scene /path/to/scene.xml` for operational geometry.
Built-in canyon results cannot establish operational fidelity. The signal-sum
benchmark is CPU-only. The diffuse material coefficient is synthetic, not a
calibrated land-cover model.

Sionna source:
[defaults](https://github.com/NVlabs/sionna-rt/blob/15b5ee036917a4c2a9b6420e05570b77717e2fcc/src/sionna/rt/path_solvers/path_solver.py#L163),
[candidate allocation](https://github.com/NVlabs/sionna-rt/blob/15b5ee036917a4c2a9b6420e05570b77717e2fcc/src/sionna/rt/path_solvers/sb_candidate_generator.py#L110),
[hash counters](https://github.com/NVlabs/sionna-rt/blob/15b5ee036917a4c2a9b6420e05570b77717e2fcc/src/sionna/rt/path_solvers/sb_candidate_generator.py#L345),
[CIR expansion](https://github.com/NVlabs/sionna-rt/blob/15b5ee036917a4c2a9b6420e05570b77717e2fcc/src/sionna/rt/path_solvers/paths.py#L603),
[mesh updates](https://github.com/NVlabs/sionna-rt/blob/15b5ee036917a4c2a9b6420e05570b77717e2fcc/src/sionna/rt/scene_object.py#L563).
