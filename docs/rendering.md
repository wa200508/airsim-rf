# Rendering operators and qualification

The current receiver offers direct reference rendering and Doppler-basis
rendering through `basis-cpu` and `basis-cuda`. The live workflow selects
`basis-cuda` and retains all physical paths. [Performance](performance.md)
records the measured GPU operating envelope; device compatibility and numerical
operator agreement are separate from calibrated RF accuracy.

<a id="doppler-basis-fft"></a>

## All-path Doppler basis and private FFT filtering

For a link with complex gain `a`, delay `τ` and narrowband Doppler `fD`, the
implemented model sums delayed/interpolated private samples multiplied by the
path's evolving phase:

```text
y[n] = Σp a[p] exp(j 2π fD[p] (t[n] − t0)) x_interpolated(t[n] − τ[p])
```

The reference interpolation is finite, with declared support and source
history/lookahead. The basis renderer approximates temporal variation within
blocks and projects all paths into delay filters. Private waveform FFT filtering
and reconstruction produce the same output observable within the tested error
bounds. Different transmitters do not share waveform transforms or substituted
input spectra. Delay/Doppler limits remain explicit errors, including zero-gain
out-of-range paths.

The GPU renderer chooses temporal rank from the maximum absolute Doppler of all
current paths and the interpolation error bound. Higher Doppler can require
higher rank and higher cost. Warp subgroup width follows rank; it does not discard
paths. Reused buffers clear uncovered padding and overwrite current source
regions. Scene-specific delay trimming, single-precision delay maps, alternate
FFT shapes and fused projection remain experimental controls, disabled in the
live workflow.

The original CPU basis experiment and 22× synthetic renderer comparison are in
[the dated research record](archive/rendering-research.md#doppler-basis-fft).
That number does not describe current fleet speed or real-time execution.

<a id="direct-path-rendering"></a>

## Direct sampled reference

Direct rendering evaluates each valid path against each output sample with its
complex gain, phase, fractional delay and Doppler. It is an expensive reference,
with work proportional to paths × samples × interpolation support. It is useful
for checking new representations and unusual waveforms, not as a substitute
for end-to-end throughput measurements. Tone-specific optimizations are not a
claim that arbitrary waveform rendering is equally cheap.

<a id="batched-rendering"></a>

## Receiver integration and continuity

Receivers sum private link outputs before continuous filtering, noise and ADC.
Split captures preserve filter state; contiguous timestamps must remain aligned
with sample counts. Epoch-relative phase avoids loss of precision at large Unix
timestamps. The live file source is finite and zero outside its explicit support.
The basis path currently requires equal nominal transmitter and receiver sample
clocks. Independent LO phase/frequency terms remain separate from that sample-clock
restriction.

Tests exercise changing delays, zero gains, high Doppler/rank, interpolation
boundaries, split captures, large epochs, subgroup widths and private inputs.
Scene-based comparisons check direct/basis I/Q and ADC agreement; synthetic tests
exercise unfavorable bounds independently of terrain. These qualify a numerical
operator, not surface reflectivity, real-world receiver behavior or every
possible deployment. [Tests](../tests) and [qualification evidence](performance.md)
are the acceptance sources.

<a id="independent-tx-optimization"></a>

## Optimization claims and reproduction

A renderer speedup must state path count, private input count, output samples,
rate/duration, declared delay/Doppler ranges, precision, block size and timer
boundary. GPU event spans and synchronized downloads are diagnostic; queued work
can shift into the synchronizing call. Report complete unprofiled service against
signal duration separately from instrumented per-stage measurements.

The timing harness uses an immutable scene with XML/mesh hashes and full-interval
clearance bounds. A different terrain, antenna, waveform or sampling budget is a
new workload. Preserve failed qualification results and compare identical inputs
before promoting a change.

Current next steps concern representative input/device-transfer workloads and
live interoperability. The [historical research record](archive/rendering-research.md)
retains completed implementation steps, old CPU measurements and experimental
controls. Do not read that record's original roadmap as current missing features.
