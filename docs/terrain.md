# Terrain

- [Ground Scattering](#ground-scattering)
- [Terrain Scenario](#terrain-scenario)
- [Terrain Signature](#terrain-signature)

<a id="ground-scattering"></a>

## First-order ground scattering: both TX and RX antenna coverage



**Runtime context (2026-10-05):** This guide measures channel generation and scene-dependent surviving paths. Sampling attempts are not guaranteed valid paths, and channel timing excludes continuous sample rendering. See [current runtime and wall-clock costs](archive/runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

For primary-source comparisons with MathWorks, Ansys, Remcom, NVIDIA and
RadarSimPy, see [published environmental RF precedents](references.md#environmental-rf-references).
The report covers terrain reflectivity, phase consistency, coherent I/Q
validation and the environmental paths excluded by the first-order limit.

The 144 paths in the optimization's street-scene test were retained direct and
specular paths, not 144 rays sampling ground illumination. Both antenna patterns
were applied to their fields, but distributed diffuse return was absent. Those
measurements do not establish realistic ground clutter or its runtime.

The optimization branch now adds `FirstOrderScatteringPathSolver`, combining
exact specular candidates with first-order diffuse surface samples. It connects
independent transmitters to receivers, with no reciprocity or monostatic return
assumption. There is one surface interaction; the two visibility segments are
TX → surface and surface → RX.

### Antenna-aware coverage

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

### Sampling weights and signal model

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

### What the test environment assumes

The original measurements below use flat ground. The separate
[DEM scenario and waterfall report](terrain.md#terrain-scenario) adds triangulated
elevation relief with the same material assumptions and radio trajectories.

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

### Measurements and verification

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

[GPU deployment metrics](archive/planning.md#gpu-runtime) separate measured CPU costs from
conditional GPU ray-stage estimates for one GPU per receiver. The new report
measures host NumPy sampling independently and records per-GPU query counts,
channel export capacity, pulse/physics budgets and unmeasured GPU/VRAM status.

The propagation tests cover both endpoint proposal boresights and
sidelobe support, independent TX/RX steering, importance-versus-uniform power,
native uniform-sampling agreement, power stability under increased ray counts,
physical scattered delay and both endpoint Dopplers, zero-scattering materials,
I/Q generation, and rejection of insufficient sampling/candidate budgets.
These are correctness checks for the stated model, not field calibration.

### Run it

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

<a id="terrain-scenario"></a>

## Flat ground and DEM terrain: tested RF scenarios



**Runtime context (2026-10-05):** Offline selected epochs and waveform plots demonstrate terrain effects, not a continuously advancing 120 Hz end-to-end flight. See [current runtime and wall-clock costs](archive/runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

For a clear view of individual terrain features in I/Q, see the
[focused beam scan and bandwidth comparison](terrain.md#terrain-signature). The
aggregate scenario below tests many links; it is not a terrain imaging scan.

The [published environmental RF comparison](references.md#environmental-rf-references)
connects this scenario to terrain-clutter and scene-multipath examples from
MathWorks, Ansys, Remcom, NVIDIA and RadarSimPy, with citations and modeling limits.

These figures come from actual Sionna channel solves and the repository's complex
voltage synthesis. They compare the original flat-ground fixture with a small
synthetic digital elevation model (DEM). The offline scenario supplies platform
poses directly; it does not require a live AirSim instance.

### Elevation model

The terrain spans 200 × 200 m, sampled on a 21 × 21 grid at 10 m spacing. Broad
Gaussian hills, a diagonal drainage swale, a gentle eastward slope and low
sinusoidal relief give elevations from −1.73 to 6.45 m. The reproducible formula
is in [`demo_terrain()`](../src/airsim_rf/terrain.py). It represents plausible low
relief, not a surveyed site or a calibrated land-cover model.

The figures and underlying I/Q were regenerated on the P100 using CUDA/OptiX
propagation and direct CUDA rendering. [Reproduction and timing scope](setup.md#regenerate-documentation-figures-on-the-p100).

![DEM elevations, platform locations and triangulated surface](figures/terrain_overview.png)

Each grid cell becomes two triangles, for 441 vertices and 800 faces. Those
triangles are the geometry Sionna actually intersects: elevations affect path
lengths, surface normals, specular reflections and visibility. The RF scene
uses face normals, so its surface is piecewise planar. A 10 m mesh does not
resolve soil roughness, vegetation or small terrain features.

`TerrainGrid(x_m, y_m, heights_m)` also accepts other finite, increasing local
Cartesian grids. `write_ply()` exports RF geometry and `elevation_at()` uses the
same triangle interpolation as that geometry. Heights are in metres, with z
upward and a shared local datum. No raster/GIS ingestion, georeferencing or
automatic AirSim world import is included. A running AirSim scene must use
matching geometry and the existing coordinate conversion for consistent truth.

Both fixtures retain identical synthetic material properties: relative
permittivity 5, conductivity 0.01 S/m, slab thickness 0.5 m, scattering
coefficient 0.3 and Lambertian diffuse scattering. Sionna uses its nonmagnetic
material model. There are no spatial land-cover classes or roughness textures.

### Platform and radio scenario

| Parameter | Value |
| --- | --- |
| Propagation | Independent one-way TX → RX; LoS, specular and diffuse; depth 1 |
| Transmitters | 100, initially x=0, y evenly spaced from −25 to +25 m, z=10 m |
| Receiver | One physical RX, initially (10, −5, 15) m |
| TX motion | +1 m/s along x, constant absolute z |
| RX motion | +0.5 m/s along y, constant absolute z |
| Antennas | 1 × 1 TR 38.901, vertical polarization, approximately downward |
| Antenna pitch | TX: π/2 + 0.05 sin(t+i); RX: π/2 + 0.05 sin(t), radians |
| Carrier | 24.125 GHz |
| Diffuse attempts | 1,028 per TX/RX pair; 514 from each endpoint |
| Proposal distribution | 90% endpoint gain pattern, 10% uniform directions |
| Random seed | 42, common random numbers across pulse epochs |
| Pulse cadence | 200 Hz, channel computed once per selected pulse |
| Figure snapshots | 32, every twentieth pulse: 0 to 3.1 s in 0.1 s steps |

The figures use the same setup and trajectory function as
`benchmark_scattering.py`. The 100-TX/1-RX channel workload represents one
receiver worker in the proposed 100-TX/10-RX deployment. The figures do not
measure ten workers concurrently. Each platform stays at a fixed height above
the datum, so its clearance above the DEM varies; it is not terrain-following.

### Delay and Doppler waterfalls

![Flat-ground and DEM channel delay and Doppler waterfalls](figures/channel_waterfalls.png)

Every row is one channel snapshot. We histogram **sum(|a|²)** across all valid
direct, specular and diffuse paths from all 100 transmitters. This is an
incoherent channel-power diagnostic; mutually uncorrelated, unit-power
transmissions give it a received-power interpretation. It is not the coherent
voltage sum from 100 transmitters.

The left column groups absolute path delays into 12.5 ns bins and displays
0–400 ns, zooming the stronger returns. The underlying data cover 0–1,200 ns.
The right column groups instantaneous path Doppler into approximately 4.17 Hz
bins over −200 to +200 Hz. This is Sionna's geometric endpoint Doppler, **not**
a slow-time FFT or a measured velocity spectrum. Each column shares one color
scale between flat ground and terrain; rows are not independently normalized.

Over this trajectory the flat fixture retains 96,383–96,416 diffuse paths per
snapshot plus 100 LoS and 100 specular paths. The DEM retains 96,483–96,514
diffuse paths, 100 LoS paths and 115–119 specular paths. These are the actual
retained paths, not a promise that every sampling attempt produces a return.

### Coherent LFM response

![Single-transmitter LFM pulse-compressed waterfalls](figures/lfm_waterfalls.png)

For this plot we select **TX 50 → RX 0** from those same channel solves. We
generate complex voltage with the existing `synthesize_voltage()` function,
using a 20 MHz LFM sweep over 8 µs, 1 W transmit power, a 50 Ω load, 50 MS/s and
a 12 µs receive window. Thermal noise is disabled. These are explicit
demonstration settings, not an additional off-the-shelf radar specification.

Each path delays the chirp, scales it by its complex Sionna coefficient and
applies narrowband Doppler during the pulse. The path voltages are added
coherently. A linear matched filter, divided by transmitted pulse energy,
produces each waterfall row. The color is 10 log10 of its voltage magnitude
squared, relative to 1 V², with a shared scale for both surfaces.

The horizontal axis is **total TX–surface–RX path length cτ**. This is a
bistatic link, so dividing by two and calling it monostatic target range would
be incorrect. The nominal path-length resolution is c/B ≈ 15 m, with a 6 m
sample spacing. Matched-filter sidelobes and coherent cancellation also affect
the displayed response.

The same seed does not create persistent physical scatterers. Sampled hit
points move with antenna proposals. The coherent response is valid as an output
of the current model, but its pulse-to-pulse fluctuations do not establish
realistic rough-ground speckle or Doppler coherence. No slow-time radar FFT is
used here. [The scattering guide](terrain.md#ground-scattering) explains those limits.

### I/Q frequency waterfall

![Received LFM I/Q spectrograms for flat ground and terrain](figures/iq_spectrograms.png)

These are spectrograms of the **actual complex voltage samples** for TX 50 at
the final, 3.1 s epoch. The sweep runs from approximately −10 to +10 MHz; delayed
copies and interference modify its response. We use a 128-sample Hann window,
16-sample hop and 256-point FFT, with a two-sided power spectral density in
V²/Hz. The noise-free window ends after 12 µs, long before the next 5 ms PRI.
The data do not represent continuous full-PRI capture.

### Runtime and reproduction

The CPU timing reports remain separate from the figure-generation trajectory.
First-use compilation and cached kernels can dominate different snapshots;
plotting and I/Q synthesis timings are not included in the channel timer.
[GPU planning](archive/planning.md#gpu-runtime) distinguishes measured host costs from
conditional GPU estimates. No GPU runtime or VRAM measurement is added here.

The DEM has 800 distinct specular planes rather than one. At 100 TX / 1 RX,
its upper bounds are 182,900 candidates and 365,700 visibility queries per
pulse, versus 103,000 and 205,900 for flat ground. At 200 pulses/s, the ray stage
alone needs 73.14 million queries/s per GPU if it consumes the entire budget.
Actual retained paths are far fewer than specular candidates. Query throughput
still depends on scene geometry and excludes fields, sampling and I/Q work.

For this DEM, set the per-source path cap to at least
`num_rx * (1028 + 1 + 800)`. The default total candidate limit of two million
covers 100 TX / 10 RX (1,829,000 candidates); a finer mesh can exceed it. The
solver rejects an insufficient cap rather than truncating coverage. Use
`solver.specular_plane_count(scene)` when budgeting another mesh.

```bash
python3.12 scripts/bootstrap.py
.venv/bin/python scripts/generate_demo_terrain.py
.venv/bin/python benchmarks/generate_rf_waterfalls.py --output-dir docs/figures
.venv/bin/python benchmarks/benchmark_scattering.py --scene terrain \
  --tx 100 --rx 1 --samples-per-link 1028 \
  --output benchmarks/results/scattering_cpu_terrain_100tx_1rx_1028.json
.venv/bin/python -m pytest -q
```

The [saved scenario data](figures/scenario_data.json) contain per-epoch
counts and the underlying delay, Doppler and matched-filter waterfall values.
The [terrain timing report](../benchmarks/results/scattering_cpu_terrain_100tx_1rx_1028.json)
records CPU cache/host conditions and per-GPU work arithmetic. The plot script
also saves SVG versions for export.

On the two-core CPU quota, the recorded DEM run used three warmups and ten
timed pulse epochs: median **70.1 ms**, p95 **76.2 ms**, with median host sampling
**17.0 ms** and peak host RSS **214 MiB**. Plane-cache preparation took about
21 ms separately. These are CPU channel measurements, not GPU predictions or
end-to-end I/Q deadlines; the JSON contains the exact values and cache context.

The published CPU test container includes the DEM and plotting script:

```bash
mkdir -p recordings
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/recordings:/work" ghcr.io/wa200508/airsim-rf:latest \
  python /opt/airsim-rf/benchmarks/generate_rf_waterfalls.py --output-dir /work/figures
```

Use `--backend cuda` on a configured CUDA host for a GPU run; it refuses CPU
fallback. The published `latest` image is the CPU test environment, not a
validated GPU deployment image.

<a id="terrain-signature"></a>

## Seeing terrain features in received I/Q



**Runtime context (2026-10-05):** Offline focused terrain/radar demonstration, not a continuous multi-emitter runtime benchmark. See [current runtime and wall-clock costs](archive/runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

Start with this focused scan to see how the existing DEM changes RF data. The
bright ridge below is calculated from **received complex voltage**, using LFM
pulse compression. The first hill, drainage swale and second hill are visible
in its changing delay. The DEM profile is shown separately for comparison.

![DEM profile, flat-control I/Q and terrain I/Q aligned along the flight line](figures/terrain_signature.png)

The terrain has not been exaggerated or replaced. We changed the measurement
geometry and waveform so the existing features become resolvable. The raw
I/Q and compressed profiles are saved in
[`terrain_scan_iq.npz`](figures/terrain_scan_iq.npz).

The [published-implementation comparison](references.md#environmental-rf-references)
relates this scan to RadarSimPy's terrain altimeter and MathWorks' bistatic
land-clutter examples. It distinguishes the demonstrated geometry/delay
behavior from calibrated rough-ground amplitudes and slow-time statistics.

### Why the earlier plots hid the terrain

The [original scenario](terrain.md#terrain-scenario) moved only about 3 m near the center
of the DEM. It did not traverse the main hills. The aggregate channel waterfalls
also mixed 100 transmitter locations and many surface points. Their delay bins
do not identify a unique ground location.

Its 20 MHz LFM pulse resolves approximately **15 m of total path length**
(`c/B`). A 6 m change in near-nadir ground height changes the TX–ground–RX path
by roughly 12 m, and smaller features change it less. Those contributions blend
inside the pulse-compression response. The I/Q frequency spectrogram mainly
shows the transmitted chirp; it is not a topographic image.

This scan makes three explicit changes: a route across the features, a narrower
beam that localizes illumination, and a wider chirp that resolves delay. It is
a separate one-link demonstration, not a replacement for the 100-TX throughput
scenario or a new off-the-shelf hardware specification.

### What was simulated

| Parameter | Focused scan |
| --- | --- |
| Surface | Same 200 × 200 m DEM, 10 m grid, 800 triangles |
| Material | Same uniform permittivity 5, conductivity 0.01 S/m, thickness 0.5 m, scattering coefficient 0.3, Lambertian |
| Radios | One independent TX and RX, separated by 2 m along x |
| Altitude | Both at z=40 m above the fixed datum |
| Route | Approximately (−75, −50) to (+75, +50) m, about 180 m |
| Motion | Both travel at 10 m/s; 91 selected pulse epochs over about 18 s |
| Pulse clock | 200 Hz; selected snapshots are about 0.2 s / 2 m apart |
| Antennas | Downward, synthetic 12° full half-power beamwidth, vertical polarization |
| Pattern | Axisymmetric Gaussian with positive background floor; spherical average gain 1, peak ≈24 dBi |
| Carrier | 24.125 GHz |
| LFM | 200 MHz bandwidth, 2 µs pulse, 1 W, 50 Ω, noise disabled |
| Capture | 500 MS/s complex voltage, 1,500 samples / 3 µs |
| Propagation | Actual Sionna LoS, first-order specular and diffuse paths |
| Diffuse budget | 1,028 attempts/link, half TX and half RX proposals; 10% uniform support |

![Flight line, beam footprints and independently extracted I/Q heights](figures/terrain_scan_geometry.png)

The circles show approximate individual-antenna half-power footprints: solid
for TX, dashed for RX. Their overlap concentrates surface contributions near
the baseline midpoint. Actual field gain is evaluated for every retained path;
these circles do not crop the mesh or select paths after tracing. Directional
proposals still preserve the uniform component and both antenna patterns.

We use the general one-way TX–surface–RX solver. We do not square a reciprocal
link, introduce point-target RCS, or substitute the DEM height into an analytic
echo generator. The DEM enters the RF calculation through its actual triangle
geometry, normals, visibility and material response.

### How the I/Q becomes the visible ridge

For every selected pulse, Sionna computes complex gains, absolute delays and
endpoint Doppler. `synthesize_voltage()` adds delayed, phase-shifted chirp copies
**coherently**. It computes the channel once per pulse and applies narrowband
Doppler during the receive window.

We correlate those complex samples with the transmitted chirp and divide by
the template's sample energy. All waterfall panels use one shared reference
for voltage magnitude squared; there is no normalization of individual rows,
terrain gain boost, smoothing or terrain-dependent path selection.

The measured ridge is the largest compressed I/Q peak in a fixed **60–100 m
total-path-length gate**. DEM elevations and predicted delays do not enter
that peak estimator. The vertical coordinate converts delay into an equivalent
height for a scatterer beneath the baseline midpoint:

```
L = c * delay
h_equivalent = 40 - sqrt((L/2)² - (2/2)²)
```

Higher ground shortens the path and appears higher in this coordinate. It is
not a general terrain inversion: off-nadir points with different positions and
elevations can have the same delay. The narrow overlapping beams make the
midpoint approximation useful here. Native sample spacing is about 0.60 m in
total path length, or 0.30 m near nadir in equivalent height. The 200 MHz
bandwidth gives approximately 1.5 m path-length resolution, about 0.75 m of
near-nadir height separation; sample spacing is not resolution.

Across the 91 snapshots, the I/Q peak coordinate and DEM midpoint profile have
correlation **0.985** and **0.35 m RMS difference**. This is a descriptive
comparison on this noise-free synthetic scene, not validated field accuracy or
a claim to reconstruct a DEM from arbitrary I/Q. Beam footprint, facets,
specular visibility and coherent interference cause departures from the
midpoint profile.

### Identify the individual features by their delays

![Flat ground and three feature-specific I/Q delay profiles](figures/terrain_delay_cuts.png)

| Feature | Distance along route | DEM midpoint height | I/Q peak equivalent height | Geometric reference total path |
| --- | ---: | ---: | ---: | ---: |
| A: first hill | 40.05 m | 6.28 m | 5.84 m | 67.46 m |
| B: swale | 108.15 m | 0.17 m | 0.44 m | 79.68 m |
| C: second hill | 162.25 m | 5.07 m | 5.24 m | 69.89 m |

Flat ground's reference path is about 80.02 m. The hills' responses arrive
earlier, while the swale approaches the flat-ground delay. Dotted lines are
geometric references calculated after simulation; they do not set the RF
peaks. The first hill is weaker on this shared absolute scale: facet slope and
specular alignment affect amplitude as well as delay. The ideal flat plane
produces a strong specular return; the terrain does not have to be equally
bright to show its shape.

### A bandwidth-only control

![Same terrain channels with 20 MHz and 200 MHz chirps](figures/terrain_bandwidth_comparison.png)

For each terrain snapshot, we reuse **exactly the same complex path gains,
delays and Dopplers** to generate another I/Q block with a 20 MHz chirp. Beam,
geometry, transmit power, pulse duration, receive window and sampling rate stay
the same. Only chirp bandwidth changes. The 20 MHz compressed response is much
broader; the 200 MHz response exposes the terrain ridge. This isolates the
delay-resolution effect from changes in terrain or ray coverage.

The DEM remains coarse and synthetic, with a homogeneous material. The model
still lacks persistent calibrated scatterer phases, roughness correlation and
validated slow-time speckle. We do not use SAR focusing or a slow-time Doppler
FFT here. The illustrated ridge demonstrates geometric delay structure in the
current coherent model; it does not validate those missing statistics.

### Reproduce and inspect the raw data

```bash
.venv/bin/python benchmarks/generate_terrain_signature.py
.venv/bin/python -m pytest -q
```

The script saves PNG/SVG plots, a
[scenario and comparison summary](figures/terrain_signature_data.json)
and the complex-sample archive. The figure-generation run is not a GPU runtime
benchmark. `--backend cuda` refuses CPU fallback on a configured CUDA host.

```python
import numpy as np
from scipy.signal import correlate

with np.load("docs/figures/terrain_scan_iq.npz", allow_pickle=False) as data:
    iq = data["iq_dem"]                  # complex64 [91, 1500], volts
    fs = float(data["sample_rate_hz"])
    width = float(data["pulse_width_s"])
    bandwidth = float(data["bandwidth_hz"])
    t = np.arange(round(width * fs)) / fs
    template = np.exp(1j * np.pi * bandwidth * (t*t/width - t))
    profile = correlate(iq[20], template, mode="full", method="fft")
    profile = profile[len(template)-1:] / np.sum(np.abs(template)**2)
    path_length_m = np.arange(len(profile)) * 299792458 / fs
```

The archive also contains `iq_flat`, `iq_dem_20mhz`, compressed complex profiles,
pose/pulse metadata and the separately labeled DEM reference. The CPU test
container includes the archive and generator:

```bash
mkdir -p recordings
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/recordings:/work" ghcr.io/wa200508/airsim-rf:latest \
  python /opt/airsim-rf/benchmarks/generate_terrain_signature.py --output-dir /work/terrain_scan
```

