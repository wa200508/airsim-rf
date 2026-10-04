# A practical route to continuous 120 Hz RF simulation

Research date: 2026-10-04. Target supplied by the user: approximately **$5,000
for total compute**, 100 transmitters, 10 receivers, continuous ESM/comms I/Q,
moving platforms, and first-order environmental multipath. The initial sample
rate is **2 MS/s per radio**, with the existing approximately 1 MHz receive
bandwidth. No GPU result or complete 120 Hz demonstration is claimed here.

## Required scope: do not optimize by simplifying the scenario

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
See [the independent-transmitter experiments and next steps](INDEPENDENT_TX_OPTIMIZATION.md).

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

## Correct the workload before choosing hardware

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

## Case-specific channel measurements: not a sizing basis

[The channel-support inspection](research_results/affordable_realtime/channel_support.json)
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

## Alternative representation study: accuracy evidence, not the selected baseline

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

### Arbitrary-waveform numerical check performed here

[The exploratory validation](research_results/affordable_realtime/ltv_validation.json)
uses one actual link with 399 rays. The input is a randomly generated complex
sample block bandlimited to +/-480 kHz, lasting 8.3335 ms at 2 MS/s. A periodic
DFT representation permits an ideal fractional-delay reference for every ray.
The reference includes each ray's independent Doppler at every sample.

A windowed-sinc channel using 18 filter coefficients and cubic temporal
interpolation produced **-92.45 dB normalized mean-square error**, or about
**0.00239% RMS error**, for a 0.5 ms knot spacing. Increasing interpolation
support gave -94.52 dB for 34 coefficients and -99.28 dB for 66 coefficients.
These are waveform accuracy measurements, not general fidelity guarantees.

A [synthetic Doppler stress](research_results/affordable_realtime/ltv_stress.json)
multiplies these same rays' Dopplers by 40, reaching 485 Hz. With 18 coefficients,
0.125 ms temporal knots retained approximately -92.44 dB NMSE; 0.5 ms knots
fell to -56.39 dB. This demonstrates why temporal resolution must adapt to
Doppler, rather than assuming one fixed update interval is sufficient.

The experiment uses FP64 NumPy, one link and a periodic waveform. It materializes
sample-expanded coefficients for convenient validation and is not a proposed
production memory layout. Its individual timings include initialization effects;
it is not a 1,000-link throughput benchmark. Production needs fused coefficient
reconstruction, overlap/history, stateful clocks and receiver filters.

## Investigated solution families

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

### Concrete open implementations and publications

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

## Hardware portability and a $5,000 deployment

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

## A concrete implementation and qualification sequence

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

## Reproduce the research experiments

No new package dependencies are required beyond the existing bootstrap:

```bash
.venv/bin/python benchmarks/analyze_channel_support.py
OPENBLAS_NUM_THREADS=2 .venv/bin/python benchmarks/validate_compact_channel.py
# Synthetic higher-Doppler stress, preserving the same delays/gains:
OPENBLAS_NUM_THREADS=2 .venv/bin/python benchmarks/validate_compact_channel.py \
  --doppler-scale 40 --knot-ms .125 .25 .5 --output-name ltv_stress.json
```

The first script writes measured channel JSON and a local NPZ containing paths;
the second writes accuracy JSON. The NPZ is ignored by git. The scripts are
research experiments, not a new production channel renderer, GPU profiling
suite or real-time acceptance test. Stored CPU timings are individual
experiment timings, with initialization effects, and must not be extrapolated
to a 1,000-link deployment.
