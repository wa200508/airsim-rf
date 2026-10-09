# References

- [Iq Rendering References](#iq-rendering-references)
- [Environmental Rf References](#environmental-rf-references)

<a id="iq-rendering-references"></a>

## Published implementations of channel-to-I/Q rendering



Sources and implementation paths reviewed on **2026-10-05**. This review
complements the [environmental RF comparison](references.md#environmental-rf-references)
and [affordable real-time architecture study](archive/planning.md#affordable-realtime-rf).
It distinguishes actual sample processing from channel generation, link
performance estimation and visualization. The external implementations were
inspected; they were not benchmarked locally against our workload.

### The operation and the workload

Time-domain channel simulation, also called channel emulation, takes complex
transmitted samples, applies propagation delays, complex gains and temporal
evolution, and sums the contributions at each receiver. Fractional delays
require a reconstruction/interpolation convention. Noise, receiver filtering,
oscillator errors and sample-clock conversion are additional processing.

A tapped delay line can preserve Doppler: its complex coefficients must evolve
at the required sample times. Freezing the coefficients over a block loses
intra-block evolution; the filter representation itself does not require that
approximation. A static FFT convolution alone has the same limitation.

Our target is 100 independent transmitters and 10 receivers, continuous 2 MS/s
I/Q, 120 Hz scene/channel updates, first-order environmental propagation and
moving platforms. The renderer stress case supplies 1,028 valid paths per
directed link and 16,667 output samples per update. Each path retains fractional
delay and its own narrowband Doppler phase evolution. Independent links keep
private source buffers and transforms. Neither path pruning nor a common
link-wide Doppler may be used to make this workload cheaper.

None of the references below establishes this exact workload at 120 Hz on a
P100 or within the approximately $5,000 compute budget.

### Comparison

| Implementation | Actual output / computation | Delay and temporal treatment | Relevance and qualification limit |
| --- | --- | --- | --- |
| Sionna PHY [1](#ref1), [2](#ref2) | Complex output samples from supplied complex input samples | Sinc conversion from physical delays; time-varying taps can change every sample | Strong correctness baseline; dense sample-by-delay channel tensors can be large |
| GNU Radio [3](#ref3) | Streaming complex samples through a fading filter | Sinc fractional-delay weights; fading coefficients rebuilt per output sample | Real streaming precedent; statistical faders and nested CPU loops are not our scene-based scaling result |
| NVIDIA Sionna Research Kit [4](#ref4) | CUDA filtering of live I/Q in circular buffers | Integer delay indices; CIR constant within each OFDM symbol | Useful CUDA/buffering reference; SISO and symbol-static channel assumptions differ from our target |
| ACHEM/CHEM [5](#ref5), [6](#ref6) | SDR-facing I/Q processing, resampling, filtering and impairments | Sionna adapter rounds delays and caps tap support; inspected Doppler stage is a common link frequency shift | Useful service and SDR integration architecture; does not establish individual-path Doppler fidelity |
| HermesPy multipath fading [7](#ref7) | Delayed, weighted complex sample copies summed into a receiver signal | Inspected fading implementation rounds delays and generates sample-varying fading | Transparent sample-level reference; not a qualified GPU solution for our path budget |
| Reduced-rank channel-emulation research [8](#ref8), [9](#ref9) | Arbitrary complex input filtered through a reconstructed time-varying channel | Controlled delay/Doppler subspace approximation | Closest architectural precedent for our basis renderer; projection still depends on physical path count |
| SimART [10](#ref10) | Channels, beam evaluation, link metrics and ROS observations | Complex CFR evaluated at subcarrier frequencies and symbol timestamps | Scene/integration complement; inspected main runner does not generate continuous receiver I/Q |

### Sionna PHY: physical paths to sampled filtering

`cir_to_time_channel()` converts complex path coefficients and delays into
sampled channel taps using sinc weights. Its convention assumes sinc transmit
pulse shaping and receive filtering. Truncating the allocated delay support
introduces a numerical approximation; our finite normalized Lanczos operator
is not automatically identical to this convention [1](#ref1).

`ApplyTimeChannel` gathers delayed complex input samples, multiplies by the
time-varying channel tensor, sums delay taps, transmit antennas and transmitters,
and optionally adds noise. The channel tensor includes a time index for every
output sample. Doppler is retained if the supplied path/tap coefficients evolve
at those times; the operator does not generate missing Doppler evolution on its
own [2](#ref2).

This supplies a direct reference for arbitrary waveform filtering without
requiring OFDM. Its channel storage scales with links, antenna pairs, output
samples and delay taps. Constructing and storing the whole tensor is a different
tradeoff from our compact basis filters. Using Sionna PHY also does not resolve
the separate Sionna RT/Dr.Jit compatibility problem on the P100.

### GNU Radio: per-sample streaming evolution

In `selective_fading_model_impl.cc`, `work()` first generates fading sequences.
For every output sample it clears the filter taps, adds each fading component
using sinc weights for its fractional delay, then multiplies the filter by input
history and sums the result [3](#ref3).

The complex stream can contain arbitrary modulation. The standard coefficients
come from statistical fading processes, rather than our environmental ray
paths. This is evidence that time-varying filtering preserves sample-level
evolution, not evidence that its path-by-tap-by-sample loops meet our deadline.

### NVIDIA Sionna Research Kit: real CUDA channel emulation

The kit applies CIRs to I/Q inside an OpenAirInterface radio pipeline. CIRs can
arrive from files or ZeroMQ. Slot samples are held in circular buffers; the
CUDA kernel accumulates delayed, complex-weighted samples, with parallelism
across output samples and tap contributions [4](#ref4).

The reviewed tutorial documents SISO operation, a CIR held constant during each
OFDM symbol and a maximum tap delay of 256 samples. It also normalizes channel
gain and limits noise scaling for the connected-UE demonstration. That is not
an absolute-voltage calibration suitable for adoption unchanged into ESM.
The tutorial allows processing taps in strength order to reduce their count;
we do not adopt that reduction for the all-path benchmark.

This implementation is useful for persistent buffers, integration and kernel
layout. Its real-time demonstration is not a measurement of 100 independent
emitters with individual sample-evolving path Dopplers. The documented benefit
of shared host/device memory on DGX Spark and Jetson platforms also must not be
assumed for a discrete PCIe P100.

### ACHEM/CHEM: SDR-facing service architecture

ACHEM combines virtual USRPs with an I/Q-level channel service. Its pipeline
receives sample buffers, converts formats, resamples, applies channel effects
and returns receiver samples. Worker threads and buffer pools support ongoing
processing. The inspected DSP source includes causal complex FIR filtering
using VOLK dot products [5](#ref5).

The Sionna extension obtains delays and complex gains and accumulates paths
into a tap vector. `cirToTaps()` rounds each delay to a sample position and
discards contributions beyond the configured support; the documented default
cap is 64 taps. The extension's documented polling interval has a minimum of
50 ms [6](#ref6).

In the inspected `Channel::applyFrequencyOffset()`, configured Doppler and
oscillator offset are added into one frequency shift applied to the link's
samples. That preserves a common phase evolution, but is not independent
Doppler for each physical path. Its rounded/capped adapter and update interval
therefore cannot be treated as an equivalent implementation of our workload.
Its service boundaries, SDR interfaces and processing measurements remain
useful architectural precedents.

### HermesPy: explicit delayed sample copies

The inspected `MultipathFadingSample` implementation generates sample-varying
complex fading for each delay component, multiplies the input samples by that
sequence, shifts the result into the output, and applies the spatial antenna
response. Its fading path generator uses rounded sample delays, despite the
general API accepting an interpolation mode [7](#ref7).

This is a readable sample-domain example for comparison with direct rendering.
It does not demonstrate our finite fractional-delay operator, arbitrary
scene-derived channels or GPU capacity. QuaDRiGa channel generation, available
through other HermesPy adapters, must also be distinguished from actually
applying a channel to waveform samples.

### Reduced-rank literature and our projection bottleneck

Kaltenberger, Zemen and Ueberhuber (2007) describe a multidimensional discrete
prolate spheroidal (DPS) subspace representation of geometry-based MIMO
channels. They exploit bounded delay/Doppler support and a numerical accuracy
target to reduce the representation. Their reported complexity reductions are
for the paper's hardware precision and parameters [8](#ref8).

Hofer, Xu and Zemen (2017) implement a related architecture on an SDR/FPGA:
the host generates physical paths and projects them into basis coefficients;
the FPGA reconstructs a time-varying channel and convolves it with complex
input samples. Fractional delays and Doppler are supported. Section IV tests
random complex input with 120 paths, 10 MHz signal bandwidth, 20 MHz
oversampled processing, maximum delay 0.4 microseconds and an accuracy target
of approximately 1e-6 [9](#ref9). These differ materially from our declared
delay bounds and default temporal tolerance of 1e-10.

The important distinction is that reconstruction cost can become independent
of physical path count **after projection**. Their host coefficient
construction still scales with paths and basis dimensions; the paper gives
O(paths × time rank × frequency rank). It does not eliminate channel setup.

Our [Doppler-basis FFT renderer](rendering.md#doppler-basis-fft) uses a Chebyshev temporal
expansion and finite fractional-delay weights, rather than their DPS
construction. It applies each temporal filter to private sampled inputs and
recombines the filtered outputs with sample-varying basis functions. The
Jacobi–Anger identities and error bound in that document have their own
attribution; they are not quoted from these papers.

The P100 [projection investigation](../results/profiling/p100-basis-investigation-20261004/REPORT.md)
shows why projection remains important: the default 100-TX/one-RX case performs
750,028,800 weighted complex contributions per window. A separate instrumented
capture measured approximately 67.52 ms around projection kernel calls. This
is not a pure Nsight instruction measurement or the unprofiled wall latency.
The original full renderer's median was 122.67 ms and its timestamp correctness
qualification failed. Subsequent
[qualified optimization results](../results/profiling/p100-basis-optimized-full-20261004/FINDINGS.md)
fix that phase bug and report 56.167 ms median with 76 CUDA correctness tests
passing, using warp-cooperative projection and 100 links per batch. The
remaining mean renderer gap to 120 Hz is about 6.80 times. The original
projection timing above belongs to the earlier gather kernel, not the new
configuration. Neither the cited papers nor a faster isolated projector
establishes complete 120 Hz service.

The [published projection comparisons](../results/profiling/p100-basis-optimization-20261004/README.md)
now include gather, warp-cooperative and dense matrix implementations. Further
work on reusable delay maps, sparse/tiled or matrix-based projection must
preserve every path and the selected tolerance, and compare with the qualified
warp implementation rather than assume a matrix formulation is faster.
A delay/frequency subspace is another research candidate, whose rank and error
must be qualified against the declared bounds. Published short-delay or
lower-precision results cannot replace that qualification.

### SimART: channels and metrics, not an I/Q renderer

SimART's main runner calls Sionna `paths.cfr()` for subcarrier frequencies and
OFDM-symbol timestamps. It uses the complex response for beamforming, then
derives power/SNR quantities and invokes `PHYAbstraction` for modeled decoding
outcomes. This is not sample generation, waveform filtering or demodulation
of an actual receiver stream [10](#ref10).

Its RF observation export converts path gains to magnitudes and publishes
delay, Doppler, angles and strength. The message does not preserve complex
path phase. The likely rationale is that this interface serves visualization
and channel summaries while phase-sensitive evaluation happens internally;
no explicit author explanation for omitting phase was found. A bridge to our
renderer must preserve the original real/imaginary coefficients and their
time, frequency and antenna conventions. Delay and Doppler alone cannot
recover all reflection/polarization phase.

SimART is consequently relevant for aligned scene assets, motion, visualization
and replay. It supplies no inspected equivalent of our continuous all-path
I/Q renderer or a matching 120 Hz benchmark.

### Sources and inspected code

<a id="ref1"></a>
**[1] NVIDIA, Sionna PHY.** [`cir_to_time_channel` source](https://nvlabs.github.io/sionna/_modules/sionna/phy/channel/utils.html).
Physical-path to sampled time-channel conversion, sinc convention and support.

<a id="ref2"></a>
**[2] NVIDIA, Sionna PHY.** [`ApplyTimeChannel` source](https://nvlabs.github.io/sionna/_modules/sionna/phy/channel/apply_time_channel.html).
Time-varying complex filtering, tensor shapes and transmitter summation.

<a id="ref3"></a>
**[3] GNU Radio.** [`selective_fading_model_impl.cc`](https://github.com/gnuradio/gnuradio/blob/main/gr-channels/lib/selective_fading_model_impl.cc).
Per-output-sample fading, fractional-delay tap construction and streaming filtering.

<a id="ref4"></a>
**[4] NVIDIA, Sionna Research Kit.** [Real-time Channel Emulator tutorial](https://nvlabs.github.io/sionna/rk/tutorials/channel_emulation/channel_emulation.html),
[`chn_emu_cuda.cu`](https://github.com/NVlabs/sionna-rk/blob/main/plugins/channel_emulation/cuda_emulator/src/chn_emu_cuda.cu).
CUDA implementation, buffering, source protocols and documented limitations.

<a id="ref5"></a>
**[5] ACHEM/CHEM.** [I/Q service documentation](https://docs.digitaltwin.sh/chem/),
[DSP filtering source](https://github.com/anilgurses/CHEM/blob/main/src/chem/dsp/channel.cpp),
[link processing source](https://github.com/anilgurses/CHEM/blob/main/src/chem/channel/channel.cpp).
For the framework publication see [Gürses and Sichitiu, *ACHEM: A Real-Time Digital Twin Framework with Channel and Radio Emulation*, arXiv:2604.04742 (2026)](https://arxiv.org/abs/2604.04742).
Implementation claims here come from the inspected code and documentation.

<a id="ref6"></a>
**[6] ACHEM/CHEM.** [Sionna RT extension documentation](https://docs.digitaltwin.sh/sionna/),
[`sionna_client.cpp`](https://github.com/anilgurses/CHEM/blob/main/extensions/sionna/src/sionna_client.cpp).
Complex-gain export, rounded delays, tap cap and polling interval.

<a id="ref7"></a>
**[7] Barkhausen Institut, HermesPy.** [Multipath fading documentation](https://hermespy.org/api/channel/fading/fading.html),
[`fading.py`](https://github.com/Barkhausen-Institut/hermespy/blob/master/hermespy/channel/fading/fading.py).
Inspected path impulse generator and `_propagate` sample processing.

<a id="ref8"></a>
**[8] F. Kaltenberger, T. Zemen and C. W. Ueberhuber.**
[*Low-Complexity Geometry-Based MIMO Channel Simulation*](https://doi.org/10.1155/2007/95281),
EURASIP Journal on Advances in Signal Processing, 2007, article 095281.
Public literature precedent, not a verified drop-in open-source renderer.

<a id="ref9"></a>
**[9] M. Hofer, Z. Xu and T. Zemen.**
[*Real-Time Channel Emulation of a Geometry-Based Stochastic Channel Model on a SDR Platform*](https://thomaszemen.org/papers/Hofer17-SPAWC-paper.pdf),
IEEE SPAWC, 2017. Sections II–IV describe projection, basis reconstruction,
time-varying convolution and tested parameters. This is distinct from the
[2019 Hofer et al. paper already discussed](archive/planning.md#affordable-realtime-rf).

<a id="ref10"></a>
**[10] SimART.** [Repository](https://github.com/guchuanv-alt/SimART),
[main simulation runner](https://github.com/guchuanv-alt/SimART/blob/main/SimART_GUI/scripts/sionna_sim_only_topic2.py),
[RF path message](https://github.com/guchuanv-alt/SimART/blob/main/rf_msgs/msg/RfPathObservation.msg),
[Yan et al., *SimART: A Unified and Open Real-world Multimodal Simulation Platform for 6G Integrated Sensing and Communication*, arXiv:2605.13309 (2026)](https://arxiv.org/abs/2605.13309).
Reviewed main commit: `f9b1937bd909b33c0705c7deaa137adca54b5fe0`.

<a id="environmental-rf-references"></a>

## Published precedents for environmental RF and terrain I/Q simulation



This review compares published implementations with airsim-rf's environmental
propagation and terrain demonstrations. Sources were inspected on **2026-10-03**;
the implementation baseline is commit
`8026af51a2524d8ebc470968d7cbcac0d91d383f` and Sionna RT **2.2.0**.
Documentation pages, executable examples, technical reports and conference
presentations are identified separately below. A vendor demonstration establishes
that a workflow exists; it does not independently validate our implementation.

For the downstream waveform step, the **2026-10-05**
[channel-to-I/Q implementation review](references.md#iq-rendering-references) adds inspected
sample-processing code from Sionna PHY, GNU Radio, NVIDIA Sionna Research Kit,
ACHEM/CHEM and HermesPy, plus reduced-rank channel-emulation papers and the
SimART comparison. It documents fractional-delay and Doppler assumptions
separately from the environmental modeling in this review.

**The architecture has strong precedents.** MathWorks publishes site-specific
bistatic terrain clutter that produces I/Q. RadarSimPy publishes a moving
terrain radar-altimeter example with complex samples and an altitude waterfall.
Ansys documents STK plus a GPU RF plugin producing channel and radar data.
Remcom demonstrates environmental multipath, chirp processing and temporally
consistent diffuse scattering. These are close matches to different parts of
our project, rather than one implementation matching every requirement.

**Our demonstrated terrain-delay behavior has more support than our current
rough-ground clutter statistics.** Geometry, illumination and a channel-to-I/Q
pipeline are established approaches. Persistent scattering phase, calibrated
surface backscatter and convergence of coherent I/Q remain work for this
project. The sources do not establish our 100-TX/10-RX runtime or GPU sizing.

### What is being compared

The project has two relevant experiments:

* The [network terrain scenario](terrain.md#terrain-scenario) uses 100 independent
  transmitters and one receiver, first-order surface paths, a synthetic DEM,
  delay/Doppler diagnostics and a selected-link coherent LFM response.
* The [focused terrain scan](terrain.md#terrain-signature) moves one independent TX/RX
  pair, separated by 2 m, across the same DEM at 40 m datum altitude. Downward
  12-degree antennas and a 200 MHz LFM pulse reveal terrain relief in a
  pulse-compressed I/Q waterfall. This is a geometric demonstration, with noise
  disabled, rather than a claim of calibrated altimeter performance.

Both use the general TX–surface–RX channel. The receiver is not restricted to
monostatic radar, and no reciprocal channel is squared to manufacture a return.
The intended deployment is a general RF simulation plane for radar, ESM and
communications, with AirSim scene truth and one GPU worker per receiver.

| Published implementation | Closest correspondence | Output actually documented | Important difference |
| --- | --- | --- | --- |
| MathWorks site-specific bistatic land clutter [1](#ref1) | Independent moving TX/RX, elevation data, illuminated terrain patches, waveform processing | Clutter I/Q and bistatic range-Doppler maps | Empirical land reflectivity and random patch coefficients; not our Lambertian material model |
| MathWorks radar scenario clutter [2](#ref2) | Terrain, antenna footprint and terrain masking | Signal-level clutter, range profiles and range-Doppler products | The illustrated surface configuration has multipath disabled |
| MathWorks ray-traced communications [4](#ref4), [5](#ref5) | Independent one-way complex channel applied to a waveform | Filtered complex baseband samples from propagation rays | Its documented ray tracer excludes diffuse scattering |
| Ansys STK / RF Channel Modeler / Perceive EM [6](#ref6), [7](#ref7) | Main scene/motion simulator plus GPU RF engine | Channel coupling data; overview describes raw receiver I/Q and range-Doppler | Commercial SBR/physical-optics engine; no matching scale benchmark established here |
| Ansys PyAEDT HFSS SBR+ Doppler example [8](#ref8) | Programmatically assembled moving scene and radar | FRTM results and range-Doppler post-processing | Public setup code requires a licensed solver; solve invocation is commented out |
| Remcom WaveFarer [9](#ref9), [10](#ref10) | Scene multipath and diffuse environmental clutter feeding waveform processing | Complex impulse response, received voltage, I/Q and range-Doppler | More detailed scattering treatment; explicitly maintains relative diffuse phase through motion |
| NVIDIA Sionna RT [11](#ref11), [12](#ref12) | Our underlying antenna/material/polarization/channel machinery | Complex path coefficients, delays, Doppler and sampled baseband channel taps | General radio propagation; our candidate sampler and ground model still need their own validation |
| RadarSimPy terrain altimeter [13](#ref13), [14](#ref14) | Moving downward beam, terrain mesh, I/Q, matched filtering and terrain waterfall | Complex baseband plus noise and extracted altitude | Monostatic 10 GHz short-pulse radar; physical-optics mesh backend rather than our first-order diffuse channel |
| RadarSimPy ground multipath [16](#ref16) | Both TX-side and RX-side environmental routes affecting coherent signal | FMCW complex samples and interference amplitude curves | Includes target-plus-ground routes beyond our accepted one-surface-interaction limit |
| RaySAR [17](#ref17), [18](#ref18) | 3D scene geometry and interpretation of multiple reflections | SAR image layers and phase-center locations | The paper explicitly excludes raw-data simulation and processing |

### MathWorks: terrain clutter all the way to I/Q

#### Site-specific bistatic land clutter

The closest MathWorks example is **“Bistatic Clutter Part 3: Simulating
Site-Specific Bistatic Land Clutter”**, marked **Since R2026b** [1](#ref1). It is a
published MATLAB live-script example, not just a product feature description.
It requires Radar Toolbox, Mapping Toolbox and Parallel Computing Toolbox.

The example places a bistatic radar scene in East Fortune, Scotland. It imports
digital elevation data through `wmsfind`/`wmsread`, converts orthometric heights
to WGS84 ellipsoidal heights, creates a `landSurface`, and defines moving
transmitter and receiver platforms. Its waveform is LFM, with approximately
1.5 MHz bandwidth and a 128-pulse coherent processing interval (CPI) [1](#ref1).

Its terrain return is built from clutter patches. For each patch, the code
calculates incident and scattering grazing angles and the out-of-plane bistatic
angle. `bistaticSurfaceReflectivityLand` supplies normalized bistatic RCS; the
example uses the **Domville / Rural** in-plane model and **RuralInterpolation**
out-of-plane model. Multiplying normalized RCS by patch area gives patch RCS,
which is converted to a reflection coefficient [1](#ref1).

The published implementation then adds a Rayleigh-distributed amplitude factor
and a uniformly distributed random phase. It stores those reflection
coefficients and assumes they remain constant for the CPI. For every pulse it
recomputes propagation paths, instantaneous bistatic range and Doppler, applies
the stored coefficients, transmits the pulse and accumulates received I/Q.
Patches are batched with `parfor`. Finally it performs matched filtering and
Doppler processing [1](#ref1).

This is a direct precedent for **terrain surface contributions → delayed,
phase-bearing waveform copies → received I/Q → range-Doppler processing**.
Computing geometry once per pulse is explicit in the example. It also shows
why both transmit and receive antenna illumination matter.

The physics differs from ours. MathWorks uses land-reflectivity/RCS models,
while our current DEM has one uniform dielectric/conductive material and a
Lambertian diffuse pattern. Its persistent patch coefficients provide a
slow-time coherence assumption that our moving angular proposals do not yet
provide. The example is terrain clutter synthesis; it should not be described
as a full arbitrary-scene electromagnetic multiple-bounce solver.

The example cites **Maitland et al., “Development of a Bistatic Clutter Tool and
Validation by Experimental Data”** [19](#ref19). This is a useful measurement-validation
lead. The bibliographic record and presentation landing page were located, but
the full paper and recorded talk were access restricted during this review.
No measured error numbers from that work are claimed here.

#### Older radar terrain examples and a compact clutter channel

**“Introduction to Radar Scenario Clutter Simulation”**, available since
R2022a [2](#ref2), provides a more widely available starting point. It demonstrates
monostatic clutter using `radarTransceiver`, flat land and DTED terrain, range
profiles, range-Doppler processing and the effect of terrain shadowing.
Large continuous surfaces are approximated by point scatterers, with uniform
or resolution-cell-based placement modes described in the example.

The printed `SurfaceManager` configuration is `EnableMultipath: 0` and
`UseOcclusion: 1` [2](#ref2). That distinction matters: terrain backscatter and terrain
masking do not imply that higher-order environmental propagation is active.
The example also suggests using a custom antenna pattern to accelerate a
summed-beam simulation. This supports separating a beam model from explicit
element-level array simulation, without validating our particular pattern.

**“Bistatic Clutter Part 1: Rapidly Generate Clutter Channel FIR and I/Q Radar
Data”** [3](#ref3) builds a compact approximation with `bistaticClutterSurfaceFIR` and
applies it to a waveform. It is an especially useful reference for separating
channel computation from signal processing. Its stated role is fast
exploration before higher-fidelity simulation or measured-data analysis.
It is not a replacement for site-specific visibility or geometry.

#### MATLAB communications ray tracing is another relevant precedent

`comm.RayTracingChannel` filters an input waveform through a multipath channel
defined by propagation rays [4](#ref4). Its rays carry path delay, loss and phase;
the object supports antenna configurations and a receive-velocity Doppler
model. This resembles our general one-way channel-to-waveform interface and
is relevant to communications and ESM, not just radar.

There are two consequential differences. First, MathWorks' ray-tracing overview
explicitly says its communications ray tracer supports LoS, reflections and
edge diffraction, but **does not currently support diffuse scattering,
refraction, or corner/vertex diffraction** [5](#ref5). The land-clutter example and
the communications ray tracer are therefore distinct modeling tools. Second,
`comm.RayTracingChannel` documents default impulse-response/output
normalization [4](#ref4). A comparison of absolute received voltage must align these
settings with our unnormalized gains and absolute path delays; matching plots
after independent normalization is insufficient.

### Ansys: a scene simulator with an RF simulation plugin

#### STK and Perceive EM closely resemble our intended division of work

The **RF Channel Modeler Plugin Overview** [6](#ref6) describes a concrete workflow:
create an STK scene, import regional 3D tilesets, specify materials, create
vehicles/aircraft and sensors, import antenna patterns, configure transceivers,
and run the RF analysis. Perceive EM supplies the GPU-accelerated shooting and
bouncing rays (SBR) engine. The overview explicitly describes frame-by-frame
range-Doppler data or raw receiver I/Q in a geospatial environment.

The plugin's documented output includes an HDF5 file of antenna-to-antenna
scattering-parameter coupling data. A plugin license also grants Perceive EM
API access, including standalone execution [6](#ref6). This makes the architecture
comparison quite specific:

| Ansys responsibility | Corresponding intended airsim-rf responsibility |
| --- | --- |
| STK supplies environment, platforms and motion | ProjectAirSim supplies scene truth, antenna poses and simulation clock |
| Perceive EM evaluates RF propagation and coupling | Sionna RT plus our solver adapter evaluates the RF channel |
| RF API connects analysis and signal workflows | Receiver workers expose RF channel/I/Q services to the AMS-GRA simulation plane |
| Imported geometry, materials and antenna patterns define RF scene | Explicit Mitsuba RF meshes, RF material assignments and antenna patterns |

The analogy supports the separation of responsibilities. It does not establish
that our AirSim mesh/material synchronization is complete, that our scheduler
has the same capabilities, or that commercial solver performance transfers.
Visual geometry still needs an explicit RF representation in our project.

Peter Douglass' public **NDIA 2024 presentation**, “Modeling Dynamic Wireless
Channels in Interactive Terrestrial Environments” [7](#ref7), makes the general RF
intent unusually clear. Slide 7 lists communications, EW/SigInt, moving arrays,
radar, I/Q on demand, and C++/Python APIs. Slide 8 diagrams a frequency sweep,
complex frequency response, IFFT, complex impulse response and a tapped-delay
model producing I/Q voltage samples. The model spans channel and waveform
simulation rather than assuming every receiver is a monostatic radar.

That presentation calls Perceive EM an SBR–physical-optics solver and describes
operation at or near real time on GPUs [7](#ref7). These are vendor claims for that
engine. The presentation does not establish our exact combination of 100 TX,
10 RX, path budget, 200 Hz pulse updates and scene complexity. In particular,
it does not substantiate one GPU per receiver as a minimum hardware requirement.

#### Public Python scene and Doppler example

The PyAEDT **“Doppler setup”** example [8](#ref8) constructs an HFSS SBR+ environment,
places actors and a radar, creates a pulse-Doppler setup and demonstrates FRTM
result loading and range-Doppler post-processing. It is public Python code for
a moving-scene workflow backed by a commercial electromagnetic solver.

The example explicitly instructs the reader to uncomment `app.analyze_setup`
to solve. Its public setup and post-processing code should not be mistaken for
a freely executable, self-contained RF backend. It is still a useful template
for scenario assembly and exporting complex results for signal processing.

### Remcom: environmental multipath and phase-consistent diffuse clutter

WaveFarer's diffuse-scattering documentation [9](#ref9) directly addresses rough
surfaces that are insufficiently represented by the geometric mesh. Surface
variations rough relative to wavelength, but smaller than the mesh features,
add clutter and can increase cross-polarization. The documented model includes
illumination, blockage, scattering directions and relative phase. The page
shows comparisons of complex impulse responses and range-Doppler products
with and without rough-road scattering.

One statement is particularly relevant to moving platforms: even though
diffuse phase is random, **relative phases must remain consistent from time
step to time step**. The page explicitly states that its implementation
maintains that consistency so results can be processed into I/Q and
range-Doppler products [9](#ref9). This is a concrete requirement our common-random-seed
sampling alone does not satisfy.

The public **COMCAS 2019 presentation** by Skidmore, Chawla and Bedrosian [10](#ref10)
provides an implementation description beyond a product page. It combines
physical optics, method of equivalent currents and GO/UTD propagation for
automotive environments. Example clutter comes from ground, guard rails,
street signs and other structures. Its processing workflow derives a received
voltage waveform from a complex impulse response and the transmitted chirp,
then mixes and Fourier-transforms the signal for range and Doppler.

The presentation makes its assumptions explicit: interactions are treated as
nondispersive in that study and a chirp simulation uses a static snapshot
because object speeds are small compared with light speed [10](#ref10). This is close
to our compact-channel waveform synthesis, though it does not establish that
all implementations use exactly our narrowband Doppler approximation.

WaveFarer's detailed target-scattering and near-field treatment should not be
equated with our dielectric slab plus angular diffuse pattern. The strongest
lessons for our project are the workflow, controlled scattering-on/off
comparisons, and preservation of phase through scene motion.

### NVIDIA Sionna RT: the basis of our complex environmental channel

The **Sionna RT Technical Report**, arXiv:2504.21719 [11](#ref11), documents the actual
underlying channel machinery. Version 3 was published on 2026-09-03. It
describes scene meshes and radio materials, SBR candidate discovery, image
method processing, antenna/polarization effects, path coefficients and delays,
Doppler, and diffuse reflection. Sections 3.3 and A.6–A.8 are particularly
relevant to interpreting our I/Q.

The report's baseband impulse response has the form
`h_b(tau) = sum_p a_p^b delta(tau - tau_p)` [11](#ref11). Our receiver applies that
channel to an arbitrary waveform and scales it into RMS complex voltage:

```text
v(t) = sqrt(R * Ptx) * sum_p a_p^b * exp(j*2*pi*fd_p*Delta_t)
                                    * x(t - tau_p) + noise(t)
```

Here `Delta_t` is time since the current channel epoch; carrier phase is already
in `a_p^b`. Geometry and envelope delays are held fixed within a pulse, while
carrier Doppler evolves analytically. Repeating the path solve at pulse epochs
updates geometry. This is the accepted narrowband Doppler approximation,
not a wideband time-scaling model. The report also states that path coefficients
are evaluated at the carrier and assumed constant across simulated bandwidth
[11](#ref11); a 200 MHz chirp does not make material response frequency dependent.

NVIDIA's **“Tutorial on Scattering”**, inspected in the Sionna 2.2.0 docs [12](#ref12),
is an executable example of diffuse reflection influencing RF data. It changes
the scattering coefficient and angular pattern, compares ray-traced summed
path power to an analytical far-wall approximation, and compares baseband
channel taps with and without scattering at 200 MHz sampling bandwidth.
Lambertian and directive patterns distribute reflected energy differently.

This directly supports using triangles, radio materials, angular scattering
and complex channels. It does not supply a measured soil/LULC model or prove
our terrain I/Q statistics. Its analytical power comparison evaluates
`sum(abs(a_p)**2)`, whereas our waveform receiver evaluates a coherent sum.
Those are different observables: coherent I/Q includes cross terms.

The technical report also includes independent random diffuse polarization phases
in its mathematical treatment [11](#ref11), Appendix A.8. That is not evidence that
our configured material has persistent random ground phases. Our default
diffuse operator and sampling behavior are documented in
[GROUND_SCATTERING.md](terrain.md#ground-scattering).

Our first-order adapter replaces native candidate discovery with exhaustive
specular candidates and **1,028 attempted diffuse samples per TX/RX link**.
Half the proposals originate at TX and half at RX, each with antenna gain
importance sampling and uniform support. Native Sionna still evaluates
material response, fields, polarization, path delay and endpoint Doppler.
The public native tutorial is a reference for these shared components, not a
validation of our modified sampler. In particular, preserving ray-tube power
normalization is not sufficient proof of coherent-I/Q convergence.

### RadarSimPy: a remarkably close terrain visualization

#### Published radar-altimeter notebook

**“Pulse Radar Altimeter”**, published on 2025-11-21 and inspected in its updated
form [13](#ref13), links to public notebook code [14](#ref14). It reports RadarSimPy 15.2.0 and
models a Grand Canyon STL terrain mesh with **relative permittivity 5**. A
downward beam moves across the terrain and the simulator produces complex
baseband samples plus receiver noise. Matched filtering then produces an
altitude profile heatmap along the flight path.

The resemblance to our focused scan is substantial:

| Feature | Published RadarSimPy example [13](#ref13) | Our focused scan |
| --- | --- | --- |
| Surface | Grand Canyon STL; soil permittivity 5 | Synthetic hills/swale DEM; permittivity 5 plus conductivity and diffuse settings |
| Motion | 200 m/s over a 30 km track | 10 m/s over approximately 180 m |
| Geometry | Monostatic, approximately 4,000 m altitude | Independent TX/RX, 2 m baseline, z=40 m datum altitude |
| Beam | Nadir, 20 dBi, cosine-tapered antenna patterns | Nadir, synthetic 12-degree pattern, approximately 24 dBi peak |
| Waveform | 10 GHz carrier, 333 ns short pulse, approximately 3 MHz bandwidth | 24.125 GHz carrier, 2 microsecond LFM, 200 MHz bandwidth |
| Receiver data | Complex baseband plus noise; 150 frames | Raw complex voltage; 91 selected pulse epochs; no noise |
| Processing | Matched filter and altitude waterfall | LFM matched filter, total-path waterfall and equivalent height |

The published radar uses a 1 MW peak-power illustrative profile [13](#ref13). Neither
that profile nor our synthetic terrain scan should be confused with the
project's separate inexpensive Distance2GoL hardware profile.

The correspondence is the **measurement principle**, not numerical equivalence
of the solvers. RadarSimPy's mesh backend is documented as ray tracing plus
physical optics [15](#ref15). Our terrain demo does not implement that PO surface
integral. Its notebook calls `sim_radar(..., density=0.05)`; that density is a
ray-density parameter, not a statement of 0.05 rays per link or evidence that
1,028 attempts are enough in our sampler.

Current RadarSimPy 15.4.0 documentation explicitly offers geometry retracing at
frame, pulse or ADC-sample level [15](#ref15). **Pulse-level tracing is an established
fidelity choice.** Between retraces, its documented range-rate extrapolation
also differs from our fixed envelope delays plus carrier Doppler. Matching
the update label alone does not make the motion models identical.

Public notebooks provide concrete examples to reproduce and compare. They do
not imply that every mesh-solver feature is freely available under every
distribution/license. Backend availability and licensing need separate checks
before incorporating RadarSimPy into the container or RF plane.

#### Environmental multipath example and our bounce limit

RadarSimPy's **“Multi-Path Effect”** example [16](#ref16) demonstrates a moving corner
reflector above a dielectric ground plane. It compares complex FMCW data and
processed amplitudes with and without the ground. It explicitly includes
ground reflection on the transmitter side, receiver side, and both sides,
in addition to the direct target return.

This addresses the concern that both ends of a link matter. It is also a useful
boundary case: TX–ground–target–RX and TX–target–ground–RX each have more than
one surface interaction. Our accepted first-order mode cannot represent those
paths. **A scene containing LoS plus many single-interaction paths has multipath,
but it does not have all multiple-bounce environmental paths.** Including the
target and ground together would require a deeper or specialized backend.

### RaySAR: useful scene interpretation, a different output level

Auer, Bamler and Reinartz's **“RaySAR — 3D SAR Simulator: Now Open Source”**
(IGARSS 2016) [18](#ref18) and the public repository [17](#ref17) show that scene-based ray
tracing for environmental radar signatures has a long history. RaySAR uses an
adapted POV-Ray and produces image layers and phase-center positions, including
different reflection orders and ghost-scatterer interpretations.

The paper explicitly says its image/phase-center products are provided
**without raw-data simulation and processing**. It also discusses simplified
reflection models, missing polarimetry and incomplete diffuse reflections [18](#ref18).
It is valuable for understanding how scene geometry and multiple reflections
manifest in radar images. It is not a ready replacement for the general I/Q
simulation plane.

### Environmental assumptions: what the precedents do and do not resolve

| Modeling issue | Evidence in the reviewed sources | Current project status |
| --- | --- | --- |
| Elevation geometry | MathWorks imports elevation/DTED; RadarSimPy imports a terrain STL [1](#ref1), [2](#ref2), [13](#ref13) | Synthetic 10 m grid, 800 triangles; no survey accuracy claim |
| RF materials | STK imports custom materials; Sionna separates geometry from radio materials; RadarSimPy altimeter assigns soil permittivity [6](#ref6), [11](#ref11), [13](#ref13) | One uniform material: relative permittivity 5, conductivity 0.01 S/m, slab thickness 0.5 m |
| Land-cover-dependent return | MathWorks explicitly uses a rural bistatic land-reflectivity model [1](#ref1) | No LULC importer, spatially varying backscatter map, moisture or vegetation-volume model |
| Sub-mesh roughness | WaveFarer describes wavelength-scale roughness; Sionna provides phenomenological diffuse patterns [9](#ref9), [11](#ref11), [12](#ref12) | Lambertian coefficient 0.3 is a synthetic setting, not calibrated roughness or measured sigma-zero |
| Magnetic response | Material assumptions must be chosen for a particular engine and application | Standard Sionna material model is nonmagnetic; no independently specified permeability map |
| Both antenna patterns | Bistatic clutter and general channel workflows include TX and RX antennas [1](#ref1), [4](#ref4), [6](#ref6), [11](#ref11) | Both fields evaluated; both gain patterns guide proposals; uniform support retains sidelobe directions |
| Phase through motion | MathWorks holds patch reflection coefficients through a CPI; WaveFarer preserves relative diffuse phase through time [1](#ref1), [9](#ref9) | No persistent world-fixed sampled scatterers or calibrated roughness correlation |
| Arbitrary environmental paths | SBR/PO and RaySAR references include richer reflection chains [7](#ref7), [10](#ref10), [18](#ref18) | First-order mode accepts at most one surface interaction; no diffraction/refraction in that adapter |
| General signal types | MATLAB communications channels, Sionna and Perceive EM separate channel from waveform [4](#ref4), [7](#ref7), [11](#ref11) | Generic SISO callable-waveform receiver exists; full many-transmitter waveform service remains integration work |
| Real-time scale | GPU engines and update-level tradeoffs are documented [7](#ref7), [11](#ref11), [15](#ref15) | CPU timings measured; target-GPU deadline and VRAM measurements still required |

Permittivity alone does not determine realistic terrain clutter. Surface
roughness, correlation length, incidence/scattering angle, polarization,
vegetation and moisture can change the return substantially. Conversely,
an empirical normalized-RCS model can encode observed land returns without
resolving every physical constituent. A future LULC model should specify which
properties each class supplies and how they are calibrated; a visual terrain
texture is not an RF material assignment.

The focused scan currently tests **how changing terrain geometry changes echo
delay**. Its raised-plane test moves the received compressed peak by the
expected bistatic path change, and its flat-ground and bandwidth controls show
why hills become resolvable. Its reported 0.35 m RMS difference against the
synthetic DEM is an internal demonstration metric, not measured sensor accuracy
or validation of clutter amplitudes and slow-time statistics.

### Validation work suggested by the published examples

These are proposed follow-ups, not tests already completed by this review.

1. **Build an independent terrain-delay comparison.** Match a small planar or
   ridge mesh, TX/RX poses and waveform in our scan and the RadarSimPy altimeter
   workflow [13](#ref13), [14](#ref14). Compare raw path delays and compressed peaks before
   comparing amplitudes. Align voltage conventions, bandwidth, antenna gain,
   noise and material settings. Different scattering engines need not produce
   identical amplitudes.
2. **Calibrate surface strength separately from geometry.** Reproduce Sionna's
   far-wall diffuse-power check [12](#ref12) with our sampler, then evaluate a
   characterized soil/land-return model over grazing/bistatic angle and
   polarization. MathWorks' rural bistatic model is an example of the latter
   approach [1](#ref1), not a universal reference for all land cover or frequencies.
3. **Add persistent surface scattering statistics.** Give surface patches or a
   world-fixed random field stable identity, phase and spatial correlation;
   define temporal evolution separately from proposal sampling. Demonstrate
   stable static-scene returns and physically consistent moving-platform
   slow-time phase, following the concerns documented in [1](#ref1), [9](#ref9).
4. **Test coherent I/Q convergence.** Sweep attempted paths and independent
   numerical seeds. Compare mean power, phase/statistics, compressed profiles,
   slow-time autocorrelation and Doppler spectra. A stable summed path-power
   diagnostic alone is insufficient. Numerical quadrature and physical
   speckle randomness must be distinguished.
5. **Make path-order coverage explicit.** Use LoS/ground, blocker and
   terrain-shadow controls for first-order operation. Use the target-plus-ground
   example [16](#ref16) as a documented case requiring additional interactions, rather
   than claiming that first-order operation supplies every environmental path.
6. **Benchmark the required RF service on deployment GPUs.** Measure 100 TX per
   receiver worker, the actual RF mesh and path budget, waveform synthesis,
   transport, synchronization, warm-up, deadline percentiles and VRAM. Report
   120 Hz scene-update and 200 Hz pulse requirements separately. Ansys' real-time
   statement and another solver's timing are not our measurements [7](#ref7).

The justified development direction is to retain the general scene/channel/I/Q
architecture while improving the environmental scattering model and independent
validation. The current code supports a useful geometric prototype. The reviewed
references do not justify labeling it a calibrated clutter simulator or a
proven real-time 100-TX/10-RX product.

### References and access notes

All web sources below were inspected or located on **2026-10-03**. Live vendor
documentation can change; versions and access limitations are noted where
relevant. No licensed vendor solver was run for this review.

<a id="ref1"></a>
**[1] MathWorks.** [Bistatic Clutter Part 3: Simulating Site-Specific Bistatic Land Clutter](https://www.mathworks.com/help/radar/ug/bistatic-clutter-part-3-simulating-site-specific-bistatic-land-clutter.html).
Radar Toolbox live-script documentation, marked Since R2026b. Full published
example inspected, including terrain import, rural reflectivity, random patch
coefficients, pulse loop and I/Q processing.

<a id="ref2"></a>
**[2] MathWorks.** [Introduction to Radar Scenario Clutter Simulation](https://www.mathworks.com/help/radar/ug/introduction-to-radar-scenario-clutter-simulation.html).
Radar Toolbox example, Since R2022a. Full example inspected; includes DTED,
shadowing, point-scatterer approximation and signal-level processing.

<a id="ref3"></a>
**[3] MathWorks.** [Bistatic Clutter Part 1: Rapidly Generate Clutter Channel FIR and I/Q Radar Data](https://www.mathworks.com/help/radar/ug/bistatic-clutter-part-1-rapidly-generate-clutter-channel-FIR-and-IQ-radar-data.html).
Published compact clutter-channel and waveform example; full page inspected.

<a id="ref4"></a>
**[4] MathWorks.** [comm.RayTracingChannel: Filter signal through multipath fading channel defined by propagation rays](https://www.mathworks.com/help/comm/ref/comm.raytracingchannel-system-object.html).
Communications Toolbox API documentation. Channel definition, waveform
filtering, receive-velocity and normalization properties inspected.

<a id="ref5"></a>
**[5] MathWorks.** [Ray Tracing for Wireless Communications](https://www.mathworks.com/help/comm/ug/ray-tracing-for-wireless-communications.html).
Propagation overview; supported interactions and explicit diffuse-scattering
limitation inspected.

<a id="ref6"></a>
**[6] Ansys.** [RF Channel Modeler Plugin Overview](https://help.agi.com/stk/Content/comm/RFCMOverview.htm).
STK help. Scene/material/antenna workflow, GPU engine, I/Q description,
HDF5 coupling output and API/licensing statements inspected.

<a id="ref7"></a>
**[7] Peter Douglass, Ansys.** [Modeling Dynamic Wireless Channels in Interactive Terrestrial Environments](https://ndia.dtic.mil/wp-content/uploads/2024/systems/Tue_PBMS_1861678_Douglass.pdf).
NDIA presentation, 2024-10-29. Full PDF inspected, especially slides 7–8 on
Perceive EM, general RF applications and channel-to-I/Q architecture.
Runtime language is a vendor claim.

<a id="ref8"></a>
**[8] Ansys / PyAEDT.** [Doppler setup](https://examples.aedt.docs.pyansys.com/version/dev/examples/high_frequency/antenna/large_scenarios/doppler.html).
Public Python HFSS SBR+ example, development documentation. Setup,
commented solve invocation and FRTM post-processing inspected.

<a id="ref9"></a>
**[9] Remcom.** [Diffuse Scattering — WaveFarer Radar Sensing Simulation Software](https://www.remcom.com/wavefarer-radar-sensing-simulation-software/diffuse-scattering).
Vendor technical feature page. Roughness, blockage, complex impulse response,
time-consistent relative phase and I/Q post-processing statements inspected.

<a id="ref10"></a>
**[10] Gregory Skidmore, Tarun Chawla and Gary Bedrosian, Remcom.**
[Combining Physical Optics and Method of Equivalent Currents to Create Unique Near-Field Propagation and Scattering Technique for Automotive Radar Applications](https://resources.remcom.com/hubfs/Blog%20Images/Remcom_WaveFarer_Chirp_Doppler_for_Drive_Scenarios_COMCAS2019.pdf).
IEEE COMCAS presentation, Tel Aviv, 2019-11-04–06. Full PDF inspected;
includes environmental clutter, CIR-to-voltage synthesis, MATLAB chirp
post-processing and stated snapshot/nondispersion assumptions.

<a id="ref11"></a>
**[11] Fayçal Aït Aoudia, Jakob Hoydis, Merlin Nimier-David, Baptiste Nicolet,
Sebastian Cammerer and Alexander Keller.**
[Sionna RT: Technical Report](https://arxiv.org/abs/2504.21719), arXiv:2504.21719,
first submitted 2025-04-30; [version 3 full text](https://arxiv.org/html/2504.21719v3),
2026-09-03. DOI: [10.48550/arXiv.2504.21719](https://doi.org/10.48550/arXiv.2504.21719).
Full text inspected, including path solver, Doppler and electromagnetic appendix.

<a id="ref12"></a>
**[12] NVIDIA.** [Tutorial on Scattering](https://nvlabs.github.io/sionna/rt/tutorials/Scattering.html).
Sionna 2.2.0 documentation. Full example inspected; includes angular patterns,
analytical far-wall power comparison and 200 MHz complex channel taps.

<a id="ref13"></a>
**[13] RadarSimX.** [Pulse Radar Altimeter](https://radarsimx.com/2025/11/21/pulse-radar-altimeter-altitude/).
Published 2025-11-21; page displays update 2026-03-10 and notebook runtime
version 15.2.0. Full example/code/output inspected, including Grand Canyon
mesh, permittivity, complex samples, noise and matched-filter waterfall.

<a id="ref14"></a>
**[14] RadarSimX.** [scene_pulse_radar_altimeter.ipynb](https://github.com/radarsimx/radarsimnb/blob/master/notebooks/scene_pulse_radar_altimeter.ipynb).
Public notebook in the [radarsimnb repository](https://github.com/radarsimx/radarsimnb).
Notebook location verified through repository tree; executable code also
inspected in the rendered example [13].

<a id="ref15"></a>
**[15] RadarSimPy.** [Ray-Tracing Simulation](https://radarsimx.github.io/radarsimpy/user_guide/ray_tracing_simulation.html).
Version 15.4.0 documentation. Physical-optics description, density parameter,
frame/pulse/sample retracing and inter-pass motion approximation inspected.

<a id="ref16"></a>
**[16] RadarSimX.** [Multi-Path Effect](https://radarsimx.com/2021/05/10/multi-path-effect/).
Original publication 2021-05-10; inspected updated page reports RadarSimPy
15.2.0. Full example inspected, including TX-side/RX-side ground routes,
dielectric ground, baseband processing and with/without-ground comparison.

<a id="ref17"></a>
**[17] Stefan J. Auer.** [RaySAR public repository](https://github.com/StefanJAuer/RaySAR).
Repository overview inspected; adapted POV-Ray and SAR geometry/image products.

<a id="ref18"></a>
**[18] Stefan Auer, Richard Bamler and Peter Reinartz.**
[RaySAR — 3D SAR Simulator: Now Open Source](https://elib.dlr.de/104370/).
IGARSS 2016, pp. 6730–6733.
[Open paper PDF](https://elib.dlr.de/104370/1/Auer_Bamler_Reinartz_RaySAR_open_source.pdf).
Full paper inspected, including output level and diffuse/polarimetric limitations.

<a id="ref19"></a>
**[19] C. Maitland, D. Mountford, B. Hopson, A. Glass, J. Patel, E. Rose,
P. Durham and P. McGinley.**
[Development of a Bistatic Clutter Tool and Validation by Experimental Data](https://doi.org/10.1049/icp.2022.2303).
IET Conference Proceedings 2022(17), pp. 125–129; publication cited by [1].
[IET presentation landing page](https://tv.theiet.org/video/development-of-a-bistatic-clutter-tool-and-validation-by-experimental-data/07b4b670-2388-4a6e-be83-79dc51742cfb).
Bibliographic/search record and talk landing page located; full paper and
recording access restricted. Included as a validation lead, not as an independently
reviewed experimental result.

