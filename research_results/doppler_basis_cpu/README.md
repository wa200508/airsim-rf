# All-path Doppler-basis FFT CPU experiment

**Timing scope:** Renderer-call wall service or separately labeled projection/kernel-call experiment; excludes propagation and receiver processing. [Common measurement definitions](../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
See [model, scaling, timings and limits](../../docs/rendering.md#doppler-basis-fft).

Measurements use a dirty tree based on
`8c26c902a8a06cf341162ce550f4f31a8e8665ac`. Each JSON records hashes of the new
research implementation, benchmark and direct reference. No CUDA timing was
collected. All supplied paths are valid and every call rebuilds path-dependent
state. No inputs or transforms are shared across independent jobs.

`one_link.json` and `four_links.json` alternate matched basis/direct timings,
after two warmups, with five unprofiled captures each. The other three JSONs
time the basis renderer only; they include a separately computed direct
full-output accuracy reference. Source generation, propagation, sample-clock
resampling, mandatory receiver frontend and transport are excluded. Equal
sample clocks are an explicit limitation, not a complete clock implementation.

The first-link accuracy reference covers every supplied path and all 16,667
output samples. Finite interpolation is shared by the operators; ideal sinc
and physical noise-floor accuracy need separate qualification. These timings
do not establish throughput or latency for 1,000 links or an integrated RF
receiver. Source hashes refer to the final measured code; documentation and
tests can subsequently change without changing the measurement.

Final validation: **128 passed, 22 skipped** in both the host venv and an
offline nonroot profiling container. The container used the pinned dependency
image from the preceding implementation, with the new research module and final
test files mounted read-only and temporary files in memory. CUDA tests were
skipped because no GPU is available. Eight new tests cover full direct-output
agreement, arbitrary private inputs, changing channels, split capture
continuity, finite zero boundaries, cancellation with opposite Dopplers,
Unix-scale timestamps and rejection of unqualified clocks/ranges.

Measurement units and scope: [timing definitions](../../docs/timing.md); [wall cost per simulated signal second](../../docs/measurements.md). Historical and instrumented records retain their original qualification.
