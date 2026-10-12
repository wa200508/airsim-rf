# Experimental fixed-surface diffuse sampling — 12 October 2026

An **opt-in solver implementation** now preserves sampled mesh locations across
radio motion. It addresses the sliding-sample mechanism found in the
[preceding audit](../diffuse-stability-20261012/REPORT.md), without changing the
existing angular sampler or live-recorder defaults. It is not yet a calibrated
rough-surface model or a fully qualified live sensing feature.

## Implementation and scope

`FirstOrderScatteringPathSolver(surface_sampling=True)` draws triangles in
proportion to their area and uniform barycentric points within each triangle.
Every link shares that seeded point set. Mesh, seed or sample-count changes rebuild
it; radio position, orientation and antenna-pattern changes do not. Visibility
from **both** endpoints and the Sionna material, polarization, antenna and Doppler
calculations are recomputed at each solve.

The proposal density is `q_A = 1 / total_mesh_area`. The existing Sionna ray-tube
correction becomes `4π q_A r_TX² / cos(theta_TX)`, yielding incident solid-angle
weight `cos(theta_TX) / (N q_A r_TX²)`. This is the area counterpart of the existing
angular importance sampler. No measured roughness or stochastic microstructure
law is invented, and no phase smoothing is applied. Sample count defines the
numerical realization; changing it does not preserve sample identities.

The point cache uses mesh-buffer identity checks already employed by the planar
candidate cache. Static geometry is the intended use. A mesh edit regenerates
points and starts a new realization; it is not continuous moving-object scattering.
The `cache_sampling` option still controls only the older angular draw cache.

## Motion replay

The same two-drone starting kinematics, synthetic ground, 915 MHz carrier, three
seeds and 128/512/2,048 attempted samples used by the prior audit are replayed.
The [physical layout](../moving-receiver-20261011/REPORT.md) is unchanged.
This is propagation-only replay, not a new live flight or an I/Q capture. Signal
offsets are 0.1, 1 and 12 ms; they are not durations of generated sample streams.
No performance measurement is claimed.

| Offset | Median phase residual, original angular sampler | Median phase residual, fixed-surface sampler |
|---|---:|---:|
| 0.1 ms | 0.00423–0.00515 rad | 0.000116–0.000136 rad |
| 1 ms | 0.0414–0.0517 rad | 0.000114–0.000162 rad |
| 12 ms | 0.4999–0.6210 rad | 0.000238–0.000285 rad |

Ranges span the nine seed/budget combinations per offset. Sampled-point movement
is zero in every fixed-surface comparison. At 12 ms the worst per-case 95th
percentile phase residual is below 0.000657 rad. Stationary repeats and fresh
solver comparisons pass. These are numerical model checks, not physical accuracy
or uncertainty estimates. [Full motion results](stability.json).

Exported path order is not a physical identity. Repeat comparisons now sort by
vertex coordinates, avoiding equal-delay ordering ambiguity; moving fixed-surface
paths match by vertex proximity. The original audit's angular paths still match
antenna-relative directions. An initial delay-sorted fresh-solver check produced
an ordering false positive and was corrected before these results were published.
The generic audit retains its conservative `persistent_surface_scatterers_qualified:
false` field: full physical roughness/live-I/Q qualification has not been established.

## Power normalization and sampling cost

A separate 2.4 GHz ground fixture compares `sum(abs(path_gain)²)` across samplers.
This is **incoherent path power**, not coherently summed received power.
TX/RX are at (−5, 0, 10)/(5, 0, 10) m with isotropic vertical arrays.

| Attempts per link | Seed 42, surface/angular power | Seed 43 | Seed 44 |
|---|---:|---:|---:|
| 4,096 | 1.034 | 0.772 | 0.836 |
| 16,384 | 1.109 | 1.035 | 0.945 |

[Raw power results](power.json) show the expected sampling tradeoff: uniform mesh
area spends effort where antenna importance sampling may concentrate elsewhere.
The lower-budget result does not satisfy a universal 20% agreement claim. At
16,384 samples the three checked seeds are within −5.5% to +10.9%; that is limited
fixture evidence, not convergence proof for arbitrary terrain or antenna patterns.

## Checks and reproduction

The [P100 scattering suite](gpu-tests.log) reports **14 passed**, including fixed
vertices under motion, Doppler continuation, incoherent power comparison, mesh
invalidation, and loss/restoration of valid reflection when either endpoint
crosses the ground. That last check exercises side-of-surface visibility, not a
complete obstacle-crossing or path-birth/death flight experiment.
The [standard suite](standard-tests.log) reports **200 passed, 157 skipped**.
GPU-only skips are not counted as CPU passes.

Use the existing GPU container invocation from the preceding audit with:

```bash
scripts/basis_launch.py scripts/qualify_diffuse_stability.py --pascal-compat \
  --surface-sampling --output recordings/surface-stability-replay
```

For the power table, use the same container and:

```bash
scripts/basis_launch.py scripts/qualify_surface_power.py --pascal-compat \
  --output recordings/surface-power.json
```

The default trajectory is committed. No Runtime server is needed. The audit's
output directory must be new; the power output's parent directory must exist.
The available P100 ran propagation; existing host services were untouched.

## Remaining work

The option is available on the path solver, **not yet exposed in the live recorder
or SDR receiver constructors**. Next integrate it as an explicit experimental
choice, verify rendered I/Q against a reference, and exercise occlusion transitions
and turns. Large meshes, directional antennas, power convergence, material changes,
and coherent roughness statistics need broader qualification before any default
change. The live diffuse limitation remains applicable to the current default.
