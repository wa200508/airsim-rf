# Archived rendering notes — snapshot 9 October 2026

This is a dated research/recipe record, not current installation or product status.
Completed roadmap steps and old environment limitations retain their historical context.
Use [the maintained guide](../rendering.md) first.

# Rendering

- [Doppler Basis Fft](#doppler-basis-fft)
- [Direct Path Rendering](#direct-path-rendering)
- [Batched Rendering](#batched-rendering)
- [Independent Tx Optimization](#independent-tx-optimization)

<a id="doppler-basis-fft"></a>

## Change the rendering architecture: all-path Doppler basis and FFTs



**Runtime context (2026-10-05):** The 22× figure below compares two CPU algorithms on an earlier host and small link counts. It is not a real-time ratio or fleet speedup. Qualified P100 results are now available separately. See [current runtime and wall-clock costs](../archive/runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

The batched direct renderer is useful as a reference, but its dominant work
still scales with physical paths times output samples times interpolation
support. A 10–15% capture improvement does not resolve the target workload.
The next candidate changes the channel representation and rendering algorithm.

The new, opt-in CPU research implementation is
[`DopplerBasisRenderer`](../../src/airsim_rf/research/doppler_basis.py), with a
[matched benchmark](../../benchmarks/benchmark_doppler_basis.py). It is separate from
the receiver backends. It demonstrates approximately **22 times faster
sampled-I/Q rendering** for the declared synthetic workload below. It does
not demonstrate complete 120 Hz service or the $5,000 target. This initial CPU
experiment predates the [qualified P100 renderer collection](../archive/runtime.md#runtime-status).

### Physical model retained

Under the already accepted narrowband Doppler model, a link is:

$$
y[n]=\sum_{p=1}^{P}a_p\,
e^{\,j2\pi f_{D,p}(t_n-t_0)}\,
\widetilde{x}(t_n-\tau_p),
\qquad t_n=t_{\mathrm{start}}+\frac{n}{f_s}.
$$

Here, $a_p$ is the complex path gain, $\tau_p$ its delay, $f_{D,p}$ its
Doppler frequency, $t_0$ the channel epoch, and $\widetilde{x}$ the reconstructed
private input waveform. This is the project's implemented model, with its
narrowband approximation and finite interpolation made explicit; see the
[direct reference implementation](../../src/airsim_rf/batched_rendering.py).

Every supplied path enters the new channel. Its fractional delay and its own
Doppler remain. Equal-delay paths with different Dopplers still beat and can
cancel. No Doppler averaging, dominant path selection, reduced output rate
or reduced scene updates are used.

For a block with centre $t_c$ and duration $\Delta t$, define

$$
u_n=\frac{2(t_n-t_c)}{\Delta t}\in[-1,1],
\qquad z_p=\pi f_{D,p}\Delta t.
$$

The [Jacobi–Anger identities, NIST DLMF Eq. 10.12.3](https://dlmf.nist.gov/10.12#E3),
combined with the [Chebyshev identity $T_q(\cos\theta)=\cos(q\theta)$,
DLMF Eq. 18.5.1](https://dlmf.nist.gov/18.5#E1), give

$$
e^{jzu}=J_0(z)+2\sum_{q=1}^{\infty}j^qJ_q(z)\,T_q(u).
$$

$J_q$ is a Bessel function and $T_q$ a Chebyshev polynomial. Truncate this
temporal expansion at a degree chosen from the declared maximum Doppler,
block duration and error tolerance. There is no snapping Dopplers onto bins.
For each basis term, combine the delayed path weights into a filter:

$$
c_{q,p}=
\begin{cases}
J_0(z_p), & q=0,\\
2j^qJ_q(z_p), & q\geq1.
\end{cases}
$$

$$
H_q[k]=\sum_{p=1}^{P}w_{p,k}\,a_p\,
e^{\,j2\pi f_{D,p}(t_c-t_0)}\,c_{q,p}.
$$

$$
\widehat{y}[n]=\sum_{q=0}^{K}T_q(u_n)\,(H_q*x)[n],
\qquad
(H_q*x)[n]=\sum_k H_q[k]\,x[n-k].
$$

$w_{p,k}$ are the finite fractional-delay reconstruction weights and $K$ is
the retained temporal degree. These filter equations are this project's
derivation from the identity above. Overlap-save FFT filtering computes the
convolutions; it does not replace time-varying Doppler with a static channel.

Thus path projection precedes fast-time filtering. The waveform is arbitrary
sampled I/Q; its structure is not used to remove work. Each link performs its
own private input FFT. That FFT is used by that job's temporal basis filters;
no transmitter/receiver jobs share data or transforms. Oscillator offsets are
factored into a delay-dependent path phase and a per-job output phase, so they
do not inflate the physical Doppler basis.

This is a **time-varying convolution representation**, revisiting the family
discussed in [the architecture study](../archive/planning.md#affordable-realtime-rf). Its speedup
comes from representing the full time evolution within a controlled error,
not from freezing a tapped delay line between channel updates. Finite temporal
approximation is an explicit additional numerical assumption.

### Error and qualification bounds

The degree selection uses a conservative bound **derived here** from the
[Bessel power series, NIST DLMF Eq. 10.2.2](https://dlmf.nist.gov/10.2#E2).
Taking absolute values and using $(q+m)!\geq q!\,(q+1)^m$ gives

$$
|J_q(z)|\leq B_q(|z|),
\qquad
B_q(s)=\frac{(s/2)^q}{q!}
\exp\!\left(\frac{s^2}{4(q+1)}\right).
$$

Define $z_{\max}=\pi f_{D,\max}\Delta t$ and let $q=K+1$ be the first omitted
degree. For $q\geq\lceil z_{\max}\rceil$ and $q\geq1$, successive bounds decrease
at least geometrically, so the omitted temporal terms satisfy

$$
\sup_{\substack{|z|\leq z_{\max}\\|u|\leq1}}
\left|e^{jzu}-\sum_{\ell=0}^{K}c_\ell(z)T_\ell(u)\right|
\leq
\frac{2B_q(z_{\max})}
{1-\dfrac{z_{\max}}{2(q+1)}}
\leq\varepsilon.
$$

Here $c_0(z)=J_0(z)$ and $c_\ell(z)=2j^\ell J_\ell(z)$ for $\ell\geq1$.
The zero-Doppler case is exact with $K=0$. The geometric-tail step and its
degree-selection rule are our derivation, not a bound quoted verbatim from
DLMF or from Hofer et al.

The default dimensionless temporal tolerance is $\varepsilon=10^{-10}$.
The triangle inequality gives the corresponding absolute output error bound:

$$
|\widehat{y}[n]-y[n]|
\leq
\varepsilon\,\|x\|_\infty
\sum_{p=1}^{P}|a_p|\sum_k|w_{p,k}|.
$$

This bound remains applicable near coherent cancellation, where relative
output error alone can be misleading.

This bound covers temporal truncation. It excludes floating-point roundoff and
the finite input reconstruction's error relative to ideal infinite sinc.
Full-output agreement with the finite direct operator does not establish an
absolute receiver noise-floor guarantee. Those are separate acceptance checks.

Delay support is allocated from the declared maximum delay and interpolation
support, not inferred from this terrain's short paths. Inputs need sufficient
private history and lookahead. Overlap-save avoids circular wraparound and does
not require periodic data.

**Current research scope:** equal input/output sample clocks and aligned source
timestamps only. Nonunit rate scales and different input sample rates fail
explicitly. Independent oscillator frequencies and phases are supported.
Private clock resampling must be implemented and its composed reconstruction
error qualified before integration with the complete SDR receiver.

The fixed delay/gain/Doppler within a channel epoch is the existing propagation
model. Current paths must be projected again when the solver supplies new data.
The prototype rebuilds its interpolation map and temporal projection on every
render call; timing does not credit reusing a previously solved channel.

### CPU evidence with all valid paths

Two-core CPU quota, two FFT/Dr.Jit threads, complex128/FP64 throughout. Each
link has independent random complex input occupying 90% of the sample-rate
bandwidth, independent gains, continuous fractional delays uniformly spanning
0–100 microseconds, and independent Dopplers spanning +/-2,500 Hz. All **1,028
paths per link** are valid. Carrier offsets span +/-20 kHz. Output is 16,667
samples at 2 MS/s, approximately one 120 Hz interval. Both renderers coherently
sum their private link outputs. There is no terrain visibility attrition.

Five unprofiled captures follow two warmups. Measurement order alternates.
FFT timing includes rebuilding path-dependent state and includes every block's
projection, private source packing, FFTs, reconstruction and output summation.
Direct timing uses the batched renderer with 128-sample tiles and private
outputs. Both exclude source generation, propagation, clock resampling,
receiver noise/filter/ADC, AirSim and transport.

| Independent links | Direct median | Basis/FFT median | Speedup |
| --- | ---: | ---: | ---: |
| [1](../../research_results/doppler_basis_cpu/one_link.json) | 694.60 ms | 30.89 ms | 22.48 times |
| [4](../../research_results/doppler_basis_cpu/four_links.json) | 2,864.97 ms | 129.48 ms | 22.13 times |

Processing blocks contain 2,048 samples: 1.024 ms at 2 MS/s. The full blocks use
26 basis terms (degree 25), with 233 delay coefficients covering the declared
range and finite interpolation support. The final shorter block selects its
own degree using the same rule. Full-output comparison includes **all 1,028
paths and all 16,667 samples** of the first link. Normalized RMS disagreement
is approximately 2.12e-12; maximum absolute disagreement is approximately
5.13e-11. The conservative temporal-only absolute bound is approximately
3.22e-8 in these normalized signal units. First-use times and every timed
capture, source hashes and stage measurements are stored in the JSON files.

These are research medians, not qualified p95/p99 deadlines. Four links are not
the complete thousand-link workload. This is an algorithm comparison, not a
speedup of the 100-transmitter scene-to-ADC capture reported elsewhere.

#### Unfavorable ranges are measured too

These are one-link basis-only timings. All output samples are still checked
against all-path direct rendering, but direct timing was not collected:

| Changed qualification parameter | Basis median | Full-block degree | Delay coefficients |
| --- | ---: | ---: | ---: |
| [Delay bound 1,000 microseconds](../../research_results/doppler_basis_cpu/delay_1000us.json) | 46.13 ms | 25 | 2,033 |
| [Doppler bound +/-25,000 Hz](../../research_results/doppler_basis_cpu/doppler_25000.json) | 279.49 ms | 138 | 233 |
| [4,096 valid paths](../../research_results/doppler_basis_cpu/paths_4096.json) | 80.77 ms | 25 | 233 |

The high-Doppler case is substantially slower. Wider delays grow FFT support;
more paths increase projection work. No fixed cheap-rank claim is made for
all environments. Shorter processing blocks are another tunable tradeoff, but
they change projection/FFT overhead and must be measured at the same bounds.

### Scaling and latency

Let `P` be paths/link, `Q` input interpolation support, `N` output samples,
`B` processing block length, `R` temporal basis terms, `L` declared delay support,
and `F` the FFT size (at least `B+L-1`). Approximately `N/B` blocks are needed.

| Stage | Work per link/capture |
| --- | --- |
| Direct sampled rendering | O(P * N * Q) |
| Sparse interpolation map | O(P * Q) |
| Temporal coefficient setup | O(P * R) coefficient entries, with Bessel evaluation cost |
| All-path projection over blocks | O((N/B) * P * Q * R) |
| Private FFT filtering and basis reconstruction | O((N/B) * R * F * log(F) + N * R) |

The temporal degree grows with the Doppler-duration product and requested
accuracy. In the initial full blocks `B/R` is approximately 79. That is the
reduction in the projection work count relative to sample-by-sample path
evaluation, not a predicted overall speedup. Projection, Bessel evaluation,
FFTs, reconstruction and allocation explain the smaller measured 22-fold gain.

No path-by-sample contribution tensor or sample-expanded full channel is built.
Sparse path weights use O(P*Q) storage; temporary channel/FFT arrays scale with
R*L and R*F. The present implementation has research resource guards, not a
production device-memory scheduler.

The 120 Hz scene clock remains 8.33 ms. Internal 1.024 ms processing blocks
could provide smaller output deliveries while still using the current channel
epoch and continuously evolving Doppler. Block accumulation can add up to
approximately 1.024 ms before computation for live inputs, plus interpolation
lookahead (up to 8 microseconds at 32 taps/2 MS/s), computation and transport.
The benchmark times an entire 8.3335 ms output window; it does not measure a
live streaming pipeline or prove block-by-block delivery deadlines.

### Recommended architecture and remaining work

Use direct sampled rendering as the accuracy oracle. Pursue the bounded-error
Doppler-basis/FFT design as the next performance architecture, conditional on
declared channel ranges and end-to-end accuracy qualification. Do not promote
the experiment to a production default based on this CPU timing alone.

1. Implement and qualify private sample-clock resampling and persistent
   history/lookahead, including arbitrary recorded streams, band-edge signals,
   clock drift and transitions between channel epochs.
2. Port channel projection, private FFT filtering and reconstruction to a
   device-resident receiver worker. Keep each job's sources/transforms private.
   Move mandatory receiver DSP with them and export final receiver I/Q.
3. GPU basis construction can use numerical primitives suited to that device;
   validate the resulting coefficient error. The prototype's CPU Bessel calls
   are not a production CUDA implementation.
4. Measure FP64 first on the P100. Explore mixed precision only with phase,
   weak-signal and coherent-cancellation error bounds against the physical
   receiver noise floor. Consumer GPUs' much lower FP64 throughput cannot be
   ignored when choosing a $5,000 deployment.
5. Qualify every 1,000-link render with at least 1,028 valid paths/link at
   declared delay/Doppler bounds, then the complete moving-scene channel-to-ADC
   pipeline. Keep host proposal sampling, channel export, network payload,
   queueing and missed deadlines in the accounting.

This is a categorical change in the computation, supported by a measured
order-of-magnitude renderer improvement. It still leaves real implementation
and qualification work before claiming a live, affordable 120 Hz RF plane.

### Reproduce

No new dependencies are required. On this branch's bootstrapped environment:

```bash
.venv/bin/python -m pytest tests/test_doppler_basis.py -q
.venv/bin/python benchmarks/benchmark_doppler_basis.py \
  --links 4 --paths 1028 --samples 16667 --max-delay-us 100 \
  --max-doppler-hz 2500 --iterations 5 --output results/basis-four-links.json
.venv/bin/python benchmarks/benchmark_doppler_basis.py \
  --skip-direct-timing --links 1000 --paths 1028 --samples 16667 \
  --output results/basis-thousand-links-cpu.json
```

The last command can take minutes and still validates every sample/path of the
first link with the direct reference. It is CPU-only even in a GPU container.
It must not be published as a CUDA measurement. Ordinary project containers
contain this module and tests; a new container image has not been published by
this experiment.

### Related basis-emulation work

The [channel-to-I/Q implementation review](../references.md#iq-rendering-references) gives
source-level comparisons with Sionna PHY, GNU Radio, NVIDIA's CUDA emulator,
ACHEM/CHEM and HermesPy. It adds Kaltenberger et al. (2007) and Hofer, Xu and
Zemen (2017) as delay/Doppler subspace precedents. Their reconstruction cost
can be independent of physical path count after projection; their coefficient
construction still depends on paths and basis dimensions. Their DPS bases,
accuracy targets and tested delay support are not this prototype's Chebyshev
derivation or a prediction of our speedup.

[Hofer et al., *Real-Time Geometry-Based Wireless Channel Emulation*, IEEE TVT
68(2), 2019, DOI 10.1109/TVT.2018.2888914](https://thomaszemen.org/papers/Hofer19-IEEETVT-paper.pdf)
separates physical path generation from time-varying basis reconstruction.
Their discrete prolate spheroidal basis differs from this prototype's Chebyshev
basis; their reported reductions are not our speedup predictions. See
[the existing references and comparison](../archive/planning.md#affordable-realtime-rf).
The mathematical identity used here follows the
[NIST DLMF Jacobi–Anger expansions](https://dlmf.nist.gov/10.12).

<a id="direct-path-rendering"></a>

## Direct path I/Q rendering



**Runtime context (2026-10-05):** Direct-path reference and earlier implementation measurements, not the current qualified basis-renderer capacity. See [current runtime and wall-clock costs](../archive/runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

Branch: `optimization/direct-path-renderer`, based on `profiling/p100`.

The renderer retains every valid channel path separately. It does not convert
paths into a fixed tapped delay line, merge equal delays, select only the
strongest returns, or discard distinct Dopplers. Propagation remains one-way
for ESM/comms. The optional point-target radar model separately supplies its
round-trip coefficients, delays and Dopplers.

For each transmitter/receiver path, it evaluates:

```text
y_p[n] = sqrt(R * Ptx) * a_p * x(t_start + n/fs - delay_p)
         * exp(j * 2*pi * doppler_p * (t_start + n/fs - channel_epoch))
y_receiver[n] = sum_transmitters sum_paths y_p[n]
```

`a_p` includes carrier-delay phase at `channel_epoch`. No extra carrier phase
is added. Delay, amplitude and Doppler remain fixed within the capture, while
Doppler phase evolves at every sample. Geometry is solved once per capture;
the caller schedules captures once per pulse. This is the accepted narrowband
model, not wideband waveform stretching.

### Implementation and supported signals

`src/airsim_rf/rendering.py` provides `render_paths` and explicit
`ToneWaveform` / `LFMChirpWaveform` descriptions. `backend="numpy"` evaluates
an independent analytic reference. `backend="llvm"` or `"cuda"` runs a
Dr.Jit recurrence kernel using the already-pinned dependency stack. CUDA
requests fail when CUDA is unavailable; there is no implicit CPU fallback.

Default tiles contain 128 paths and 32 consecutive samples. Each path/sample
tile lane initializes the analytic waveform+Doppler phase and advances by
complex multiplication. For LFM, the phase increment itself advances by a
second recurrence. Fractional delays are evaluated analytically, including the
half-open pulse gate. Phase is reinitialized analytically every 32 samples to
bound accumulated error. Phase arithmetic, recurrence and reduction use FP64.

Each lane writes unique locations in two temporary real/imaginary buffers.
The buffers are reduced across paths and added to the receiver waveform.
This avoids a contested atomic addition for every path/sample. Buffers hold
one path tile times the receive-window size, rather than all scene paths
at all sample times. Contribution-buffer storage is approximately
`16 * path_tile * num_samples` bytes: 8.5 MiB for 128 paths and 4,352 samples,
plus recurrence state, reduction/output arrays and runtime allocations.
Work remains O(paths × samples). This implementation is a correctness-first
baseline; tile sizes and launch/reduction overhead require GPU profiling.

An experimental `render_paths(..., accumulation="local")` option replaces the
contribution buffers with SIMD-packet/CUDA-warp local pre-reduction followed by
atomic output addition. It preserves the same waveform, FP64 arithmetic, valid
paths and individual Dopplers. It can introduce atomic contention and small
nondeterministic summation-rounding differences; the default remains
`"partial"`. `SDRNetworkReceiver(..., accumulation="local")` exposes it for
comparison with the full receive chain. No transmitter buffers are shared.
See [the measurements and profiling commands](../rendering.md#independent-tx-optimization).

The newer [batched backend](../rendering.md#batched-rendering) adds independent private-input
jobs, reusable execution and sampled-waveform interpolation. The analytic-only
restriction below applies to the original `direct-*` backends.

Arbitrary Python waveform callbacks continue to work with the existing NumPy
renderer. They are rejected explicitly by the direct backend. Sampled comms
waveforms with fractional-delay interpolation are a subsequent extension;
the current direct GPU implementation is not yet an arbitrary SDR waveform
renderer. One `LFMChirpWaveform` describes one pulse, with an explicit pulse
start epoch; a pulse train needs appropriately scheduled pulses or a future
train descriptor. The caller must select adequate sample rate/bandwidth.

### Coherence between captures

When splitting one channel realization into blocks, supply the same
`channel_epoch_ns` and waveform reference epoch for every block. Doppler phase
then continues across block boundaries. Integer nanosecond epochs are
subtracted before conversion to seconds, preserving LFM timing precision even
at Unix-scale epochs. TX clock error and pre-propagation LO phase are supported.
Very large absolute epochs with nonzero oscillator offsets still have finite
FP64 phase precision; this is not an arbitrary-precision clock model.

When Sionna retraces moving geometry, its new complex coefficient already
includes phase at the new capture epoch. Use that new epoch with the new
coefficient; carrying the old Doppler phase into it again would double count
motion. Newly appearing/disappearing paths and changing diffuse sample
identities still need physical temporal-correlation validation. This kernel
does not establish persistent terrain scatterers across retraces.

### APIs and receiver integration

```python
from airsim_rf.rendering import LFMChirpWaveform, render_paths

iq = render_paths(
    coefficients, delays_s, doppler_hz,
    LFMChirpWaveform(bandwidth_hz=20e6, pulse_width_s=1e-6,
                    reference_time_ns=pulse_start_ns),
    sample_rate_hz=50e6, num_samples=5000,
    sim_time_ns=pulse_start_ns, channel_epoch_ns=channel_epoch_ns,
    amplitude_scale=(50 * transmit_power_w)**0.5,
    backend="cuda",
)
```

`render_paths` returns complex128 values; it does not add noise or normalize
power. `synthesize_voltage(..., renderer="direct-cuda")` applies the usual
RMS voltage scaling/noise and returns the established complex64 `IQBlock`.
`RFReceiver(..., renderer="direct-cuda")` accepts waveform descriptors.
`PointTargetRadar(..., renderer="direct-cuda")` uses compact one-way Sionna
coefficients to form its existing reciprocal point-target radar model, then
renders LFM echoes through this backend.

`SDRNetworkReceiver(..., renderer="direct-cuda")` traces all links once,
renders each transmitter's contribution and sums before receiver noise/filter
and ADC. Emitters must use the explicit waveform descriptions. TX clock/LO
error and the receiver LO are preserved. Its current implementation exports
channels through NumPy, transfers each link to the device, and downloads the
rendered link before CPU diagnostics, filtering and ADC. It is not a fully
GPU-resident, fused 100-transmitter receive chain. Per-link transfers and all
front-end work are included in the service timing.

### Run and profile

```bash
git clone --branch optimization/direct-path-renderer --single-branch \
  https://github.com/wa200508/airsim-rf.git
cd airsim-rf
bash scripts/run_p100_docker.sh --quick --run-id p100-direct-quick
bash scripts/run_p100_docker.sh --run-id p100-direct-full
python3 scripts/publish_gpu_results.py results/profiling/p100-direct-full --push
```

The collector now compares NumPy and direct recurrence for both CPU and CUDA
propagation, at 2 and 100 transmitters per receiver. Direct CPU uses LLVM;
direct GPU uses CUDA. It runs renderer correctness tests after successful GPU
preflight, records synchronized rendering latency separately, and collects
separate instrumented profiles. The report groups CPU/CUDA pairs by renderer
and includes a renderer comparison table. Use `--renderers numpy` to reproduce
the previous implementation alone, or `--renderers direct` for recurrence only.

The pulsed radar example also accepts the renderer:

```bash
.venv/bin/python examples/lfm_radar.py --backend cuda --renderer direct-cuda \
  --output lfm-direct.npz
```

A single case can be measured with:

```bash
.venv/bin/python benchmarks/benchmark_sdr_runtime.py \
  --backend cuda --renderer direct-cuda --tx 100 --rx 1 \
  --samples 4096 --samples-per-link 1028 --warmup 5 --iterations 30 \
  --output results/direct-cuda.json
```

`--path-tile` and `--sample-tile` tune standalone benchmark tiles. The collector
uses the documented defaults. See [the P100 guide](../setup.md#p100-profiling) for device
passthrough, compatibility checks, telemetry, Nsight and publication details.
No P100 or other CUDA execution has been verified in this CPU-only workspace.

### Validation

Tests compare both implementations with independent waveform equations,
including fractional delays, LFM pulse gates, positive/negative Doppler,
same-delay paths with different Dopplers, coherent cancellation, independent
TX clocks/LOs, phase continuity across blocks and Unix-scale LFM epochs.
The LLVM renderer is compared with the existing Sionna/SDR voltage, link-power
and ADC pipeline. CUDA equation/continuity checks run on a GPU host; local
CUDA cases are explicitly skipped when no device is available.

Useful public implementation precedents include NVIDIA's
[Sionna Research Kit CUDA renderer](https://github.com/NVlabs/sionna-rk/blob/main/plugins/channel_emulation/cuda_emulator/src/chn_emu_cuda.cu),
[Sionna PHY time-channel renderer](https://github.com/NVlabs/sionna/blob/main/src/sionna/phy/channel/apply_time_channel.py)
and [OCUDU GPU Channel](https://github.com/zhouyou-gu/ocudu-gpu-channel).
This implementation uses our own direct-path equations and the existing
Dr.Jit runtime; no source from those renderers was copied.

### Preliminary CPU measurements

The [CPU-only profiling bundle](../../results/profiling/direct-renderer-cpu-validation/REPORT.md)
compares the original renderer with LLVM recurrence on this workspace's two-core
CPU quota. Both use the same 800-triangle terrain, 1,028 attempts/link,
4,096 output samples plus 256 filter warmup samples, and independent radio clocks.

| 100 TX / 1 RX | Original NumPy | Direct LLVM |
|---|---:|---:|
| Median rendering | 11,069 ms | 310 ms |
| Median complete service | 11,195 ms | 394 ms |
| Sustained serial updates | 0.089 Hz | 2.537 Hz |
| Retained paths | 42,509–42,513 | 42,509–42,513 |

That is approximately 35.7× faster rendering and 28.4× lower median complete
service latency. Only two timed captures were collected in this quick large
case; this is not a reliable p95/tail estimate or a 120 Hz claim. The small
2-TX case also improved, but its three timed captures include a latency spike
and do not establish stable warmed performance. The source was a dirty working
copy based on `720c401`; the bundle records file hashes and exact commands.
These are measured CPU results, not GPU projections or measured P100 behavior.

The completed local suite and offline non-root profiling container each passed
88 tests, with five CUDA cases skipped. The direct LLVM pulsed-radar example
recovered range peaks at 299.79 m and 599.58 m for targets at 300 m and 600 m.

<a id="batched-rendering"></a>

## Batched private-transmitter rendering



**Runtime context (2026-10-05):** Historical CPU optimization. The 243 ms service case uses tones, about 42,500 surviving paths and 2.048 ms of output; it is not the newer all-valid-path continuous-window GPU case. See [current runtime and wall-clock costs](../archive/runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

Branch: `optimization/direct-path-renderer`. The new `batched-llvm` and
`batched-cuda` SDR backends batch independent link jobs and replay compiled
execution. They also accept arbitrary sampled I/Q. Existing renderer defaults
are unchanged. This is an implementation and CPU measurement, not a claim of
120 Hz operation or measured GPU performance.

### What changed and why

The [independent-transmitter profiling study](../rendering.md#independent-tx-optimization)
identified repeated kernel launches, phase setup, temporary contribution arrays
and per-link transfers. This implementation addresses those costs:

- Each job has disjoint path data, private sampled input and private output.
  Packing jobs never aliases transmitter samples or shares their transforms.
- Jobs are grouped under `max_render_lanes`, with configurable path and sample
  tiles. Paths are padded and masked; all valid paths remain. A larger path
  count creates a larger capacity configuration instead of truncating paths.
- Persistent `dr.freeze` callables replay execution for compatible shapes.
  Gains, delays, Dopplers, clocks, input samples and timestamps remain runtime
  inputs. Cache capacity is bounded to 16 configurations. Aligned private input
  allocations avoid retracing caused by inconsistent NumPy buffer alignment.
- Weighted initial phasors and increments are prepared once per path. Within
  a tile, recurrence preserves phase evolution at every sample. LFM retains
  its changing instantaneous frequency and quadratic phase. No low-Doppler,
  common-waveform or short-delay assumption is used to remove work.
- Contributions reduce directly into contiguous job outputs without storing
  a complete path-by-sample array. CPU `auto` uses Dr.Jit's thread-private
  expanded reduction when the output fits its threshold, otherwise local
  reduction. CUDA uses local reduction. CPU thread replicas still consume
  memory: the lane limit is not a total-memory limit.
- Per-link diagnostics remain enabled by default. Explicitly disabling them
  permits coherent device summation and one receiver output export, and omits
  the per-link power report. Noise, receiver filtering and ADC remain enabled.

The receiver retains a `BatchedPathRenderer` between captures. Recreating it
per capture discards the replay cache. Replay does not freeze scene physics:
channel visibility and coefficients still update at each channel epoch.

Sionna channel data still pass through NumPy, preparation is still on the host,
and final receiver filtering/noise/ADC remain CPU work. Captures still use the
existing 256-sample filter warmup and fresh filter state; this change does not
provide a stateful continuous streaming receiver or eliminate distributed
transport latency.

### Arbitrary sampled I/Q

`SampledWaveform` owns a copied, read-only complex128 source buffer. The batched
backend supports different input/output rates, independent transmitter clocks
and carrier offsets. Even jobs given the same descriptor receive disjoint
source allocations; no transmitter sharing savings are assumed.

```python
from airsim_rf.batched_rendering import BatchedPathRenderer, PathRenderJob
from airsim_rf.sampled_waveform import SampledWaveform

wave = SampledWaveform(
    input_iq_with_history_and_lookahead,
    sample_rate_hz=2e6,
    reference_time_ns=first_input_sample_ns,
    interpolation_taps=32,
)
engine = BatchedPathRenderer(backend="cuda")  # Keep this instance alive.
job = PathRenderJob(gains, delays_s, dopplers_hz, wave)
iq = engine.render(
    [job], sample_rate_hz=2e6, num_samples=16667,
    sim_time_ns=output_start_ns, channel_epoch_ns=channel_epoch_ns,
)
```

Fractional delays use normalized Lanczos-windowed sinc interpolation. Every
physical path retains its gain, delay and Doppler; interpolation taps describe
the sampled-waveform reconstruction kernel, not a merged physical channel.
The implementation factors out common sinc terms and advances the remaining
interpolation sine through recurrence, including sample-coordinate wraps.
It avoids trigonometry per interpolation tap and handles nonunit rate ratios.

The finite kernel approximates ideal bandlimited reconstruction. Support is
selectable from 4 to 128 even taps. Agreement with the NumPy reference verifies
the same finite operator, not an ideal-reconstruction error or receiver noise
floor guarantee. A separate 64-tap Fourier test checks normalized RMS error
below 1e-4 for its specific frequencies up to 0.23 times the input sample rate;
that is not a full-band qualification.

The default `boundary="error"` requires valid history and lookahead for every
path and output sample. `boundary="zero"` explicitly represents a finite
transmission surrounded by zero. At 2 MS/s, 32 taps require up to 8 microseconds
of future input support, adding delivery latency for a live input source.
Input amplitude is preserved, not normalized. Use unit mean-square input when
interpreting the SDR emitter's nominal power that way, and declare occupied
frequency bounds correctly for receiver Nyquist checks.

### Matched CPU measurements

Data: [environment](../../research_results/batched_renderer_cpu/environment.json),
[per-link local](../../research_results/batched_renderer_cpu/per_link_local.json),
[batched, tile 32](../../research_results/batched_renderer_cpu/batched_32.json),
[batched, tile 128](../../research_results/batched_renderer_cpu/batched_128.json).

All three use the same ten scene epochs and identical per-epoch retained path
counts (42,513–42,526). Configuration: 100 independent tone transmitters,
one receiver, 4,096 output samples plus 256 filter-warmup samples, 1,028 diffuse
attempts per link, two Dr.Jit threads and a two-core CPU quota. Per-link
diagnostics, clocks, noise, filtering and ADC are enabled. Two warmups precede
ten unprofiled captures. Complete service includes channel calculation and
channel export, but excludes AirSim physics/RPC, network queues and RF skills.

| Renderer | Median rendering | Median complete service | Serial capture rate |
| --- | ---: | ---: | ---: |
| Per-link recurrence, local reduction | 189.40 ms | 274.03 ms | 3.60 Hz |
| Batched replay, sample tile 32 | 170.32 ms | 247.32 ms | 4.04 Hz |
| Batched replay, sample tile 128 | 169.87 ms | 243.25 ms | 4.03 Hz |

The tile-128 comparison is 1.115 times faster in rendering and 1.127 times
faster in complete service. Earlier 331 ms captures are not a matched baseline
for this run. Tile 128 did not demonstrate a clear CPU throughput advantage
over 32, so the API default stays 32. Neither configuration meets 120 Hz.

The [separate instrumented run](../../research_results/batched_renderer_cpu/batched_events.json)
uses four replayed rendering kernels per capture, compared with approximately
400 in the earlier per-link profile. Warm captures report no new recordings
and zero replayed code-generation time. Tile 128 fits the hundred jobs in one
435,200-lane group with 512 padded path slots per job. This is a launch-count
improvement to test on a GPU, not a prediction of a hundredfold speedup.
Host preparation alone takes roughly 7–8 ms in that profile. Export/wait time
includes asynchronous device execution and is not a measurement of pure copy
cost. These stages can overlap; do not add them as independent costs.

#### Separate sampled-input stress measurement

[Sampled-input data](../../research_results/batched_renderer_cpu/sampled_input.json)
exercise one private source, **1,028 valid paths**, 4,096 outputs, 32 taps,
delays up to 100 microseconds and Dopplers up to 2,500 Hz, with source clock
offset and random complex input occupying 90% of the sample-rate bandwidth.
Median renderer latency is **166.34 ms**, p95 **171.29 ms**, over ten unprofiled
captures. This is 4,210,688 path/sample contributions with interpolation.
It excludes ray tracing, AirSim, receiver DSP and private source generation.

The finite-operator reference includes all paths of the first link and a
128-sample prefix: normalized RMS disagreement is 6.9e-14. It is not a
100-transmitter/10-receiver continuous-stream benchmark. Arbitrary sampled
rendering remains much more expensive per contribution than analytic tones;
the new engine does not establish feasibility for the target workload.

### Run the GPU comparisons

The [P100 kit](../setup.md#p100-profiling) now compares NumPy, per-link and batched
rendering by default. Per-link collection defaults to local accumulation;
`--direct-accumulation partial` selects the old buffered implementation.
It separately collects sampled-input stress measurements and includes them
in the report without treating them as complete scene service measurements.
CUDA correctness checks cover both renderer implementations when preflight
successfully exercises a real CUDA/OptiX scene.

```bash
bash scripts/run_p100_docker.sh --quick --renderers direct batched \
  --run-id p100-batched-quick
bash scripts/run_p100_docker.sh --renderers direct batched \
  --run-id p100-batched-full
bash scripts/run_p100_docker.sh --quick --renderers batched \
  --sample-tile 128 --run-id p100-batched-128
python3 scripts/publish_gpu_results.py results/profiling/p100-batched-full --push
```

The collector's full sampled case defaults to 100 independent links, 1,028
valid paths per link, 4,096 outputs and 32 interpolation taps. Pass
`--samples 16667` to the collector to measure approximately one 120 Hz interval
at 2 MS/s in both its scene and sampled cases. The sampled case remains a
renderer-only test. For a separately measured all-1,000-link stress run:

```bash
.venv/bin/python benchmarks/benchmark_batched_rendering.py \
  --backend cuda --links 1000 --paths 1028 --samples 16667 \
  --taps 32 --max-delay-us 100 --max-doppler-hz 2500 \
  --iterations 10 --output results/sampled-gpu-1000links.json
```

That run can be expensive and needs a separate delay/Doppler/bandwidth/support
sweep for qualification. Neither terrain path attrition nor transmitter sharing
is used to reduce its path count. The collector reports unavailable CUDA
explicitly; it does not silently substitute CPU measurements.

### Validation and next priorities

Tests cover changing runtime data under replay, capacity growth, private inputs,
different interpolation supports, arbitrary rate ratios, clock offsets, split
capture continuity, finite-buffer boundaries, coherent summation and complete
SDR receiver outputs against the existing implementation. CUDA cases remain
untested in this CPU workspace.

Before further backend changes, collect real GPU execution, bandwidth and
reduction contention measurements. Next architectural candidates are keeping
channel inputs/preparation and receiver DSP resident on the device, a persistent
streaming receiver with history/lookahead and backpressure, and an optimized
native interpolation kernel if GPU profiling identifies interpolation as the
dominant cost. These require measurements and accuracy qualification; none is
included in the performance claim above.

<a id="independent-tx-optimization"></a>

## Optimizations with independent transmitter data



**Runtime context (2026-10-05):** Historical direct-renderer accumulation experiments and bandwidth accounting; preserve independent buffers, but use the current qualified basis measurements for achieved throughput. See [current runtime and wall-clock costs](../archive/runtime.md#runtime-status) for comparable measurements, hardware, exclusions and ten-minute estimates.

The target remains 100 independent transmitters, 10 receivers, continuous
2 MS/s I/Q and 120 Hz channel updates, retaining full first-order path coverage
and individual narrowband Doppler evolution. The compute ceiling is $5,000.
No transmitter-buffer or transmitter-transform sharing is credited. Separate
receiver workers own private copies of their inputs. Batching jobs means
launching independent work together, not making their input data identical.

The workload has not been qualified at 120 Hz on affordable GPUs. Optimizing
execution must not depend on short delays, low Doppler, fewer rays, a special
waveform family or reduced scene-update cadence.

### First experiment: eliminate contribution buffers

Previously, `render_paths` wrote two FP64 arrays of size
`path_tile * num_samples`, then reduced them across paths. The new experimental
`accumulation="local"` option computes the same contribution, locally combines
lanes with the same output index, and atomically adds to the link's private
output. Dr.Jit implements this local reduction within CPU SIMD packets or CUDA
warps. This removes the explicit path-by-sample buffers and their later
reduction pass. Path coefficients, delays, sample count, precision and per-path
Doppler recurrence are unchanged. It remains O(paths * samples).

This is an intermediate implementation to measure. Atomic updates still touch
memory and may contend; a custom GPU block reduction with register/shared-memory
accumulators is another candidate. Local reduction does not imply that every
sum stays on-chip, nor that removing buffers guarantees a particular speedup.
Atomic summation can have small scheduling-dependent rounding differences.
The default remains `accumulation="partial"` until GPU qualification.

#### CPU kernel measurements

[Recorded measurements](../../research_results/affordable_realtime/accumulation_cpu.json)
use four independent directed-link jobs, each with 1,028 valid paths and 16,667
samples at 2 MS/s. Every link has separately allocated, randomly generated
gains, fractional delays spanning a declared 0–100 microsecond range, and
independent Dopplers in +/-2,500 Hz. No terrain visibility removes paths.
Tone parameters and LFM parameters are different between links. The LFM gate
is identical between implementations; the continuous tone case exercises
contributions throughout the window. The CPU quota is two cores.

| Four private links, 128-path tiles | Original contribution buffers | Local accumulation | Median reduction |
|---|---:|---:|---:|
| Tone | 292.86 ms | 50.26 ms | 5.83x |
| LFM | 182.04 ms | 52.48 ms | 3.47x |

With 1,028-path tiles, local accumulation took 47.38 ms for tone and 47.79 ms
for LFM. Increasing tile size alone made the original buffered implementation
slower here. This illustrates why tile size is a measured hardware choice.
For 128-path tiles, the eliminated contribution arrays occupied 32.55 MiB
per active link; for 1,028-path tiles, 261.44 MiB. The renderer still allocates
outputs, lane/phase state and other runtime memory.

Ten warmed runs per configuration were collected, with synchronous NumPy export
included in timing. The JSON includes every timing, first-call timing, validation
errors and source hashes. These are exploratory timings, not dependable tail
latency estimates. Maximum absolute error against the independent FP64 analytic
reference was below 1e-11; normalized RMS error was below 1.5e-12. Tests also
cover equal-delay paths with different Dopplers, coherent cancellation, pulse
boundaries, split-block phase continuity and the complete SDR frontend.

**This experiment supports analytic tone/LFM only.** It does not benchmark
sampled-waveform interpolation, propagation or continuous stateful receiver
processing. Four links are a kernel diagnostic, not the 1,000-link acceptance
workload. No CUDA execution is available in this workspace. A CPU speedup must
not be multiplied by a guessed GPU scaling factor.

#### Complete existing CPU capture case

The same option was compared in the existing 100-TX/1-RX terrain capture,
using 4,096 output samples plus 256 filter-warmup samples, 1,028 attempts/link,
moving poses, independent clocks and the complete noise/filter/ADC chain.
Both runs used the same ten timed scene epochs and retained 42,513–42,526 paths.
These capture windows are the existing test, not a gap-free continuous stream.

| Median stage | [Buffered run](../../research_results/affordable_realtime/sdr_partial_cpu.json) | [Local run](../../research_results/affordable_realtime/sdr_local_cpu.json) |
|---|---:|---:|
| Rendering | 355.57 ms | 240.32 ms |
| Channel solve/export | 84.03 ms | 67.97 ms |
| Complete service | 461.36 ms | 330.69 ms |
| Service minus rendering, measured per epoch | 106.38 ms | 90.84 ms |

Complete-service median improved by about 1.40x, substantially less than the
isolated kernel's improvement. The channel timing difference is variability in
a stage unchanged by this rendering option; do not attribute it to accumulation.
The buffered run also had large service spikes (about 1,046 ms empirical p95,
versus 362 ms for local). Ten samples do not qualify tail latency, and these
runs did not diagnose the cause of those spikes. Host proposal draws alone
took approximately 17–18 ms, exceeding the 8.33 ms scene-update budget.
This establishes that reducing rendering buffers alone cannot meet 120 Hz.

The updated local suite passed 97 tests, with nine CUDA cases skipped because
no device was available. GPU qualification remains outstanding.

### Other optimizations to explore

| Change | Why it can help | Required constraint / verification |
|---|---|---|
| Fused sampled-waveform rendering | Interpolate private input samples, evolve each path's Doppler, apply complex gain and accumulate in one kernel instead of writing intermediate tensors | Preserve all valid paths and arbitrary sampled data. Sweep delay/Doppler ranges and interpolation accuracy; retain input history and include any lookahead in latency. The analytic experiment is only the accumulation portion. |
| Device-resident channel and receiver chain | Avoid exporting Sionna paths to NumPy, re-uploading derived arrays, downloading every rendered link and running the coherent sum/filter/ADC on the CPU | Input buffers remain private. Retain independent clocks, calibrated scaling, noise, filter state, ADC and clipping. Download the selected receiver output stream after mandatory processing. |
| Batched independent jobs and stable launches | Reduce Python calls, allocations, synchronization and JIT/launch overhead by scheduling separate link jobs together | Keep separate storage and parameters. Size buckets may pad with invalid lanes but must never truncate valid paths; overflow needs a larger bucket or additional work. Measure first-use compilation separately from warmed deadlines. |
| Private double buffering and streams | Overlap independent input transfer, rendering and output delivery when resources permit | Count the full private input traffic. Overlap does not remove bandwidth cost, and throughput can improve without reducing dependent-sample latency. Queues must stay bounded. |
| GPU proposal sampling | Current diffuse direction draws use NumPy even with CUDA propagation; move sampling/PDF work to the GPU to remove a host stage and direction upload | Preserve both TX and RX proposal components, uniform coverage, all attempts, mixture densities and weights. Validate distribution and RF statistics when the RNG changes. |
| Cache invariant antenna tables | Current code rebuilds body-frame angular gain/PDF tables on each solve, including device-to-host export | Only cache a pattern that is unchanged; rotate directions using current poses and invalidate on pattern changes. Materials, geometry-dependent gains and visibility still update. This does not remove the separate sampling cost. |
| Compile or move frontend processing | Existing per-link diagnostics and receiver processing have CPU/Python overhead | Mandatory RF processing stays. Per-link power diagnostics can be separately timed or explicitly disabled when unused, with equivalence of receiver I/Q verified. No savings are credited until measured. |
| Validated mixed precision | FP32 arithmetic could make consumer GPUs more suitable than the current FP64 kernel | Validate phase continuity, long epochs, weak returns and strong-signal cancellation against FP64, using absolute noise-floor error as well as relative EVM. Do not assume ADC resolution permits FP16/TF32. P100 and consumer RTX have different FP64/FP32 tradeoffs. |

Static geometry acceleration and exact specular plane extraction are already
cached in the current stack. Do not count them again as an entirely new
optimization. Moving platforms still require current geometry, visibility,
antenna orientation, delay, gain and Doppler at the requested update cadence.
Persistent diffuse scatterer identities need separate temporal-correlation
validation; freezing visibility is not a valid substitute.

### Bandwidth accounting without source sharing

At 100 TX, 10 RX and continuous 2 MS/s:

| Traffic | Aggregate payload | Interpretation |
|---|---:|---|
| 100 original independent complex64 source streams | 1.6 GB/s | Data at the source side, before worker replication |
| Private input delivery to all ten receiver workers | 16 GB/s | Each worker owns 100 streams; no reuse credit |
| Current per-link complex128 output downloads | 32 GB/s | If the present per-link export architecture rendered all 1,000 links continuously |
| One final complex64 I/Q stream per receiver | 160 MB/s | Possible output traffic after moving required summation/frontend work to the device |
| Raw FP64 path state at 1,028 paths/link and 120 Hz | 3.95 GB/s | Complex gain plus delay plus Doppler, 32 bytes/path; excludes padding, gates and other solver state |

The output reduction combines the physically required independent signals at
the receiver. It does not share transmitter input buffers. The input traffic
still needs to fit the actual PCIe/network arrangement, or be generated locally
into private buffers with that generation cost measured. If generation moves
on-device, arbitrary recorded streams must still be supported and benchmarked.
A single 10 GbE link cannot carry even one worker's 1.6 GB/s raw input payload.

With 1,028 valid paths per link, direct continuous rendering requires 2.056
trillion path/sample contributions per second. The old temporary write/read
scheme alone accounts for about 65.8 TB/s at 32 bytes/contribution. Removing
that traffic is worthwhile, but interpolation input reads, phase arithmetic,
reduction, ray tracing and private input delivery remain. Neither these operation
counts nor the CPU experiment prove a $5,000 deployment can meet the deadline.

### Run the comparison on a GPU

On the existing profiling branch/environment:

```bash
## Kernel diagnostic; all input/channel arrays are private per directed link.
.venv/bin/python benchmarks/benchmark_render_accumulation.py \
  --backend cuda --links 4 --paths 1028 --samples 16667 \
  --max-delay-us 100 --max-doppler-hz 2500 \
  --iterations 30 --output results/accumulation-gpu.json

## Larger analytic renderer stress; still excludes propagation and receiver DSP.
.venv/bin/python benchmarks/benchmark_render_accumulation.py \
  --backend cuda --links 1000 --paths 1028 --samples 16667 \
  --iterations 10 --output results/accumulation-gpu-1000links.json

## Complete existing SDR capture case with experimental reduction.
.venv/bin/python benchmarks/benchmark_sdr_runtime.py \
  --backend cuda --renderer direct-cuda --accumulation local \
  --tx 100 --rx 1 --samples 4096 --samples-per-link 1028 \
  --iterations 30 --output results/sdr-local-gpu.json
## Repeat with --accumulation partial for the same workload.
```

The kernel diagnostic deliberately retains existing per-link transfers and
launches, so it measures this implementation's overhead rather than assuming
private residency/batching has already been built. The large stress also
retains those costs and can take substantial time. Accuracy is checked against
NumPy on the first four independent links; the correctness suite supplies
additional cancellation/continuity cases. It is not full arbitrary-I/Q validation.
Run unprofiled timings separately from instrumented profiles, record GPU model,
driver and software versions, and compare exactly matching parameters.

Qualification must eventually use arbitrary private sample streams across all
1,000 links, declared channel ranges and the complete moving-scene/frontend
pipeline. Report achieved sustained rate, chunk delivery latency, p95/p99,
missed deadlines and dropped samples. A whole 8.33 ms chunk can add buffering
delay before computation; smaller delivery chunks trade that latency against
more launches without reducing the total physical workload.

The immediate next priorities are GPU measurement of accumulation and a general
sampled-waveform fused kernel, followed by device-resident channel/frontend
processing and proposal sampling. The complete 120 Hz goal remains unproven.

