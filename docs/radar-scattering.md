# First-order radar target and terrain response

Radar acquisition uses one direct illumination/return interaction per scatterer:
`TX → point target → RX` or `TX → terrain sample → RX`. The monostatic radio
endpoints are colocated. RCS points are never installed as radios in Sionna,
and no lists of outbound and inbound multipath are cross-multiplied. Ordinary
ESM/comms radio pairs retain their configured propagation and rendering.

## Channel and signal model

A point target has the monostatic received-power scaling
`Pt × Gtx × Grx × wavelength² × RCS / ((4π)³ × range⁴)`.
Each terrain sample uses the same equation with an effective patch RCS:
`sigma0 × represented actual surface area × cos(incidence)^exponent`.
Sigma0 is a linear RCS-per-area ratio; scenario values use `sigma0_db`.
The default −20 dB earth value and exponent 1 are illustrative, uncalibrated
choices at this carrier. Dielectric permittivity/conductivity do not uniquely
determine rough-surface backscatter, so these rules are supplied separately.
Multiple classes require corresponding shared-mesh material IDs; textures and
LULC rasters are not automatically interpreted.

Stratified area samples cover all configured surface objects. Each represents
`total configured surface area / propagation.samples_per_link` square metres, making expected
scattered power independent of the sample budget. A seeded, unit-magnitude
random scattering phase is fixed at each sample. Geometry, seed or budget edits
start a new realization; motion alone never redraws scatterers. Coherent
interference causes finite-realization power fluctuations, so numerical and
physical convergence must be studied rather than assumed from 1,024 samples.

For each chirp, discard scatterers outside the configured slant-range limit,
then apply surface-front-face and antenna gain checks and batch direct visibility
against the actual Sionna/Mitsuba mesh. The engine uses the active CPU or CUDA
ray backend. Target bodies retain scalar RCS; their illustrative box visuals
are outside the RF mesh. A surface-endpoint tolerance scales with float32 ray
precision to prevent self-intersection. A monostatic unobstructed segment is
reciprocal; an obstructed target contributes no echo. There are no reflected
illumination/return legs, diffraction or secondary scattering. These are
fidelity assumptions, not a general assertion that such returns are always weak.

Each surviving echo retains round-trip delay `2 × range / c`, carrier phase and
narrowband Doppler derived from relative radial velocity. For stationary terrain,
the moving radar still creates Doppler. The dechirped convention is
`TX × conjugate(RX)`; positive range rate is receding. Within a 4 ms source
window, actual radar readback and moving target poses are extrapolated at
constant velocity for each chirp, preserving phase across window boundaries.
Absolute Unix time never enters an enormous carrier-phase argument.

The IF bandpass response is evaluated for all current beat frequencies using
cached analog filter coefficients. Echo tones sum coherently in 128-echo NumPy
tiles, followed by the existing receiver noise and ADC model. Echo work is
linear in scatterer count times output samples, with bounded temporary storage;
there is no quadratic path pairing. NumPy IF synthesis runs on the host even
when visibility uses CUDA. This is not a new measured GPU throughput claim.

## Defaults and ownership

The maintained scenario uses 1,024 terrain samples, a 400 m slant-range cutoff,
three stationary scalar-RCS targets and the existing 77 GHz waveform. A sample
budget describes attempted quadrature points over the map; range, incidence,
beam and occlusion determine the surviving echo count. The 400 m limit is an
explicit model truncation; the physical IF filter rolls off rather than having
an exact hard range cutoff. At zero Doppler its 4.5 MHz upper corner corresponds
to roughly 432 m in this chirp mode.

Edit the shared `propagation.samples_per_link` budget, plus `radar.clutter`,
`radar.max_range_m` and `radar.targets` in the
[scenario radios](../scenarios/mmwave-radar/radios.json).
The [compiler](../src/airsim_rf/dashboard_scenario.py) resolves mesh classes and
heights. [radar_scattering.py](../src/airsim_rf/radar_scattering.py) owns surface
quadrature and visibility; [fmcw.py](../src/airsim_rf/fmcw.py) owns echo rendering;
[dashboard_radar.py](../src/airsim_rf/dashboard_radar.py) applies hardware-neutral
TX/RX commands and packs acquisition gates. TX off suppresses both targets and
terrain while configured receiver noise remains. Sample recording, the external
radar skill, and the generic dashboard display contract remain independent of
scene truth. Per-window producer metadata records terrain sampling/visibility
counts; receiver metadata contains no target or clutter definitions.

Tests cover radar-equation power, area normalization across sample budgets,
incidence weighting, stationary realization reuse, coherent slow-time evolution,
shared-mesh target/terrain blockage, range rejection before tracing, TX-off
suppression, 1,024 independent echoes with linear term count, and actual
acquisition → lossless I/Q archive → unchanged external radar processing.

For published terrain-clutter workflows and the limits of their comparison,
see the [environmental RF source review](references.md#environmental-rf-references).


CPU screening for the implemented model, with both median ± SD and p95 stage
tables in one place, is in the [runtime report](../results/reviews/first-order-radar-20261023/REPORT.md).
It includes both configured terrain sampling and a separate 1,024-valid-echo
stress, with explicit exclusions and no GPU/realtime claim. Reproduce using
`benchmarks/benchmark_first_order_radar.py`.


## Inspect the clutter independently

The [clutter visibility and sampling audit](../results/reviews/clutter-sampling-sweep-20261023/REPORT.md)
isolates side-looking flat ground, forward-looking flat ground and a ridge with
actual mesh shadowing. Every power-of-two proposal budget from 1,024 to 524,288
uses the production echo source, 64 moving-platform chirps and the independent
radar skill FFT. Plots share one absolute voltage-power scale. Noise-free ADC
maps and separately labeled pre-ADC references accompany saved complex I/Q.
This is a sampling/fidelity experiment, not a calibrated terrain or GPU benchmark.
Changing the sample budget changes the random-phase realization; individual
speckles need not converge pixel by pixel. Area-normalized expected surface
power remains constant. The same report separates this effect from receiver
noise hiding clutter in the maintained dashboard scenario.
