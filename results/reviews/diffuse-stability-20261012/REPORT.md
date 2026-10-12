# Moving diffuse-path stability audit — 12 October 2026

**Repeatability checks pass; coherent moving diffuse scattering is not qualified.**
The sampling cache preserves the result, but fixed antenna-relative ray directions
intersect different surface positions as the radios move. Their regenerated path
phases can differ substantially from continuing the previous snapshot's Doppler.
This is a model limitation, not evidence of a cache bug.

## Experiment

This is GPU propagation replay from the initial measured positions, velocities and
orientations in the [two-drone experiment](../moving-receiver-20261011/REPORT.md),
whose figure shows the physical layout. The same synthetic ground, isotropic
vertical antennas and 915 MHz carrier are used. Only diffuse paths are enabled;
LoS and specular paths are excluded. Positions advance at the measured endpoint
velocities while starting orientations stay fixed. This isolates translation;
it is not a fresh flight simulation or a recorded I/Q experiment.

The audit uses 128, 512 and 2,048 attempted samples per link, seeds 42–44, and
elapsed signal offsets of 0.1, 1 and 12 ms: **27 moving comparisons**. These are
snapshot offsets, not generated signal durations. No throughput claim is made.
The available P100 executes propagation.

Stationary repeats and cached/uncached results are compared after sorting by delay
(relative tolerance 1e-6, absolute 1e-12). Exported path order can change, so an
initial array-index comparison was invalid. The corrected motion analysis matches
launch directions relative to each endpoint, with chord-distance tolerance 1e-5
and unique matches. Tests explicitly cover reordered paths and rejection of
unrelated proposals. The initial index-based diagnostic is excluded from physical
conclusions; the final reproducible audit includes proper matching.

For each matched ray, the phase residual is
`arg(a_new / a_old × exp(−j 2π f_D_old Δt))`.
This includes changes in geometric and material/polarization phase. Vertex
movement directly establishes that the same angular proposal is not attached to
a fixed physical surface point. The complex-sum diagnostic compares the new
coefficient sum with the old sum advanced by local Doppler, normalized by
`sqrt(sum(abs(a_old)²))`. It is neither ADC I/Q NRMSE nor calibrated fading error.

## Results

Ranges below span the nine sample-count/seed combinations at each offset.

| Signal offset | Median sampled-point movement | Median absolute phase residual | Normalized complex-sum change |
|---|---:|---:|---:|
| 0.1 ms | 0.280–0.283 mm | 0.00423–0.00515 rad | 0.00094–0.00609 |
| 1 ms | 2.77–2.88 mm | 0.0414–0.0517 rad | 0.00783–0.05897 |
| 12 ms | 33.2–34.7 mm | 0.4999–0.6210 rad | 0.1155–0.6404 |

[Full results and input hashes](stability.json) include all comparisons, retained
counts, matched counts, displacement percentiles, phase percentiles and starting
RF kinematics. Stationary repeatability and cache equivalence pass in every case.
The sample-count sweep does not remove the per-ray motion effect. These results
do not quantify error against real rough-ground measurements; no such ground-truth
scattering realization is supplied.

The earlier direct/specular phase checks must therefore **not** be generalized
to moving diffuse sensing. Snapshot path geometry and sampling-weight tests remain
useful, but they do not establish temporal speckle, coherent Doppler spectra, or
phase continuity across changing diffuse channel snapshots.

## Required next change

A coherent moving diffuse model needs a defined persistent surface-scattering
realization (or a validated temporal correlation model), consistent weights as
coverage changes, and explicit behavior at visibility transitions. It must be
checked for power normalization, stationary repeatability, both endpoint
velocities, path births/deaths, and cadence/sample-count sensitivity. Reusing a
random seed, disabling the cache, increasing samples, or smoothing phase by hand
is not a demonstrated solution. No scenario-specific phase correction was added.

The current live workflow still enables first-order diffuse sampling by default.
Its guidance now explicitly distinguishes timestamp/sample continuity from
qualified diffuse temporal coherence. This audit closes the investigation step;
the coherent diffuse-model implementation remains open.

## Reproduce

```bash
docker run --rm --gpus device=0 --network none --tmpfs /.drjit:rw,mode=1777 \
  --user "$(id -u):$(id -g)" -v "$PWD:/work/repo" -w /work/repo \
  -e PYTHONPATH=/work/repo/src \
  --entrypoint /opt/airsim-rf/.venv/bin/python airsim-rf:p100-modern-gpu \
  scripts/basis_launch.py scripts/qualify_diffuse_stability.py --pascal-compat \
  --output recordings/diffuse-stability-replay
```

The default trajectory input is committed; no server is required. Output must be
a new directory. [Regression log](standard-tests.log): **196 passed, 157 skipped**.
The separate GPU audit is recorded in [client.log](client.log). Existing services
were untouched; no Runtime container was needed or started.
