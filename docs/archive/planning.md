# Planning

Historical measurements and planning assumptions. These chapters preserve prior configurations; use [current performance](../performance.md) for the qualified GPU workload.

- [Performance](#performance)
- [Per Pulse Runtime](#per-pulse-runtime)
- [Optimization](#optimization)
- [Network Runtime](#network-runtime)
- [Gpu Runtime](#gpu-runtime)
- [Sdr Runtime](#sdr-runtime)
- [Sdr Complexity](#sdr-complexity)
- [Affordable Realtime Rf](#affordable-realtime-rf)
- [P100 Gpu Pipeline](#p100-gpu-pipeline)

<a id="performance"></a>

## RF timing versus a 120 Hz simulation



**Runtime context (2026-10-05):** Historical small point-target radar/chirp measurements, not continuous multi-emitter I/Q or full environmental multipath. See [current runtime and wall-clock costs](runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

The current accepted assumptions and updated results are in
[PER_PULSE_RUNTIME.md](planning.md#per-pulse-runtime): one channel epoch per pulse and
at most one scene interaction, with compact coefficients and analytic Doppler.

For the broader AMS-GRA plane (100 independent transmitters, 10 receivers and
moving-platform multipath), see [NETWORK_RUNTIME.md](planning.md#network-runtime).
It audits current limitations and separates tracing, wideband I/Q synthesis,
transport and hardware sizing using new multi-transmitter measurements.
The measurements below remain specific to the monostatic radar prototype.

A 120 Hz simulation tick has **8.333 ms** available for all synchronous work.
On this machine, the current Sionna-based RF adapter does **not reliably fit**
that deadline even before physics, rendering, RPC or data publication are added.
The results are CPU measurements, not predictions for your home GPU.

The original two-target implementation solved each target separately. Targets
are now batched into one Sionna `PathSolver` call, with persistent receiver
objects and cached noise-filter coefficients. This preserves echo phase and
target mapping; a new test compares a batched signal to the sum of individual
returns, including targets excluded by beam direction or zero RCS.

![CPU RF update timing against the 120 Hz deadline](../../benchmarks/cpu_timing.png)

### Measured results

Run on 2026-10-02 with Python 3.12.14, Sionna RT 2.2.0, and Mitsuba's
`llvm_ad_mono_polarized` backend. The VM exposes three AMD EPYC 9V74 logical
CPUs, with a cgroup quota of two CPU cores and an 8 GiB memory limit. No GPU
was available. Cloud host contention and JIT/cache state affect the numbers.

| Workload | Samples | Median | p95 | Deadline misses |
| --- | ---: | ---: | ---: | ---: |
| Original, 2 targets, empty scene, one chirp + FFT | 100 | 18.92 ms | 22.57 ms | 100/100 at 8.33 ms |
| Batched, 2 targets, empty scene, short run | 200 | 9.44 ms | 10.31 ms | 110/200 at 8.33 ms |
| Batched, 2 targets, empty scene, longer run | 1000 | 10.11 ms | 11.83 ms | 838/1000 at 8.33 ms |
| Batched, 8 targets, empty scene | 200 | 7.51 ms | 8.33 ms | 10/200 at 8.33 ms |
| Batched, 2 targets, street scene (5 objects) | 200 | 11.78 ms | 13.10 ms | 200/200 at 8.33 ms |
| Batched, 2 targets, complete 16-chirp frame | 30 | 162.85 ms | 177.51 ms | 30/30 at 80 ms |

The 8-target run happened to be faster than the 2-target runs in this cloud
environment; do not infer a monotonic scaling curve from these separate runs.
The longer 2-target measurement was added to characterize timing variability.
Its worst sample was 75.14 ms, while p99 was 13.19 ms. Stored JSON files in
`benchmarks/results/` retain the full distributions and exact command arguments.

The street case uses Sionna's built-in `simple_street_canyon`; rays test geometry
and may be obstructed. It is not an aligned AirSim scene. All solves use
`max_depth=0` (direct paths/blocked paths), so these timings do not characterize
specular multipath, diffuse scattering, diffraction or moving mesh updates.

Each measured update materializes NumPy path coefficients, generates the FMCW
IF signal, applies target RCS and antenna response, adds colored thermal noise,
and quantizes both ADC channels. `--fft` includes range FFT processing. The
benchmark moves the radar and preserves phase between updates. Returning NumPy
data synchronizes Sionna/Dr.Jit evaluation; the timing is not just GPU/CPU work
submission latency.

AirSim transport, native physics, Unreal rendering, mesh export, background
sensor workloads and NPZ writing are excluded. The benchmark therefore tests
the isolated RF workload, not a live integrated 120 Hz simulation.

Imports took approximately 1.2–1.3 s. First-update timing varied from roughly
15–44 ms for empty scenes and was about 541 ms for the street scene. Initialize
and warm the RF pipeline before measuring steady-state deadlines.

### Physics rate, chirp rate and RF refresh rate

The hardware profile's chosen PRI is 5 ms: **200 chirps/s**, while physics at
120 Hz advances about once every 8.33 ms. A 16-chirp RF frame spans 80 ms and
arrives at 12.5 frames/s if chirps are contiguous. These are separate rates.
Simply generating one chirp per physics tick changes the chirp schedule and
slow-time Doppler properties. Synthesizing a whole frame in every 120 Hz tick
would also represent the wrong sampling schedule.

The current CPU implementation cannot sustain the selected 200-chirp/s
schedule when re-solving Sionna paths for every chirp: the measured full frame
took about 164 ms for an 80 ms simulated interval. Offline steppable simulation
can still preserve timestamps and physical sampling while running slower than
wall time.

For real-time operation, the next performance step is to decouple the 120 Hz
physics clock, RF path refresh, and chirp synthesis. For slowly changing geometry,
an RF worker could refresh paths at a lower rate and evolve their phase/Doppler
between refreshes, while physics publishes timestamped states and the worker
buffers chirps. Occlusion/material/moving-object changes would need invalidation
and interpolation policy. This cached-channel worker is a proposed next step;
the published implementation performs a fresh solve on every chirp.

A GPU or more CPU capacity may improve throughput, but small solves can remain
sensitive to launch and Python overhead. Run the included benchmark on the
actual home system and aligned scene, then include physics/render/RPC costs
before choosing a synchronous RF deadline.

### Reproduce the measurements

After bootstrap, from the `airsim-rf` repository root:

```bash
.venv/bin/python benchmarks/benchmark_rf.py --backend cpu --targets 2 --fft --iterations 1000 --warmup 100 --output benchmark_home_cpu.json
.venv/bin/python benchmarks/benchmark_rf.py --backend cuda --targets 2 --fft --iterations 1000 --output benchmark_home_gpu.json
.venv/bin/python benchmarks/benchmark_rf.py --backend cuda --rf-scene builtin:simple_street_canyon --targets 2 --fft --output benchmark_home_street.json
.venv/bin/python benchmarks/benchmark_rf.py --targets 2 --chirps 16 --update-hz 12.5 --iterations 30 --warmup 5 --fft --output benchmark_home_frame.json
```

The first two commands evaluate an 8.33 ms budget. The last evaluates an 80 ms
frame budget. Each output reports import, setup, first-update latency, median,
p95, p99, maximum, deadline misses, and raw latency samples.

<a id="per-pulse-runtime"></a>

## Accepted model: one channel solve per pulse, one interaction



**Runtime context (2026-10-05):** Historical single-interaction channel-only timings and compact-tone microbenchmarks; the 144-path scene is not the all-valid-path stress workload. See [current runtime and wall-clock costs](runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

Updated 2026-10-03. This supersedes the depth-three planning baseline in
[NETWORK_RUNTIME.md](planning.md#network-runtime); its older results remain available
for comparison. Sionna/Mitsuba/Dr.Jit versions remain 2.2.0/3.9.1/1.5.0.

The small-scene specular path counts below do not establish distributed
ground-return coverage. [GROUND_SCATTERING.md](../terrain.md#ground-scattering) documents
the added TX/RX-aware diffuse sampling mode, its per-link budget, separate
runtime measurements and remaining roughness/temporal-coherence limitations.

### Model and implementation

Compute path geometry, gain and absolute delay once at the start of each pulse.
Hold them through fast time, with at most one scene interaction: direct paths
and single reflections. Default refraction, diffraction and diffuse scattering
are disabled in the new benchmark. Diffuse scattering can be exercised explicitly
with `--diffuse`, still at depth one, with a specified material coefficient.

Preserve narrowband Doppler by evolving phase analytically within the pulse:

```
h_p[n] = a_p(t_pulse) * exp(j * 2*pi * f_D,p * n/Fs)
v[n]   = sqrt(R*Ptx) * sum_p h_p[n] * x(t_pulse + n/Fs - tau_p)
```

This does not invoke ray tracing per ADC sample. Omitting this phase evolution
would remove the fast-time Doppler contribution to an FMCW beat. Geometry and
envelope delay still use the accepted frozen-within-pulse approximation.

The SISO `RFReceiver` now defaults to depth one, accepts only depths zero/one,
sets explicit ray/candidate budgets, calls Sionna once per capture, and requests
`cir(num_time_steps=1)`. It exports one gain, delay and Doppler value per path.
`synthesize_voltage` accepts these compact coefficients and applies Doppler
one path at a time. Its previous per-sample coefficient interface remains
available for callers that already supply time-varying channels.

The existing distributed worker still instantiates the direct-path monostatic
FMCW model. Changing that model to depth one by squaring a multipath radio
channel would not be a correct general radar scattering implementation.
The 100-TX network benchmark exercises actual radio links, but is not a new
production network worker. Multi-transmitter mixing, GPU synthesis, general
AMS receiver configuration and bulk AirSim truth are still required.

#### Native Sionna candidate discovery

`max_depth=1` stops the interaction chain at its first surface. It does **not**
disable shooting-and-bouncing candidate generation in native Sionna:
`sb_candidate_generator.py` invokes that generator for any depth greater than
zero. The image method subsequently refines discovered specular candidates.
There is no public switch for exhaustive first-order image-method discovery
without shooting. The optimization branch now adds an explicit
`SingleBouncePathSolver` adapter; see [OPTIMIZATION.md](planning.md#optimization).
The measurements below remain the native sampled baseline. The adapter has
separate paired measurements and does not enable diffuse or diffracted paths.

The earlier tracing measurements also used one CIR epoch per solve; they never
traced per fast-time sample. The earlier dense-memory warning concerned
time-expanded coefficients/Doppler and CPU copies, which this compact SISO
implementation now avoids.

### Test results

**30 Python tests pass.** A new analytic two-path test verifies fractional delay
and Doppler/phase continuity over two consecutive pulse blocks. The existing
real-Sionna free-space test still verifies physical voltage, absolute delay,
carrier phase and moving-receiver Doppler.
Another real-Sionna test verifies direct, floor-image and wall-image distances
of 1 m, sqrt(17) m and 2 m, excludes a second bounce, and compares the compact
moving-channel output with Sionna's time-expanded reference.

New screening measurements use moving independent radios, a static street scene
with five objects/74 triangles, LoS plus specular single reflections, and no
refraction. The host still has a two-core CPU quota, 8 GiB memory and no GPU.
They include synchronized propagation and one-epoch NumPy CIR export; exclude
waveform synthesis, receiver processing, moving meshes, AirSim and transport.

| Workload | Rays/TX | Timed iterations | Median | p95 | Valid paths |
| --- | ---: | ---: | ---: | ---: | ---: |
| 100 TX, 1 RX | 1,000 | 20 | 399 ms | 413 ms | 144 |
| 100 TX, 1 RX | 10,000 | 20 | 162 ms | 178 ms | 144 |
| 100 TX, 10 RX in one solve | 10,000 | 10 | 293 ms | 303 ms | 1,440 |

All samples missed the benchmark's 5 ms budget. The budget comes from the current
radar's 5 ms PRI (200 pulse epochs/s), not the separate 120 Hz world clock.
The benchmark assumes common pulse epochs for batching all transmitters; their
oscillator phases need not be shared. Staggered independent pulses need an
event scheduler that updates the relevant channels without solving every link
at every transmitter's event, and launch overhead must be measured.

The lower-ray run being slower is a real observed result. Separate cloud runs,
JIT behavior and fixed solver work prevent a simple monotonic inference. These
short runs do not certify tail latency or GPU speedups. Single-reflection path
counts were stable across this ray-count pair, but signal convergence still
requires checking weak paths and complex phase, especially in richer scenes.

The compact CPU signal microbenchmark (1,000 paths, 4,096 samples, one tone,
20 MS/s) took **88.2 ms median** for **0.2048 ms simulated**, about **431 times
slower than real time**. Coefficient storage fell from **65,536,000 bytes to
16,000 bytes**, a factor of 4,096. This measures storage, not a 4,096-fold speedup.
It uses constant gains with zero Doppler; the analytic Doppler case is verified
by tests. GPU sample generation remains necessary for this wideband workload.

### Revised work and memory budgets

For 100 TX and one RX GPU at depth one, approximate primary/visibility queries
per pulse are at most `2 * 100 * rays_per_TX`, before image-method validation,
field evaluation, hashing and other work. Early termination can reduce them.

| Rays/TX | Queries/pulse | Query rate at 200 pulses/s | At assumed 100 M queries/s | At assumed 1 B queries/s |
| --- | ---: | ---: | ---: | ---: |
| 1,000 | 200,000 | 40 M/s | 2 ms | 0.2 ms |
| 10,000 | 2,000,000 | 400 M/s | 20 ms | 2 ms |
| 100,000 | 20,000,000 | 4 B/s | 200 ms | 20 ms |

Those rates are sensitivity assumptions, not measured RTX/Sionna throughput.
Depth one cuts this query estimate by three relative to the depth-three model;
it does not establish a threefold wall-time speedup. It makes GPU feasibility
more promising, but the full 5 ms pulse budget is still unverified.

Declared candidate payload falls from approximately 116 to 60 bytes/candidate.
For 100 TX with a cap of 1,000/TX this is about **6 MB**, rather than 11.6 MB;
with native default capacity it is approximately 6 GB, rather than 11.6 GB.
Logical sample history is approximately 28 bytes/ray, rather than 84 bytes/ray.
These are source-derived capacities, not measured VRAM peaks.

The native minimum hash-counter allocation remains **800 MB for 100 TX**.
Depth one does not remove it. At 200 pulse epochs/s, clearing that payload
corresponds to 160 GB/s of writes/GPU. Smaller TX batches reduce peak allocation
but can increase launch/runtime cost; benchmark before selecting them.

With 1,000 total retained paths/RX, compact complex64 gain + float32 delay +
float32 Doppler is approximately **16 KB/pulse**, or **3.2 MB/s/RX at 200 Hz**,
before metadata. The former 160 GB/s time-expanded coefficient transfer at
20 MS/s is no longer required by the compact model. Final I/Q output rates and
external raw-transmitter ingress requirements in NETWORK_RUNTIME remain unchanged.

An 8–16 GiB RTX card is a reasonable measurement candidate for a bounded scene
with explicit caps, subject to actual peak VRAM. A 16–24 GiB card provides
development headroom; a high-end 24–32 GiB RTX remains a throughput candidate.
The single-interaction assumption does not establish a need for 48 GiB in this
small scene. No purchase minimum or 120 Hz/200-pulse/s GPU deadline has been
validated; test an available card before provisioning ten receivers.

### Reproduce the accepted baseline

After bootstrap, from the repository root:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python benchmarks/benchmark_network_paths.py --backend cpu --tx 100 --rx 1 --depth 1 --rays 10000 --path-cap 1000 --pulse-hz 200 --iterations 20 --warmup 5 --output depth1_cpu.json
.venv/bin/python benchmarks/benchmark_signal_sum.py --compact --paths 1000 --samples 4096 --sample-rate 20000000 --iterations 10 --output compact_signal_cpu.json
CUDA_VISIBLE_DEVICES=0 .venv/bin/python benchmarks/benchmark_network_paths.py --backend cuda --tx 100 --rx 1 --depth 1 --rays 10000 --path-cap 1000 --pulse-hz 200 --iterations 200 --warmup 20 --output depth1_gpu.json
```

`--pulse-hz` defaults to 200; `--update-hz` remains an alias. Set the actual
planned pulse rate explicitly. The benchmark defaults to depth one, with no
refraction, and records these interaction flags. For historical depth-three
conditions add `--depth 3 --refraction --pulse-hz 120`. Actual geometry, pulse
schedule and GPU measurements are the next feasibility gate.

<a id="optimization"></a>

## Exhaustive single-bounce optimization



**Runtime context (2026-10-05):** Historical tiny-scene LoS/specular optimization with 144 surviving paths. Channel timing excludes I/Q generation and distributed diffuse clutter. See [current runtime and wall-clock costs](runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

**Scope correction:** the 144-path benchmark below measures retained LoS and
specular paths in a tiny scene. It has no distributed diffuse ground return and
does not establish clutter coverage. Both antenna patterns weight its fields;
it does not importance-sample either pattern. The new
[TX/RX-aware ground-scattering mode](../terrain.md#ground-scattering) covers distributed
first-order scattering with an explicit per-link sampling budget and separate
timings. These specular timings must not be used as its runtime estimate.

This branch implements **one-way TX → RX** propagation for ESM, comms and other
RF skills. It does not infer a return channel from reciprocity, square a channel,
or assume a monostatic radar. The radar worker remains its existing point-target
implementation; a general network worker and multi-emitter I/Q mixing remain
separate work.

### What changed

`SingleBouncePathSolver` replaces Sionna's sampled candidate discovery with
exhaustive first-order planar image candidates. For every TX/RX pair it considers
one direct path and one reflection per distinct plane in the triangle mesh.
Coplanar triangles share one candidate, including disconnected patches: the
visibility trace determines whether the reflection actually lands on a surface.

Plane grouping uses exact integer plane equations derived from the mesh's binary
floating-point vertices. Nearby parallel surfaces are kept separate. Sionna's
own finite-surface/occlusion checks determine accepted paths, with its existing
numerical tolerances. The adapter then uses Sionna's original field calculator
and `Paths` implementation for dielectric/conductive material response,
polarization, antenna patterns, delay, carrier phase and narrowband Doppler.
The material on the surface actually hit supplies the response, including when
another coplanar patch supplied the candidate. This is exhaustive discovery
within the depth-one **specular mesh model**, rather than all physical scattering.

Static plane discovery is cached. Vertex/face buffer or shape changes rebuild
it; radio movement and antenna rotation are read every solve. Direct-path slots
stay allocated even when blocked, and their visibility mask is applied before
field calculation. This keeps candidate array sizes stable as LoS changes.

The native deterministic generator's large hash tables and sampled-ray replay
are removed from this backend. No path-power threshold, sidelobe cut, or reduced
material model was introduced. The adapter rejects unsupported diffuse
scattering, refraction, diffraction, deeper paths and non-mesh shapes. The
native backend remains available. It is pinned to Sionna RT 2.2.0 because it uses
private candidate buffers and image-method interfaces.

Use the optimized SISO receiver explicitly:

```python
receiver = RFReceiver(scene, config, path_solver="single-bounce")
block = receiver.capture(waveform, sim_time_ns)
```

For multiple independent radios, `SingleBouncePathSolver()(scene)` returns
normal Sionna `Paths`; it does not generate or mix their waveforms itself.
The scene's TX/RX arrays supply the antenna patterns, as in native Sionna.
The AirSim receiver example also accepts `--path-solver single-bounce`.

### Measurements

Paired measurements alternate solver order at identical moving radio poses,
with 30 timed epochs and five warmup epochs. Both use two Dr.Jit CPU threads,
a two-core quota, 8 GiB memory, 24.125 GHz, the same 74-triangle street scene,
LoS plus one specular reflection, and one CIR epoch per pulse. The optimized
mesh has 20 distinct planes. Native discovery uses 10,000 rays/TX and a cap of
1,000/TX; the optimized backend enumerates candidates without random rays.

| Workload | Native median / p95 | Optimized median / p95 | Median speedup | Paths |
| --- | ---: | ---: | ---: | ---: |
| 100 TX, 1 RX | 149.8 / 192.5 ms | 17.3 / 23.1 ms | 8.6× | 144 |
| 100 TX, 10 RX in one solve | 247.5 / 269.3 ms | 17.9 / 22.1 ms | 13.8× | 1,440 |

These include pose updates, synchronized propagation and NumPy CIR/Doppler
export. They exclude I/Q synthesis, filtering/ADC, AirSim, transport and moving
mesh/BVH updates. Every timed sample still missed both 5 ms and 8.33 ms budgets.
The optimized one-receiver isolated run measured 16.6 ms median, 18.1 ms p95
and **181 MiB peak host RSS**. Earlier native-only measurements used about
994 MiB; these separate runs are indicative, not paired memory measurements.
Paired-process RSS includes both backends and cannot measure optimized-only
memory. No GPU or VRAM measurement was possible here.

The 33,000 link comparisons across these two paired runs found equal path
counts. Maximum differences were:

- Absolute delay: 1.42e-14 s.
- Relative gain magnitude: 1.11e-4, about 0.011%.
- Carrier phase: 0.00196 rad, about 0.112 degrees.
- Narrowband Doppler: 0.000981 Hz.

The native sampled solver can miss reflections in other scenes; matching this
scene does not prove native ray convergence elsewhere. The new physical tests
also compare rotated directional/isotropic antennas on independent 2-TX/2-RX
links, wall/floor image distances, moving-wall cache invalidation, changing LoS
occlusion and complex receiver voltage. **42 tests pass.**

Cold runs are recorded separately. First-use compilation can cost hundreds of
milliseconds, and the recorded cold timings depend on the persistent JIT cache.
These short runs do not certify production tail latency. An earlier variable-LoS
prototype had large spikes; stable candidate slots and the final two-thread
configuration produced the reported measurements. Final path-count changes,
new scene geometry and new antenna/material code can still cause compilation.

### Environment and antenna choices

Use an RF mesh distinct from the visual/render mesh. Retain terrain and walls,
large metallic structures, important shadowing obstacles, material boundaries,
and surfaces needed for the intended clutter model. Reduce decorative
geometry and merge coplanar patches. This reduces both distinct-plane candidates
and BVH complexity. A land-use/land-cover layer can supply terrain/material
classes, but is not itself enough geometry for urban specular multipath. This
branch does not add land-cover classification or change Sionna's material data.

Candidate work scales as `TX * RX * (planes + 1)`, and depth-one visibility
requires at most approximately `TX * RX * (2*planes + 1)` ray queries. Here that
is 2,100 candidates / 4,100 queries for one RX, or 21,000 / 41,000 for ten RX.
This removes the million primary rays and large duplicate tables of the native
100-TX/10,000-ray case. Python, JIT launch and field-calculation overhead still
set a substantial timing floor in this small scene.

The adapter limits candidates to two million and requires a per-source path cap
large enough for the whole candidate set. It raises an error instead of silently
truncating paths. Highly faceted terrain or curved detailed objects can make
plane enumeration expensive; simplify the RF mesh or use the native solver.
Exact plane extraction also has an upfront CPU cost on large meshes and repeats
when their geometry changes. Moving-platform poses alone do not trigger it.

In the specular-only backend, directional patterns weight fields without pruning candidates. Future
antenna-sector pruning should use explicit sidelobe or received-power bounds,
including reflected departure/arrival directions. Beamwidth alone is an unsafe
cut for ESM because a weak sidelobe may be the signal of interest. Omnidirectional
receivers can still benefit from a transmitter coverage restriction if that
restriction is part of the modeled antenna. Such pruning needs an explicit
accuracy budget; this implementation keeps the complete pattern.

Next targets are GPU measurement, RF-mesh simplification on the intended scene,
and GPU waveform synthesis. The generic CPU synthesis benchmark remains about
88 ms for 1,000 paths × 4,096 samples; its cost was not optimized in this change.
Independent receiver workers map naturally to one GPU each, but this CPU result
cannot establish a GPU purchase minimum or certify ten-worker real-time operation.

### Reproduce

```bash
git checkout optimization/single-bounce-runtime
.venv/bin/python -m pytest -q
.venv/bin/python benchmarks/benchmark_single_bounce.py --threads 2 --tx 100 --rx 1 --iterations 30 --warmup 5 --output paired_1rx.json
.venv/bin/python benchmarks/benchmark_single_bounce.py --threads 2 --tx 100 --rx 10 --iterations 30 --warmup 5 --output paired_10rx.json
.venv/bin/python benchmarks/benchmark_network_paths.py --solver single-bounce --threads 2 --tx 100 --rx 1 --iterations 30 --warmup 5 --output isolated.json
CUDA_VISIBLE_DEVICES=0 .venv/bin/python benchmarks/benchmark_single_bounce.py --backend cuda --tx 100 --rx 1 --iterations 200 --warmup 20 --output paired_gpu.json
```

CUDA runs refuse CPU fallback. Set thread count to the actual CPU allocation;
`--threads 0` keeps Dr.Jit's default. All three CPU result files are committed in
`benchmarks/results/single_bounce_cpu_*.json`. Container CI also runs on
optimization branches and publishes their tested image with `sha-<full-commit>`;
it reserves `latest` for the default branch.

<a id="network-runtime"></a>

## Runtime assessment: 100 transmitters, 10 receivers



**Runtime context (2026-10-05):** Historical depth-three propagation sizing and conditional GPU query arithmetic; not a current continuous-I/Q service benchmark. See [current runtime and wall-clock costs](runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

**Updated baseline:** [PER_PULSE_RUNTIME.md](planning.md#per-pulse-runtime) applies the
accepted one-solve-per-pulse, depth-one model, compact coefficients and new
measurements. This document preserves the original depth-three assessment.

Assessed 2026-10-03 against application commit
`557bf23ab87b3a552d1f79378cc26aebc4beabe4`, Sionna RT 2.2.0 at
`15b5ee036917a4c2a9b6420e05570b77717e2fcc`, Mitsuba 3.9.1 and Dr.Jit 1.5.0.
The accompanying benchmark scripts/results were added during this assessment.

At the originally audited commit, all 28 Python tests passed. The prototype
is ready for performance investigation. It is not yet a general
AMS-GRA RF simulation plane. The deployed worker is one monostatic FMCW radar
with direct-path point-target echoes; Sionna can model independent radio links,
but the application needs a general channel-to-I/Q backend.

No GPU or live AirSim server is available here. CPU numbers below are measured.
GPU timing tables are conditional arithmetic, not measured GPU performance.

### Assumptions and scope

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

### Code audit

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

### New measurements

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

### Tracing work and conditional GPU time

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

### Memory findings from source

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

### Signal generation and host transfers

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

### Transport and world simulation

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

### Hardware to evaluate

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

### Engineering and acceptance gates

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

### Reproduction

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

<a id="gpu-runtime"></a>

## Runtime metrics for one GPU per receiver



**Runtime context (2026-10-05):** Historical channel-only CPU measurements and hypothetical GPU query rates. Sub-millisecond ray arithmetic is not complete GPU renderer latency. See [current runtime and wall-clock costs](runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

See [the code-derived scaling model](planning.md#sdr-complexity) for stage-by-stage
complexity, CPU prediction checks and explicit GPU implementation estimates.

The CPU benchmark is a correctness and host-cost baseline. It is not a measured
GPU runtime, and CPU deadline misses do not establish GPU deadline misses.
The deployment target is **10 receiver workers, each with one GPU and all 100
transmitters**. A 100-TX/10-RX CPU solve divided by ten does not measure that
deployment. AirSim physics at 120 Hz has an 8.33 ms tick budget; the current
200 Hz pulse cadence has a separate, tighter 5 ms channel budget.

For the newer Pluto-class pipeline including completed I/Q, use [SDR runtime](planning.md#sdr-runtime). The propagation-only figures below exclude its CPU waveform and receiver chain.

### Per-GPU work

For the current single-element, one-bounce ground fixture with N = 1,028 diffuse
attempts per link, T = 100 transmitters and M = 1 specular plane:

```
diffuse attempts = T*N                              = 102,800 / pulse / GPU
visibility queries <= 2*T*N + T*(1+2*M)             = 205,900 / pulse / GPU
candidate paths <= T*(N+1+M)                       = 103,000 / pulse / GPU
compact channel capacity = paths*(8+4+4) bytes      = 1.648 MB / pulse / GPU
```

Each diffuse sample needs a first-hit ray and at most one opposite-leg shadow
ray. LoS adds one query per link; a specular plane adds at most two. Misses and
occlusion reduce active queries. This is a work-count upper bound, not a scene
complexity bound: a detailed land-cover scene's BVH traversal and material/field
cost can differ substantially from a two-triangle ground plane.

At 200 pulses/s, each GPU needs at least **41.18 million queries/s for the ray
stage alone**, if it spends the entire 5 ms on tracing. At 120 solves/s that
becomes 24.71 million queries/s. Field evaluation, proposals and other work
need their own share of those budgets. Ten receivers multiply fleet work by ten,
without dividing each receiver's latency by ten.

Exporting the maximum compact channel every pulse is 329.6 MB/s per worker at
200 Hz, or 3.296 GB/s across ten workers. Actual retained coefficients are fewer;
padded CIR arrays and temporaries can add bytes. These figures cover complex64
gain, float32 delay and float32 Doppler only. They exclude IQ, geometry, BVH,
intermediate field buffers and allocator reservations, so they do not specify
minimum VRAM. Peak host RSS also does not estimate VRAM.

### Measured host cost and conditional GPU cost

The new CPU run used two Dr.Jit threads, a two-core quota and the previously
populated JIT cache. Ten timed moving-platform epochs followed three warmups:

| Region | Median | p95 | Interpretation on a CUDA worker |
| --- | ---: | ---: | --- |
| Total channel + poses + NumPy export | 48.6 ms | 49.2 ms | CPU measurement only |
| NumPy proposal sampling | 15.3 ms | 16.0 ms | Host code remains on CPU |
| Antenna proposal table preparation | 2.03 ms | 2.10 ms | Mixed backend evaluation and host export; changes on CUDA |

The sampling timer covers seed setup, allocation, weighted cell selection,
angular jitter, trigonometry and filling the proposal buffer. It stops before
uploading that buffer to Mitsuba. It adds no stage-wide GPU synchronization.
The full solve timer already synchronizes completion. Other solve work remains
mixed host/device, so subtracting these regions does not produce a pure GPU
kernel time. Per-epoch timings and assumptions are in
[the JSON report](../../benchmarks/results/scattering_cpu_100tx_1rx_gpu_planning.json).

The following rates are **hypothetical effective scene-query throughput**,
not measured GPU performance or vendor RT-core ratings:

| Assumed effective queries/s | Ray stage at query-count upper bound | Ray stage + unchanged measured host sampling |
| ---: | ---: | ---: |
| 100 million | 2.059 ms | 17.38 ms |
| 250 million | 0.824 ms | 16.14 ms |
| 1 billion | 0.206 ms | 15.52 ms |

The last column is a subtotal under those assumptions, not an end-to-end
prediction. It excludes proposal table preparation, field evaluation,
compaction, launches/synchronization, upload/export, poses, IQ, AirSim and
transport. A different deployment CPU changes the sampling cost. A faster GPU
does not accelerate the current NumPy draws. Moving proposal sampling onto the
device, and caching proposal tables while antenna patterns stay unchanged,
are immediate optimization priorities. Sample count and TX/RX coverage must
remain unchanged while doing that work.

The planning model is:

```
worker latency = host preparation + proposals + scene queries + RF fields
               + compaction + device/host transfers + IQ synthesis + transport
```

Only the channel portion was benchmarked in this historical study. GPU-resident
proposals and a complete scene-to-ADC pipeline remain work; the separate
basis I/Q renderer now has qualified P100 measurements. A 120 Hz physics tick can advance poses while RF
workers schedule pulse epochs separately; this does not remove the required RF
throughput or establish acceptable latency. Neither a specific GPU model nor a
minimum VRAM capacity is validated yet. CUDA capability and compatibility with
the pinned Sionna/Mitsuba/Dr.Jit stack are prerequisites, not a throughput guarantee.

### Measure the actual target

The [DEM terrain scenario](../terrain.md#terrain-scenario) has 800 specular planes. Its
per-worker query-count upper bound is 365,700 per pulse rather than the flat
fixture's 205,900. Use `--scene terrain` to measure that geometry;
`benchmark_scattering.py` now derives its budgets from the actual plane count.

On a CUDA-capable host, record the GPU name, driver and VRAM, then run a **one
receiver** benchmark on each assigned device. This command refuses CPU fallback:

```bash
nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv
CUDA_VISIBLE_DEVICES=0 .venv/bin/python benchmarks/benchmark_scattering.py \
  --backend cuda --tx 100 --rx 1 --samples-per-link 1028 \
  --deployment-receivers 10 --pulse-hz 200 --warmup 20 --iterations 200 \
  --output ground_gpu_0.json
```

Preserve both cold and cached measurements. Changing retained-path counts can
trigger compilation on either backend; warmups do not guarantee all future
shapes are compiled. Then exercise all ten workers concurrently with their
actual host CPU allocation, terrain, motions and waveform duty cycle. Measure
end-to-end IQ deadlines, queue growth, transport load and peak device memory.
The existing published test image is a CPU image; its successful tests do not
validate CUDA deployment or GPU memory sizing.

`benchmark_scattering.py` now emits `stage_timings` and `gpu_deployment` on both
backends. CPU reports mark GPU channel runtime and deadlines unmeasured. A
multi-receiver batch leaves the per-worker host sampling estimate unset rather
than inventing it by dividing a batched timing.

<a id="sdr-runtime"></a>

## SDR runtime: update rate and latency



**Runtime context (2026-10-05):** Historical scene-to-ADC tone captures contain only 4,096 output samples (2.048 ms at 2 MS/s), with scene-dependent surviving paths. Later arbitrary-I/Q GPU rendering is measured separately. See [current runtime and wall-clock costs](runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

See [the code-derived scaling model](planning.md#sdr-complexity) for stage-by-stage
complexity, CPU prediction checks and explicit GPU implementation estimates.

Measured 2026-10-03 against the Pluto-class receiver introduced in commit
279787aa181172fe5d95c14aaa5f61c729e9f701. These measurements include finished ADC
I/Q. Earlier propagation-only reports do not measure this complete pipeline.
**The present CPU implementation is suitable for offline simulation. Selecting
CUDA alone cannot make its CPU I/Q synthesis run at 120 or 200 Hz.** This older scene-to-ADC pipeline has not been fully ported to GPU.
The separate basis renderer now has qualified P100 measurements; see
[RUNTIME_STATUS.md](runtime.md#runtime-status).

### What the two numbers mean

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

For 2 TX, positions/powers/clock errors match [the COTS lab](../architecture.md#cots-sdr-lab);
one-worker timing uses listener A. For 100 TX, transmitters occupy x=0,
y=−25…25 m, z=10 m and move at 1 m/s along x. They use −30 dBm each,
tones spanning ±250 kHz, reference errors spanning ±20 ppm and distinct phases.
Listener A starts at [−30, −10, 14] m and moves at 3 m/s along x.
This is a measured expanded SDR workload, not the earlier 24.125 GHz radar
fixture or a tested AMS-GRA distributed run. The second receiver is omitted
in the per-worker tests, not obtained by dividing a batched result.

### Measured CPU results

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

### GPU: current code versus a future implementation

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

### Reproduce and inspect

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

* [2 TX / 1 RX](../../benchmarks/results/sdr_cpu_2tx_1rx.json)
* [2 TX / 2 RX](../../benchmarks/results/sdr_cpu_2tx_2rx.json)
* [100 TX / 1 RX](../../benchmarks/results/sdr_cpu_100tx_1rx.json)

Timing boundaries are in [the benchmark](../../benchmarks/benchmark_sdr_runtime.py).
The channel export and CPU receive chain are in [sdr.py](../../src/airsim_rf/sdr.py);
the per-path waveform loop is in [receiver.py](../../src/airsim_rf/receiver.py).
See [GPU planning](planning.md#gpu-runtime) for earlier channel-only work estimates;
those figures exclude this SDR synthesis and receive chain.

<a id="sdr-complexity"></a>

## Code-derived CPU and GPU runtime model



**Runtime context (2026-10-05):** Historical code model and conditional GPU estimates for the older tone/short-capture pipeline. Do not use these forecasts as current GPU measurements. See [current runtime and wall-clock costs](runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

This analysis uses the current Pluto-class SDR path, the code in main as of
4e29528, and [the recorded CPU benchmarks](planning.md#sdr-runtime). The benchmark
waveforms are continuous tones. LFM recurrence is a proposed extension, not a
measured LFM GPU result. All GPU estimates below are **untested planning
estimates**, with their assumed throughput stated explicitly.

### Work counts and complexity

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

### Compare the CPU model with measurements

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

### GPU work, parallel execution and latency

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

#### Why the implementation changes the estimate

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

### Explicit GPU engineering estimate

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

### Reproduce the arithmetic

```
.venv/bin/python benchmarks/analyze_sdr_scaling.py
```

This reads the three CPU reports and writes
[the machine-readable model](../../benchmarks/results/sdr_scaling_analysis.json),
including held-out CPU predictions and each GPU scenario's assumptions.
It does not execute a GPU benchmark or modify the RF implementation.

Code references: [CPU path loop](../../src/airsim_rf/receiver.py),
[SDR receive chain](../../src/airsim_rf/sdr.py),
[antenna proposals and diffuse visibility](../../src/airsim_rf/scattering.py),
[specular candidates and geometry cache](../../src/airsim_rf/single_bounce.py).
Pinned Sionna 2.2.0 references:
[solver orchestration](https://github.com/NVlabs/sionna-rt/blob/v2.2.0/src/sionna/rt/path_solvers/path_solver.py),
[field calculation](https://github.com/NVlabs/sionna-rt/blob/v2.2.0/src/sionna/rt/path_solvers/field_calculator.py),
[path packing](https://github.com/NVlabs/sionna-rt/blob/v2.2.0/src/sionna/rt/path_solvers/paths.py).

[1] NVIDIA, [GeForce RTX 4090 specifications](https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4090/), accessed 2026-10-03.

[2] NVIDIA, [CUDA C++ Programming Guide 12.6.3: native arithmetic instruction throughput](https://docs.nvidia.com/cuda/archive/12.6.3/cuda-c-programming-guide/index.html#arithmetic-instructions-throughput-native-arithmetic-instructions), and the same guide's [sine/cosine and intrinsic-function discussion](https://docs.nvidia.com/cuda/archive/12.6.3/cuda-c-programming-guide/index.html#arithmetic-instructions), accessed 2026-10-03. Hardware maxima constrain the estimate; they are not measured application throughput.

<a id="affordable-realtime-rf"></a>

## A practical route to continuous 120 Hz RF simulation



**Runtime context (2026-10-05):** Architecture research and conditional sizing, not a demonstrated $5,000 real-time deployment. Later P100 measurements supersede statements about unmeasured GPU rendering, not the study’s historical data. See [current runtime and wall-clock costs](runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

Research date: 2026-10-04. Target supplied by the user: approximately **$5,000
for total compute**, 100 transmitters, 10 receivers, continuous ESM/comms I/Q,
moving platforms, and first-order environmental multipath. The initial sample
rate is **2 MS/s per radio**, with the existing approximately 1 MHz receive
bandwidth. No GPU result or complete 120 Hz demonstration is claimed here.

### Required scope: do not optimize by simplifying the scenario

The user explicitly requires that optimization not rely on the current scene's
short delay spread, low Doppler, favorable visibility, waveform family or small
number of effective channel coefficients. The terrain measurements below are
case-specific accuracy evidence; they are not the production sizing basis.
The previous recommendation to make a compact channel the primary renderer,
using those properties to justify the budget, is withdrawn.

The baseline is a **general sampled-waveform direct path renderer**. Preserve
all supplied valid paths, their fractional delays, individual Doppler evolution,
coherent sums and continuous samples at the configured rate. Keep the requested
scene/channel update cadence. Optimize execution: fuse interpolation, phase
updates and summation; avoid path-by-sample intermediate writes; batch
independent jobs and transfers; keep mandatory processing on-device where
beneficial. Scheduling across one, two or more GPUs is a measured deployment
choice, not an assumed capacity improvement.

The 100 transmitters are independent. **Do not credit transmitter-buffer or
transform sharing as an optimization.** Benchmark separate data and storage
for each transmitter job, with private copies in separate receiver workers.
Physical coherent summation at a receiver still combines independent signals.
See [the independent-transmitter experiments and next steps](../rendering.md#independent-tx-optimization).

A first [batched sampled-I/Q implementation](../rendering.md#batched-rendering) now exists,
with private inputs and retained path Dopplers. Its finite interpolation kernel
and CPU measurements are documented separately; the full target workload and
ideal-reconstruction accuracy remain to be qualified.

A new [bounded-error Doppler-basis FFT experiment](../rendering.md#doppler-basis-fft) tests
the alternative representation on synthetic channels with 1,028 valid paths,
100-microsecond delay bounds and +/-2,500 Hz Doppler bounds. It measures about
22 times faster CPU rendering, with separate wider-range cases, independent
private input transforms and explicit equal-clock scope. This is evidence for
an architectural candidate, not qualification of the target RF plane.

Other representations remain research candidates only if they handle the same
declared workload and numerical accuracy, report their unfavorable cases, and
do not obtain their speedup by pruning paths, averaging Dopplers, narrowing the
waveform bandwidth or quietly reducing scene updates. Caching static mesh
acceleration is useful; skipping required visibility checks on moving geometry
is not an equivalent optimization.

Qualify rendering independently of the scene's surviving-ray count: include
at least 1,028 valid paths per directed link for all 100x10 links, parameterized
larger counts, fractional delays over the declared delay range, independent
Dopplers over the declared Doppler range and arbitrary sampled inputs. The
initial 1,028-path stress amounts to 1.028 million paths and 2.056 trillion
path/sample contributions per second at continuous 2 MS/s. It is a renderer
stress workload, not a claim that the present geometry produces that many rays.
Delay range and Doppler range must be explicit qualification parameters; there
is no performance guarantee for unbounded channels or arbitrary hardware.

Whether a $5,000 machine can meet the complete 120 Hz target for that workload
is **unresolved**. A hardware allocation is a budget ceiling, not evidence of
capacity. If equal-fidelity optimization is insufficient, report the measured
hardware requirement or achieved rate rather than making the scene easier.

### Correct the workload before choosing hardware

The previous benchmark emits 4,096 samples at selected epochs. Continuous
2 MS/s reception requires approximately 16,667 samples per 120 Hz scene tick,
with the exact fractional sample count carried between ticks. That is about
four times the samples of the previous capture, with no gaps. Physics/scene
updates, waveform sample rate, pulse repetition frequency, and wall-clock
processing latency are distinct clocks.

The measured 100-TX/1-RX direct LLVM capture took about 394 ms for 4,096 output
samples; rendering accounted for about 310 ms. The remaining CPU work already
exceeds the 8.33 ms update budget. Multiplying by ten receivers or asking for
continuous samples is not a measured GPU projection.

At approximately 42,500 rays per receiver, direct rendering of continuous
2 MS/s output evaluates about 85 billion ray/sample contributions per second
per receiver, or 850 billion across ten receivers. The current FP64 temporary
buffers write and read about 32 bytes per contribution: approximately **27 TB/s
of contribution-buffer traffic** for the whole deployment, before buffer
initialization and other data movement. This is an accounting limit for the
current implementation, not a universal limit for direct rendering: fused
on-chip accumulation can avoid those buffers. It does establish why switching
the current kernel to an inexpensive GPU is insufficient.

### Case-specific channel measurements: not a sizing basis

[The channel-support inspection](../../research_results/affordable_realtime/channel_support.json)
uses the first epoch of the existing 100-TX, one-receiver DEM scenario:

| Property | Measured value |
|---|---:|
| Carrier / sample rate | 915 MHz / 2 MS/s |
| Attempted diffuse samples per link | 1,028 |
| Total retained rays | 42,503 |
| Rays per link | 376–454 |
| Absolute path delays | 0.101–1.017 microseconds |
| Maximum delay spread within a link | 0.914 microseconds |
| Maximum physical Doppler magnitude | 12.16 Hz |
| Maximum link delay spread in sample units | 1.83 samples |

Hundreds of physical rays occupy a very short delay interval and evolve
slowly relative to the waveform sample rate. Distinct carrier phases and
Dopplers still matter; physical ray count is not the necessary number of
sampled filter coefficients. This observation is specific to this compact,
slow-moving, 915 MHz scene. Larger scenes, fast objects and higher carrier
frequencies can need substantially more delay support and temporal basis terms.
The other nine receiver locations were not measured by this inspection.

The source inspection and experiments were performed on the CPU implementation
based on commit `e6a18dd4a4b220b464cd1b2b96e8d78a91fd9b43`. They do not alter
the production renderer or provide a complete simulation-plane timing result.

### Alternative representation study: accuracy evidence, not the selected baseline

For sampled, bandlimited transmitter data, define the time-varying channel:

```text
h_rt[k,n] = sum_paths a_p * q(k - fs*delay_p)
                        * exp(j*2*pi*doppler_p*(t_n - channel_epoch))
y_r[n]   = sum_transmitters sum_k h_rt[k,n] * x_t[n-k]
```

`q` is the fractional-delay interpolation kernel. With ideal infinite sinc
interpolation, this is the sampled form of direct path rendering under our
accepted narrowband model. A finite practical kernel introduces a measurable
approximation. All ray coefficients, delays and Dopplers enter the sum. Two
paths at the same delay with different Dopplers produce an evolving coefficient,
including their interference and beating. They are not replaced with a fixed
coefficient or a single averaged Doppler.

The production algorithm can represent each `h[k,n]` by a small set of temporal
basis coefficients, or by densely enough spaced knots and validated
interpolation. Reconstruct the coefficient at output sample times. Its temporal
bandwidth comes from physical path Doppler and geometry evolution, rather than
the 2 MHz waveform sample rate. Stationarity boundaries, path appearance and
occlusion transitions require their own update handling.

Radio LO offsets must be factored separately: apply a transmitter's oscillator
and resampling to that job's private waveform, include its delay-dependent LO phase in
path gains, and apply each receiver's oscillator/resampling once after coherent
summation. Otherwise a 20 kHz oscillator offset unnecessarily inflates the
basis needed for a physical channel whose Dopplers are only tens of hertz.

Delay support and temporal rank are selected against an error tolerance and
reported. They are not fixed at 18 or 32 regardless of scenario. Near-cancellation
and weak-signal tests must include absolute error against the receiver noise
floor, not only relative error when reference power approaches zero. Band-edge
signals, delay boundaries, moving obstruction and cross-block phase must be
validated. Fractional-delay interpolation can require a small lookahead;
production buffering and delivery latency must account for it.

#### Arbitrary-waveform numerical check performed here

[The exploratory validation](../../research_results/affordable_realtime/ltv_validation.json)
uses one actual link with 399 rays. The input is a randomly generated complex
sample block bandlimited to +/-480 kHz, lasting 8.3335 ms at 2 MS/s. A periodic
DFT representation permits an ideal fractional-delay reference for every ray.
The reference includes each ray's independent Doppler at every sample.

A windowed-sinc channel using 18 filter coefficients and cubic temporal
interpolation produced **-92.45 dB normalized mean-square error**, or about
**0.00239% RMS error**, for a 0.5 ms knot spacing. Increasing interpolation
support gave -94.52 dB for 34 coefficients and -99.28 dB for 66 coefficients.
These are waveform accuracy measurements, not general fidelity guarantees.

A [synthetic Doppler stress](../../research_results/affordable_realtime/ltv_stress.json)
multiplies these same rays' Dopplers by 40, reaching 485 Hz. With 18 coefficients,
0.125 ms temporal knots retained approximately -92.44 dB NMSE; 0.5 ms knots
fell to -56.39 dB. This demonstrates why temporal resolution must adapt to
Doppler, rather than assuming one fixed update interval is sufficient.

The experiment uses FP64 NumPy, one link and a periodic waveform. It materializes
sample-expanded coefficients for convenient validation and is not a proposed
production memory layout. Its individual timings include initialization effects;
it is not a 1,000-link throughput benchmark. Production needs fused coefficient
reconstruction, overlap/history, stateful clocks and receiver filters.

### Investigated solution families

| Approach | Arbitrary sampled waveforms and Doppler | Hardware / assessment |
|---|---|---|
| Direct per-path interpolation and summation | Yes, with a fractional-delay interpolator and individual phase evolution | CPU, CUDA, OpenCL/SYCL possible. Required general baseline and correctness reference; dense continuous streams need fused execution and full-workload qualification. Our existing direct backend supports analytic tone/LFM descriptors, not arbitrary sample streams yet. |
| Compact time-varying FIR with SIMD/GPU kernels | Yes; all rays contribute to coefficients that evolve at sample times | Conditional candidate; short-delay performance cannot establish general capacity. Interpolation and temporal approximation must be controlled. |
| Temporal basis expansion plus overlap-save FFT convolution | Yes; separately filter through each basis channel, then combine with its time-varying basis function | Candidate with explicit dependence on delay support and temporal rank. Account for private per-link input transforms and receiver summation. A static block FFT alone does not preserve intra-block Doppler. |
| Delay/Doppler spreading-grid or low-rank compression | Yes within validated delay/Doppler bounds | Potentially efficient; off-grid delays/Dopplers require interpolation or basis expansions. Simple nearest-bin quantization is not sufficient for coherent data. |
| Cached geometry and persistent scatterer support | Independent of waveform | Complements every renderer. Reuse static mesh acceleration, candidates and quadrature support; update gains, angles, delays, visibility and Doppler with motion. Cache invalidation and sampling weights matter. |
| Commodity FPGA channel emulation | Arbitrary input I/Q; small published designs have limited paths/links | Low latency for a few hardware links. Attractive later for hardware-in-the-loop; not the cheapest way to implement 1,000 rich virtual links. |
| Remote shared research facility | Existing large-scale RF emulation | Colosseum is worth evaluating for independent experiments. Access/allocation conditions need checking; it is not a local AirSim replacement or a confirmed free service. |
| Packet-only or RF power-only network simulation | Does not produce the required coherent arbitrary I/Q | Can help surrounding network studies but cannot replace the RF plane for this task. |
| Full-wave FDTD/FEM on the moving scene | Potentially very detailed electromagnetic solutions | Unlikely to fit this real-time workload and budget. Full-wave results can calibrate selected scattering/material cases offline. |

#### Concrete open implementations and publications

The [2026-10-05 channel-to-I/Q review](../references.md#iq-rendering-references) supplements
these references with the Sionna PHY sample operator, ACHEM/CHEM and HermesPy,
additional reduced-rank papers and a SimART comparison. It traces what the
code actually filters and distinguishes sample-evolving Doppler from
symbol-static taps or a common link frequency shift.

1. **Hofer et al., “Real-Time Geometry-Based Wireless Channel Emulation,” IEEE
   TVT 68(2), 2019, DOI 10.1109/TVT.2018.2888914.**
   [Author PDF](https://thomaszemen.org/papers/Hofer19-IEEETVT-paper.pdf),
   [Lund record](https://portal.research.lu.se/en/publications/real-time-geometry-based-wireless-channel-emulation/).
   Section III uses discrete prolate spheroidal basis functions to compress a
   time-varying geometry-derived channel. Section IV separates O(paths) channel
   setup from reconstruction whose cost depends on basis rank and delay support.
   It reports a 617-path vehicular validation, with normalized power-delay and
   Doppler-spectrum errors below approximately -35 dB. These are statistical
   measurement metrics, not a universal -35 dB I/Q error guarantee. The paper's
   example complexity reduction is 267x, and PC/SDR channel-data reduction is
   427x. Those factors belong to its parameters and hardware; they are not our
   predicted speedup. Public paper, not a verified drop-in open-source engine.
2. **Sionna Research Kit** — Apache 2.0.
   [Tutorial](https://nvlabs.github.io/sionna/rk/tutorials/channel_emulation/channel_emulation.html),
   [CUDA source](https://github.com/NVlabs/sionna-rk/blob/main/plugins/channel_emulation/cuda_emulator/src/chn_emu_cuda.cu).
   Real I/Q channel filtering with time-varying CIR updates. Current integration
   is SISO, integer delay indices and communications-specific normalization/
   clipping. Useful code precedent, not a 1,000-link calibrated-voltage solution.
3. **OCUDU GPU Channel** — MIT.
   [Repository](https://github.com/zhouyou-gu/ocudu-gpu-channel),
   [Sionna adapter](https://github.com/zhouyou-gu/ocudu-gpu-channel/blob/main/scripts/sionna_rt/channel_adapter.py).
   CUDA fractional-delay I/Q filtering and phase recurrence are relevant.
   Its Sionna adapter prunes to 32 taps and does not carry individual ray
   Dopplers through that conversion. The repository also documents failed
   strict real-time qualification cases. Reuse techniques, not its tap cap or
   a presumed latency guarantee.
4. **GNU Radio**, GPL, and **VOLK**, GPL.
   [Selective-fading source](https://github.com/gnuradio/gnuradio/blob/main/gr-channels/lib/selective_fading_model_impl.cc),
   [VOLK](https://github.com/gnuradio/volk).
   The inspected GNU Radio code adds fading paths to fractional-delay filter
   coefficients at each sample, then filters arbitrary I/Q. This confirms the
   model; its nested loops do not provide our large-scale optimization. VOLK
   supplies portable SIMD building blocks. **liquid-dsp**, MIT,
   [source](https://github.com/jgaeddert/liquid-dsp), is another CPU DSP source
   for resampling, fractional delay and oscillator/filter primitives.
5. **Adamek et al., “GPU Fast Convolution via the Overlap-and-Save Method in
   Shared Memory,” 2020.** [Paper](https://arxiv.org/abs/1910.01972),
   [MIT CUDA implementation](https://github.com/KAdamek/GPU_Overlap-and-save_convolution).
   Supplies FFT convolution techniques; time-varying Doppler basis handling is
   additional work, not provided by ordinary stationary convolution.
6. **AntSDR channel emulator** — GPL-2.0-or-later.
   [Source and limitations](https://github.com/simonwunderlich/antsdr-channel-emulator).
   Public FPGA design advertises/measures two directed channels at 30.72 MS/s,
   four paths per direction and per-sample Doppler oscillators. Its board cost
   is reported as about $690. Delay positions use whole samples; fractional
   delay is future work. A useful affordable hardware demonstration, but
   reducing this terrain scene to four paths would not meet our objective.
7. **OpenAirLink** — public GPL project.
   [Source](https://github.com/N3Martix/OpenAirLink),
   [2024 paper](https://arxiv.org/abs/2404.09660).
   RFNoC FIR on USRP, with a reported approximately 1.72 microsecond processing
   latency. The implementation studied has 42 dense delay taps and lacks
   Doppler/fading support and cross-channel mixing. Its low latency does not
   establish our required functionality or budget fit.
8. **Colosseum** — remote research infrastructure.
   [Official overview](https://colosseum.sites.northeastern.edu/),
   [architecture](https://colosseumwireless.readthedocs.io/en/latest/index.html),
   [PAWR access description](https://advancedwireless.org/colosseum/).
   Offers 256 radio endpoints and up to 256x256 configurable channels. Worth
   investigating as a shared validation resource. Custom scenarios, live motion
   coupling, experiment access and any fees need confirmation.

### Hardware portability and a $5,000 deployment

Arbitrary waveform support should mean complex sample buffers with explicit
sample rate, timestamps and history, independent of waveform family. Hardware
portability should mean compatible CPU and accelerator implementations of the
same operator. It cannot mean that every device sustains an unbounded sample
rate, number of links, delay spread and Doppler range.

For portable acceleration, investigate **ArrayFire**, BSD-3-Clause,
[unified CPU/CUDA/oneAPI/OpenCL API](https://arrayfire.org/docs/unifiedbackend.htm),
and **VkFFT**, MIT,
[Vulkan/CUDA/HIP/OpenCL/Level Zero/Metal FFT library](https://github.com/DTolm/VkFFT).
They provide primitives, not a ready RF renderer. A small C++ CPU implementation
plus GPU kernels may be preferable to materializing large intermediate tensors.
Keep the existing Dr.Jit renderer for reference/P100 testing. Do not add several
accelerator stacks before benchmarking the chosen algorithm.

Sionna propagation remains a separate compatibility constraint: the current
stack supports LLVM CPU and NVIDIA CUDA acceleration. Portable signal rendering
alone does not give Sionna an AMD/Intel/Apple GPU ray-tracing backend. Those
systems could use CPU propagation or a separately validated geometry backend.

A candidate local workstation allocation is below. These are spending limits,
not current retailer quotes or proof that this configuration meets 120 Hz:

| Item | Allocation |
|---|---:|
| One or two 16–24 GB NVIDIA GPUs, expansion staged after profiling | $2,400 |
| Modern CPU, roughly 12–16 cores | $500 |
| 64–128 GB host RAM | $500 |
| Motherboard, case and adequate PSU | $700 |
| NVMe storage | $250 |
| Cooling / networking / miscellaneous | $250 |
| Contingency | $400 |
| Total | $5,000 |

NVIDIA's published launch prices give useful scale: the RTX 5060 Ti 16 GB
launched at $429, and the RTX 5070 Ti 16 GB at $749. These are **2025 launch
prices**, not verified October 2026 availability or purchase prices:
[5060 announcement](https://nvidianews.nvidia.com/news/nvidia-blackwell-geforce-rtx-arrives-for-every-gamer-starting-at-299),
[5070 announcement](https://nvidianews.nvidia.com/news/nvidia-blackwell-geforce-rtx-50-series-opens-new-world-of-ai-computer-graphics).
A used 24 GB RTX 3090 is another candidate, but no current used-price quote was
verified here. Prefer profiling over selecting cards solely by peak TFLOPS.

P100 is useful because it is already available and has strong FP64 throughput.
It lacks RT cores, has an older software-support envelope and server cooling
requirements. Consumer RTX GPUs benefit from mixed precision: preserve careful
phase initialization while evaluating FP32 sample/filter arithmetic against
FP64 references. Do not assume FP16/TF32 or 12-bit ADC output makes weak-signal
errors harmless. Also do not assume our current FP64 kernel maps efficiently to
consumer hardware.

A dual-GPU host needs actual PCIe lane/slot support, adequate power and cooling.
Keep graphics rendering from consuming the RF worker's deadline margin. A
headless RF host or a separate display device is useful, but live AirSim with
110 moving radio platforms must still be measured; these tests do not include
its physics/rendering cost.

At 2 MS/s, complex64 transmitter data for 100 sources is **1.6 GB/s** and ten
receiver outputs are **160 MB/s** for one complex64 stream per receiver.
Under the independent-buffer benchmark, each of ten receiver workers pays for
its own 100 input streams: **16 GB/s aggregate input traffic**, without sharing
credit. A single 10 GbE link cannot carry even one worker's 1.6 GB/s payload.
Private local generation or suitably provisioned transport must be measured;
neither makes independent input generation or transfers free. Persistent
private device buffers can avoid allocation churn without aliasing input data.
Do not continuously archive every intermediate. Record selected outputs when
needed and include actual RF skill consumption in delivery-latency tests.

### A concrete implementation and qualification sequence

1. **Define a continuous sampled-waveform contract.** Timestamped complex
   buffers, channel epoch, sample-rate conversion and history. Preserve phase
   across ticks; retain previous input/filter state. Explicitly test gap-free
   production, including fractional sample counts at 120 Hz. The rendering
   backend must handle recorded data, modulation and pulses without waveform
   family-specific formulas.
2. **Implement fused general direct rendering.** Fractional-delay interpolation
   of arbitrary sampled inputs, individual Doppler phase evolution and coherent
   accumulation. Eliminate the current full path-tile/sample-window contribution
   buffers. Preserve the existing reference for comparison; validate across the
   declared path count, delay and Doppler ranges, not only this terrain case.
3. **Compare general algorithms at equal fidelity.** Evaluate direct rendering,
   time-varying FIR and temporal-basis FFT methods against the same stress suite.
   Report costs as delay support and Doppler complexity grow. Retain private
   input buffers/transforms and all required input/filter history for each job.
   Approximation error and any extra lookahead belong in the results.
4. **Remove CPU work from the critical path.** Batch proposals/visibility tests,
   reuse scene acceleration and candidates, keep paths/channel state on-device,
   and disable or decimate optional per-link diagnostic filters. Keep mandatory
   receiver noise, clocks, stateful filtering and ADC. Do not count deleted
   physical effects as an optimization.
5. **Measure consolidation and preserve distribution.** Compare logical
   receiver batching on one/two GPUs with the one-worker-per-GPU architecture.
   Select deployment from measured full-workload capacity. Separate scene
   scheduling from sample streaming without allowing growing queues.
6. **Qualify the actual affordable machine.** Test all 100x10 links, moving
   platforms, all attempted-ray budgets and continuous 2 MS/s input/output.
   A useful engineering target is RF service below 5 ms per 8.33 ms scene tick
   to leave margin; this is a target, not a prediction. Measure per-chunk
   delivery latency, p95/p99, deadline misses and dropped samples for sustained
   runs. Then add AirSim/AMS-GRA, consumers and transport to the same test.

The following small-filter arithmetic is a case-specific illustration only.
It must not be used to justify the general workload or the $5,000 target: 1,000 links with
18 sampled coefficients at 2 MS/s require 36 billion complex multiply-accumulates
per second, about 288 GFLOP/s at eight real operations per complex MAC, excluding
coefficient reconstruction, ray tracing, resampling and receiver effects.
That is a tractable arithmetic scale for commodity GPUs, but achievable speed
also depends on memory reuse and fusion.

For temporal-basis FFT rendering, an illustrative 512-point block with 18-tap
support produces 495 valid samples. Four basis terms, 100 TX and 10 RX require
about 8.3 billion complex MACs/s for the frequency-domain link products, roughly
66 GFLOP/s, before FFT/channel setup and other stages. With private input
transforms for all 1,000 directed links, forward FFTs add roughly 93 GFLOP/s
using the rough `5 * K * log2(K)` operation estimate; they are not shared.
RX inverse transforms are needed per receiver/basis after coherent summation.
Four basis
terms are an illustration, not a qualified rank for every scene. These are
operation counts, not measured latency estimates. They describe only that illustrative rank/support choice. Neither those
counts nor this scene's compactness establish the required general runtime.

### Reproduce the research experiments

No new package dependencies are required beyond the existing bootstrap:

```bash
.venv/bin/python benchmarks/analyze_channel_support.py
OPENBLAS_NUM_THREADS=2 .venv/bin/python benchmarks/validate_compact_channel.py
## Synthetic higher-Doppler stress, preserving the same delays/gains:
OPENBLAS_NUM_THREADS=2 .venv/bin/python benchmarks/validate_compact_channel.py \
  --doppler-scale 40 --knot-ms .125 .25 .5 --output-name ltv_stress.json
```

The first script writes measured channel JSON and a local NPZ containing paths;
the second writes accuracy JSON. The NPZ is ignored by git. The scripts are
research experiments, not a new production channel renderer, GPU profiling
suite or real-time acceptance test. Stored CPU timings are individual
experiment timings, with initialization effects, and must not be extrapolated
to a 1,000-link deployment.

<a id="p100-gpu-pipeline"></a>

## P100 CUDA propagation and rendering



The P100 can run the current Sionna RT 2.2.0 first-order terrain solver on
CUDA/OptiX with an explicit compatibility environment. The previous
end-to-end collections used LLVM CPU propagation; `basis-cuda` selected GPU
signal rendering only. These are different backend configurations.

```bash
bash scripts/run_p100_docker.sh --end-to-end --p100-gpu \
  --run-id p100-gpu-full
```

This selects CUDA propagation and rendering, builds the existing pinned
profiling environment plus `Dockerfile.p100-gpu`, and installs Mitsuba 3.8.0 /
Dr.Jit 1.3.1 from `requirements-p100-propagation.txt`. Sionna RT remains 2.2.0.
Production dependency pins remain unchanged. The older pair is an explicitly
tested compatibility configuration, not a claim of upstream support for every
Sionna feature. The launcher provides writable old-Dr.Jit cache storage without
changing the user's home directory or driver. It never silently falls back to
CPU tracing. GPU-propagation/GPU-rendering performance rows are collected; CPU worker protocol
fixtures run as correctness tests in a separate process.

The [final collection](../../results/profiling/p100-gpu-pipeline-opaque-full-20261007/FINDINGS.md)
measures 30 windows per fleet size, plus separate 30-window instrumented series.
For 100 TX / 10 RX, the unprofiled median **RF fleet-update wall service time** is
**553.685 ms**, p95 **563.363 ms**. One update produces 16,666 or 16,667 samples
at 2 MS/s (~8.333 ms signal) for each receiver, sequentially on one P100.
The earlier hybrid configuration measured **843.630 ms** per fleet update,
or **101.43 wall seconds per simulated signal second** (30 updates covering
0.250 signal seconds).
Backend, dependency stack and optimization settings changed; this comparison
does not isolate an optimization gain. GPU propagation
wall time is **31.223 ms** and GPU-renderer wall time **398.271 ms**. Every
instrumented target window records four OptiX-enabled events. This remains
**66.36 wall seconds per simulated signal second**, using summed measured
wall time and actual sample-duration accounting.

The implementation retains every physical path, 1,028 diffuse attempts per
link, independent source allocations/FFTs, FP64/complex128 rendering, declared
100 us delay / 2,500 Hz Doppler ranges, 1e-10 temporal tolerance, and continuous
receiver filtering/noise/ADC and actual consumer delivery. No path pruning or
sample-budget reduction is used. The compatibility counter uses GPU uint32
atomics instead of an unsupported Volta warp-match instruction. Optional Metal
backend checks are handled for the older API, and evaluated loops keep native
reference traversal/arithmetic on the GPU. Path storage capacity is padded,
not the physical path set.

Repeated local-direction draws are reused only when antenna probabilities,
seed and dimensions match exactly. Antenna tables and all geometry/visibility/
fields are recomputed. Moving GPU poses are made opaque so new values do not
trigger fresh compiler specialization; they are never cached or frozen.
Per-receiver pinned/device workspaces reuse storage. Fused coefficient
projection remains optional because its short-run improvement was marginal.
See [all experiments and qualifications](../../results/profiling/p100-gpu-system-20261007/README.md).

Source generation/preparation, receiver filtering/noise/ADC, bridge/control and
HTTP/file I/O remain host stages. GPU propagation/rendering is not a claim that
every operation is device-resident. Live AirSim physics/RPC, WAN/AMS-GRA workers
and unequal-clock resampling remain outside this qualification. Raw SC16 files
stay local; reports, JSON, logs and checksums are published.
The [matched block-size sweep](../../results/profiling/p100-gpu-block-sweep-20261008/README.md) measures 66.297–66.580 wall seconds per simulated signal second for the unchanged 2,048-sample default. Alternative block sizes measured 71.201–118.140 and were rejected. These are 30-update trials covering 0.250 simulated seconds each, not whole-flight execution times.

