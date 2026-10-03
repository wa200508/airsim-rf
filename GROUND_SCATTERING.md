# First-order ground scattering: both TX and RX antenna coverage

The 144 paths in the optimization's street-scene test were retained direct and
specular paths, not 144 rays sampling ground illumination. Both antenna patterns
were applied to their fields, but distributed diffuse return was absent. Those
measurements do not establish realistic ground clutter or its runtime.

The optimization branch now adds `FirstOrderScatteringPathSolver`, combining
exact specular candidates with first-order diffuse surface samples. It connects
independent transmitters to receivers, with no reciprocity or monostatic return
assumption. There is one surface interaction; the two visibility segments are
TX → surface and surface → RX.

## Antenna-aware coverage

The provisional default is **1,028 sampling attempts per TX/RX link**, half from
the transmitter's pattern and half from the receiver's pattern. The requested
number is configurable. This interpretation treats “1028” as the integer 1,028,
not an exponent or a required count of nonzero physical paths.

Each proposal allocates 90% of its probability according to that endpoint's
antenna power pattern and 10% uniformly over all directions. Both main lobes,
multiple lobes and sidelobes remain eligible. These are continuous angular draws
inside a 64 × 128 equal-solid-angle grid, whose cell-center gain estimates define
the proposal density. Actual field calculation evaluates the complete pattern
at each path's actual direction. The proposal grid can under-resolve a very
narrow or irregular beam; its uniform component preserves support, but more
samples and a finer/adaptive proposal may be necessary for low variance.

The receiver proposal looks outward from RX toward the illuminated/scattering
surface, using the same pattern-direction convention as Sionna's incoming-field
projection. Both endpoint orientations rotate the sampled directions. Every
sample traces the first hit from its proposing endpoint, then tests the other
segment for visibility and reflection hemisphere consistency. The actual hit
triangle and its radio material determine the diffuse response. These proposals
use the scene's element antenna patterns; beamforming weights/array-factor
importance sampling are not implemented. The measured profile uses 1 × 1 arrays.

Misses, blocked paths, zero-scattering materials and antenna nulls contribute
zero. A request for 1,028 attempts can therefore retain fewer than 1,028 paths.
The solver does not duplicate weak paths or invent returns to meet a count.
There is an explicit total-candidate limit and the per-source cap must cover
all diffuse attempts plus all LoS/specular candidates, across receivers.

## Sampling weights and signal model

Importance concentration must not increase simulated received power. For a
sampled surface point y, define the angular densities p_T and p_R and distances
r_T and r_R. With endpoint mixture weights alpha_T and alpha_R, the surface-area
density is

```
q_A(y) = alpha_T * p_T(direction_TX_to_y) * |cos(theta_T)| / r_T²
       + alpha_R * p_R(direction_RX_to_y) * |cos(theta_R)| / r_R²
```

The respective endpoint samples use this **complete mixture density**, including
both proposals. This is valid on points visible from both endpoints; samples
that fail either visibility check contribute zero. The ray-tube solid angle
supplied to Sionna's diffuse material is

```
Delta_Omega_T = |cos(theta_T)| / (N * q_A(y) * r_T²)
```

Sionna initializes a ray-tube solid angle of 4*pi/N and divides by the candidate's
stored probability. The adapter stores the positive density correction
`4*pi*q_A*r_T²/|cos(theta_T)|` in that field. It is an importance correction,
not the probability of randomly choosing a diffuse interaction: the diffuse
material response is evaluated explicitly, and material strength still controls
its amplitude. For uniform forward-only sampling this reduces to the original
4*pi/N ray-tube weight. The tests compare the uniform bidirectional limit to
native Sionna and check that importance concentration preserves summed path
power.

Sionna computes the dielectric/conductive slab response, diffuse angular
scattering pattern, polarization/XPD, both antenna fields, spreading, path
length and moving-endpoint Doppler. The default diffuse material has a real
Jones operator with geometric carrier-delay phase; this adapter adds no
independent random scatterer phases. The existing I/Q receiver applies the
compact complex coefficients to delayed waveform samples and evolves narrowband
Doppler analytically during each pulse, with no fast-time ray tracing.

This preserves Sionna's diffuse **ray-tube/power normalization**. The diagnostic
`sum(|a_p|²)` is an incoherent path-power sum, not the power of the coherent I/Q
sum `|sum(a_p*x_p)|²`. Sampling-count and power tests do not establish coherent
rough-ground speckle statistics or I/Q convergence.

The same seed is reused at successive pulse epochs as common random numbers,
but sampled hit points follow moving/rotating antenna proposals. They are not
persistent world-fixed scatterers. Within a pulse the geometry is frozen and
endpoint Doppler is applied. Across pulses, persistent roughness/scatterer
identities, spatial correlation, and speckle/slow-time coherence still require
an explicit terrain model. Repeating a seed alone does not supply that physics.

## What the test environment assumes

The new synthetic fixture is a flat 200 × 200 m ground mesh with two triangles.
It has relative permittivity 5, conductivity 0.01 S/m, thickness 0.5 m, scattering
coefficient 0.3 and Sionna's default Lambertian scattering pattern. These are
synthetic, spatially uniform assumptions, not measured soil or land-cover data.
Sionna's standard radio-material model assumes nonmagnetic materials; this
fixture does not assign a separate permeability model.

Both endpoints use vertical-polarized TR 38.901 element patterns pointed
approximately downward. The transmitters lie along a 50 m line at 10 m height;
receivers are at 15 m height. Platforms move and their antenna pitch varies.
Materials can be assigned per mesh object/region for land-cover classes, but no
land-cover importer, measured roughness data, vegetation/volume scatter or
stochastic terrain texture is added here. Flat specular plane merging does not
replace this diffuse sampling pass.

## Measurements and verification

The CPU host has a two-core quota and 8 GiB RAM, with no GPU. Timings include
host proposal generation, synchronized propagation and one-epoch NumPy
CIR/Doppler export. They exclude I/Q synthesis, AirSim, transport, moving mesh/BVH
updates and diagnostic path classification.

| Workload | Diffuse attempts | Median / p95 | Peak host RSS |
| --- | ---: | ---: | ---: |
| 100 TX / 1 RX, initial trajectory run | 102,800 | 719 / 754 ms | 219 MiB |
| 100 TX / 1 RX, repeated cached trajectory | 102,800 | 51.7 / 53.3 ms | 201 MiB |
| 100 TX / 10 RX in one solve | 1,028,000 | 355 / 367 ms | 414 MiB |

The one-RX runs used ten timed epochs and three warmup epochs; the ten-RX run
used five timed epochs and two warmup epochs. The one-RX fixture retained about
96,000 diffuse paths, approximately 950–980/link. The ten-RX fixture retained
about 964,000, approximately 940–990/link. LoS and specular paths are additional.
Exact per-epoch counts and original timings are committed in
`benchmarks/results/scattering_cpu_*.json`.

The initial one-RX run had substantial first-use compilation as retained path
counts changed. A repeated identical trajectory benefited from the persistent
JIT cache; the later ten-RX run also benefited from previously compiled material
code. These are different cache states, not evidence that ten receivers cost
less than one. New path-count/scene variations can incur fresh compilation.
All measured epochs missed 5 ms; GPU deadlines and VRAM remain unmeasured.
Host sampling itself remains work to optimize before a GPU real-time claim.

**51 tests pass.** New checks cover both endpoint proposal boresights and
sidelobe support, independent TX/RX steering, importance-versus-uniform power,
native uniform-sampling agreement, power stability under increased ray counts,
physical scattered delay and both endpoint Dopplers, zero-scattering materials,
I/Q generation, and rejection of insufficient sampling/candidate budgets.
These are correctness checks for the stated model, not field calibration.

## Run it

```python
from airsim_rf.scattering import FirstOrderScatteringPathSolver
solver = FirstOrderScatteringPathSolver()
paths = solver(scene, samples_per_src=1028, max_num_paths_per_src=2048)
```

For SISO I/Q:

```python
receiver = RFReceiver(scene, config, path_solver="first-order-scattering",
                      samples_per_src=1028, max_num_paths_per_src=2048)
block = receiver.capture(waveform, sim_time_ns)
```

The scene must assign nonzero scattering coefficients where diffuse return is
intended. The receiver does not replace material properties with synthetic ones.
`samples_per_src` retains native API spelling but means attempts **per link**
in this adapter. For multiple receivers, size the cap for all their candidates.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python benchmarks/benchmark_scattering.py --tx 100 --rx 1 --samples-per-link 1028 --output ground_1rx.json
.venv/bin/python benchmarks/benchmark_scattering.py --tx 100 --rx 10 --samples-per-link 1028 --output ground_10rx.json
CUDA_VISIBLE_DEVICES=0 .venv/bin/python benchmarks/benchmark_scattering.py --backend cuda --tx 100 --rx 1 --samples-per-link 1028 --iterations 200 --warmup 20 --output ground_gpu.json
```

GPU runs refuse CPU fallback. The sample budget should subsequently be chosen
by convergence of received power, delay/Doppler spectra, weak-path contributions
and intended I/Q statistics on the intended terrain. An order of 1,000 samples
per link is a starting budget, not a fidelity guarantee.
