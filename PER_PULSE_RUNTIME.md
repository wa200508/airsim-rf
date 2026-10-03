# Accepted model: one channel solve per pulse, one interaction

Updated 2026-10-03. This supersedes the depth-three planning baseline in
[NETWORK_RUNTIME.md](NETWORK_RUNTIME.md); its older results remain available
for comparison. Sionna/Mitsuba/Dr.Jit versions remain 2.2.0/3.9.1/1.5.0.

## Model and implementation

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

### Native Sionna candidate discovery

`max_depth=1` stops the interaction chain at its first surface. It does **not**
disable shooting-and-bouncing candidate generation in native Sionna:
`sb_candidate_generator.py` invokes that generator for any depth greater than
zero. The image method subsequently refines discovered specular candidates.
There is no public switch for exhaustive first-order image-method discovery
without shooting. The optimization branch now adds an explicit
`SingleBouncePathSolver` adapter; see [OPTIMIZATION.md](OPTIMIZATION.md).
The measurements below remain the native sampled baseline. The adapter has
separate paired measurements and does not enable diffuse or diffracted paths.

The earlier tracing measurements also used one CIR epoch per solve; they never
traced per fast-time sample. The earlier dense-memory warning concerned
time-expanded coefficients/Doppler and CPU copies, which this compact SISO
implementation now avoids.

## Test results

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

## Revised work and memory budgets

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

## Reproduce the accepted baseline

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
