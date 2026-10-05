# Exhaustive single-bounce optimization

**Runtime context (2026-10-05):** Historical tiny-scene LoS/specular optimization with 144 surviving paths. Channel timing excludes I/Q generation and distributed diffuse clutter. See [current runtime and wall-clock costs](RUNTIME_STATUS.md) for comparable measurements, hardware, exclusions and ten-minute estimates.

**Scope correction:** the 144-path benchmark below measures retained LoS and
specular paths in a tiny scene. It has no distributed diffuse ground return and
does not establish clutter coverage. Both antenna patterns weight its fields;
it does not importance-sample either pattern. The new
[TX/RX-aware ground-scattering mode](GROUND_SCATTERING.md) covers distributed
first-order scattering with an explicit per-link sampling budget and separate
timings. These specular timings must not be used as its runtime estimate.

This branch implements **one-way TX → RX** propagation for ESM, comms and other
RF skills. It does not infer a return channel from reciprocity, square a channel,
or assume a monostatic radar. The radar worker remains its existing point-target
implementation; a general network worker and multi-emitter I/Q mixing remain
separate work.

## What changed

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

## Measurements

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

## Environment and antenna choices

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

## Reproduce

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
