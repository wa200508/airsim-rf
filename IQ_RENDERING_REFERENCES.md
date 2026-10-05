# Published implementations of channel-to-I/Q rendering

Sources and implementation paths reviewed on **2026-10-05**. This review
complements the [environmental RF comparison](ENVIRONMENTAL_RF_REFERENCES.md)
and [affordable real-time architecture study](AFFORDABLE_REALTIME_RF.md).
It distinguishes actual sample processing from channel generation, link
performance estimation and visualization. The external implementations were
inspected; they were not benchmarked locally against our workload.

## The operation and the workload

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

## Comparison

| Implementation | Actual output / computation | Delay and temporal treatment | Relevance and qualification limit |
| --- | --- | --- | --- |
| Sionna PHY [1](#ref1), [2](#ref2) | Complex output samples from supplied complex input samples | Sinc conversion from physical delays; time-varying taps can change every sample | Strong correctness baseline; dense sample-by-delay channel tensors can be large |
| GNU Radio [3](#ref3) | Streaming complex samples through a fading filter | Sinc fractional-delay weights; fading coefficients rebuilt per output sample | Real streaming precedent; statistical faders and nested CPU loops are not our scene-based scaling result |
| NVIDIA Sionna Research Kit [4](#ref4) | CUDA filtering of live I/Q in circular buffers | Integer delay indices; CIR constant within each OFDM symbol | Useful CUDA/buffering reference; SISO and symbol-static channel assumptions differ from our target |
| ACHEM/CHEM [5](#ref5), [6](#ref6) | SDR-facing I/Q processing, resampling, filtering and impairments | Sionna adapter rounds delays and caps tap support; inspected Doppler stage is a common link frequency shift | Useful service and SDR integration architecture; does not establish individual-path Doppler fidelity |
| HermesPy multipath fading [7](#ref7) | Delayed, weighted complex sample copies summed into a receiver signal | Inspected fading implementation rounds delays and generates sample-varying fading | Transparent sample-level reference; not a qualified GPU solution for our path budget |
| Reduced-rank channel-emulation research [8](#ref8), [9](#ref9) | Arbitrary complex input filtered through a reconstructed time-varying channel | Controlled delay/Doppler subspace approximation | Closest architectural precedent for our basis renderer; projection still depends on physical path count |
| SimART [10](#ref10) | Channels, beam evaluation, link metrics and ROS observations | Complex CFR evaluated at subcarrier frequencies and symbol timestamps | Scene/integration complement; inspected main runner does not generate continuous receiver I/Q |

## Sionna PHY: physical paths to sampled filtering

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

## GNU Radio: per-sample streaming evolution

In `selective_fading_model_impl.cc`, `work()` first generates fading sequences.
For every output sample it clears the filter taps, adds each fading component
using sinc weights for its fractional delay, then multiplies the filter by input
history and sums the result [3](#ref3).

The complex stream can contain arbitrary modulation. The standard coefficients
come from statistical fading processes, rather than our environmental ray
paths. This is evidence that time-varying filtering preserves sample-level
evolution, not evidence that its path-by-tap-by-sample loops meet our deadline.

## NVIDIA Sionna Research Kit: real CUDA channel emulation

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

## ACHEM/CHEM: SDR-facing service architecture

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

## HermesPy: explicit delayed sample copies

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

## Reduced-rank literature and our projection bottleneck

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

Our [Doppler-basis FFT renderer](DOPPLER_BASIS_FFT.md) uses a Chebyshev temporal
expansion and finite fractional-delay weights, rather than their DPS
construction. It applies each temporal filter to private sampled inputs and
recombines the filtered outputs with sample-varying basis functions. The
Jacobi–Anger identities and error bound in that document have their own
attribution; they are not quoted from these papers.

The P100 [projection investigation](results/profiling/p100-basis-investigation-20261004/REPORT.md)
shows why projection remains important: the default 100-TX/one-RX case performs
750,028,800 weighted complex contributions per window. A separate instrumented
capture measured approximately 67.52 ms around projection kernel calls. This
is not a pure Nsight instruction measurement or the unprofiled wall latency.
The original full renderer's median was 122.67 ms and its timestamp correctness
qualification failed. Subsequent
[qualified optimization results](results/profiling/p100-basis-optimized-full-20261004/FINDINGS.md)
fix that phase bug and report 56.167 ms median with 76 CUDA correctness tests
passing, using warp-cooperative projection and 100 links per batch. The
remaining mean renderer gap to 120 Hz is about 6.80 times. The original
projection timing above belongs to the earlier gather kernel, not the new
configuration. Neither the cited papers nor a faster isolated projector
establishes complete 120 Hz service.

The [published projection comparisons](results/profiling/p100-basis-optimization-20261004/README.md)
now include gather, warp-cooperative and dense matrix implementations. Further
work on reusable delay maps, sparse/tiled or matrix-based projection must
preserve every path and the selected tolerance, and compare with the qualified
warp implementation rather than assume a matrix formulation is faster.
A delay/frequency subspace is another research candidate, whose rank and error
must be qualified against the declared bounds. Published short-delay or
lower-precision results cannot replace that qualification.

## SimART: channels and metrics, not an I/Q renderer

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

## Sources and inspected code

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
[2019 Hofer et al. paper already discussed](AFFORDABLE_REALTIME_RF.md).

<a id="ref10"></a>
**[10] SimART.** [Repository](https://github.com/guchuanv-alt/SimART),
[main simulation runner](https://github.com/guchuanv-alt/SimART/blob/main/SimART_GUI/scripts/sionna_sim_only_topic2.py),
[RF path message](https://github.com/guchuanv-alt/SimART/blob/main/rf_msgs/msg/RfPathObservation.msg),
[Yan et al., *SimART: A Unified and Open Real-world Multimodal Simulation Platform for 6G Integrated Sensing and Communication*, arXiv:2605.13309 (2026)](https://arxiv.org/abs/2605.13309).
Reviewed main commit: `f9b1937bd909b33c0705c7deaa137adca54b5fe0`.
