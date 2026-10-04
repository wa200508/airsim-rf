# Change the rendering architecture: all-path Doppler basis and FFTs

The batched direct renderer is useful as a reference, but its dominant work
still scales with physical paths times output samples times interpolation
support. A 10–15% capture improvement does not resolve the target workload.
The next candidate changes the channel representation and rendering algorithm.

The new, opt-in CPU research implementation is
[`DopplerBasisRenderer`](src/airsim_rf/research/doppler_basis.py), with a
[matched benchmark](benchmarks/benchmark_doppler_basis.py). It is separate from
the receiver backends. It demonstrates approximately **22 times faster
sampled-I/Q rendering** for the declared synthetic workload below. It does
not demonstrate complete 120 Hz service, GPU performance or the $5,000 target.

## Physical model retained

Under the already accepted narrowband Doppler model, a link is:

```text
y[n] = sum_p gain[p] * exp(j*2*pi*fd[p]*(t[n]-channel_epoch))
                      * reconstructed_private_input(t[n]-delay[p])
```

The finite input reconstruction is the same normalized Lanczos interpolation
as the existing sampled renderer. Every supplied path enters the new channel;
its fractional delay and its own Doppler remain. Equal-delay paths with
different Dopplers still beat and can cancel. No Doppler averaging, dominant
path selection, reduced output rate or reduced scene updates are used.

For each small processing block, write output time as its centre plus `u`
times half its duration, where `u` ranges from -1 to 1. The Jacobi–Anger identity
gives the Chebyshev expansion:

```text
exp(j*z*u) = J_0(z) + 2*sum_{q>=1} j^q*J_q(z)*T_q(u)
z[p]       = pi*fd[p]*block_duration
```

`J_q` is a Bessel function and `T_q` a Chebyshev polynomial. Truncate this
temporal expansion at a degree chosen from the **declared maximum Doppler**,
block duration and error tolerance. There is no snapping Dopplers onto bins.
For each basis term, combine the delayed path weights into a filter:

```text
H_q[k] = sum_p interpolation_weight[p,k] * gain[p]
              * exp(j*2*pi*fd[p]*(block_centre-channel_epoch))
              * chebyshev_coefficient[q,p]
y[n]   = sum_q T_q(u[n]) * overlap_save_convolution(H_q, private_input)[n]
```

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

The degree selection uses a conservative uniform Bessel-tail bound:

```text
|J_q(z)| <= (|z|/2)^q/q! * exp(z^2/(4*(q+1)))
tail     <= 2*B_q/(1-|z_max|/(2*(q+1)))
```

Starting beyond `|z_max|`, this bounds the omitted Chebyshev terms for every
`u` in [-1,1] and every Doppler in the declared range. The default dimensionless
temporal tolerance is 1e-10. The reported absolute output bound multiplies that
tolerance by maximum input amplitude and the sum of absolute path gains times
the interpolation weights' L1 norms. It therefore still applies near coherent
cancellation, where relative output error alone can be misleading.

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

[Hofer et al., *Real-Time Geometry-Based Wireless Channel Emulation*, IEEE TVT
68(2), 2019, DOI 10.1109/TVT.2018.2888914](https://thomaszemen.org/papers/Hofer19-IEEETVT-paper.pdf)
separates physical path generation from time-varying basis reconstruction.
Their discrete prolate spheroidal basis differs from this prototype's Chebyshev
basis; their reported reductions are not our speedup predictions. See
[the existing references and comparison](AFFORDABLE_REALTIME_RF.md).
The mathematical identity used here follows the
[NIST DLMF Jacobi–Anger expansions](https://dlmf.nist.gov/10.12).
