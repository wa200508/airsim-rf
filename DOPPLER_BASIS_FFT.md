# Change the rendering architecture: all-path Doppler basis and FFTs

**Runtime context (2026-10-05):** The 22× figure below compares two CPU algorithms on an earlier host and small link counts. It is not a real-time ratio or fleet speedup. Qualified P100 results are now available separately. See [current runtime and wall-clock costs](RUNTIME_STATUS.md) for comparable measurements, hardware, exclusions and ten-minute estimates.

The batched direct renderer is useful as a reference, but its dominant work
still scales with physical paths times output samples times interpolation
support. A 10–15% capture improvement does not resolve the target workload.
The next candidate changes the channel representation and rendering algorithm.

The new, opt-in CPU research implementation is
[`DopplerBasisRenderer`](src/airsim_rf/research/doppler_basis.py), with a
[matched benchmark](benchmarks/benchmark_doppler_basis.py). It is separate from
the receiver backends. It demonstrates approximately **22 times faster
sampled-I/Q rendering** for the declared synthetic workload below. It does
not demonstrate complete 120 Hz service or the $5,000 target. This initial CPU
experiment predates the [qualified P100 renderer collection](RUNTIME_STATUS.md).

## Physical model retained

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
[direct reference implementation](src/airsim_rf/batched_rendering.py).

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
discussed in [the architecture study](AFFORDABLE_REALTIME_RF.md). Its speedup
comes from representing the full time evolution within a controlled error,
not from freezing a tapped delay line between channel updates. Finite temporal
approximation is an explicit additional numerical assumption.

## Error and qualification bounds

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

## CPU evidence with all valid paths

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
| [1](research_results/doppler_basis_cpu/one_link.json) | 694.60 ms | 30.89 ms | 22.48 times |
| [4](research_results/doppler_basis_cpu/four_links.json) | 2,864.97 ms | 129.48 ms | 22.13 times |

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

### Unfavorable ranges are measured too

These are one-link basis-only timings. All output samples are still checked
against all-path direct rendering, but direct timing was not collected:

| Changed qualification parameter | Basis median | Full-block degree | Delay coefficients |
| --- | ---: | ---: | ---: |
| [Delay bound 1,000 microseconds](research_results/doppler_basis_cpu/delay_1000us.json) | 46.13 ms | 25 | 2,033 |
| [Doppler bound +/-25,000 Hz](research_results/doppler_basis_cpu/doppler_25000.json) | 279.49 ms | 138 | 233 |
| [4,096 valid paths](research_results/doppler_basis_cpu/paths_4096.json) | 80.77 ms | 25 | 233 |

The high-Doppler case is substantially slower. Wider delays grow FFT support;
more paths increase projection work. No fixed cheap-rank claim is made for
all environments. Shorter processing blocks are another tunable tradeoff, but
they change projection/FFT overhead and must be measured at the same bounds.

## Scaling and latency

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

## Recommended architecture and remaining work

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

## Reproduce

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

## Related basis-emulation work

The [channel-to-I/Q implementation review](IQ_RENDERING_REFERENCES.md) gives
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
[the existing references and comparison](AFFORDABLE_REALTIME_RF.md).
The mathematical identity used here follows the
[NIST DLMF Jacobi–Anger expansions](https://dlmf.nist.gov/10.12).
