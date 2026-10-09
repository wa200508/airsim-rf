# All-path Doppler-basis FFT CPU experiment

**Timing scope:** Renderer-call wall service or separately labeled projection/kernel-call experiment; excludes propagation and receiver processing. [Common measurement definitions](../../TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [research_results/doppler_basis_cpu/delay_1000us.json](delay_1000us.json) — Renderer call (basis) | historical | 5 | 8.333500 | 0.041668 | 0.238805 | 5.731 |
| [research_results/doppler_basis_cpu/doppler_25000.json](doppler_25000.json) — Renderer call (basis) | historical | 5 | 8.333500 | 0.041668 | 1.420582 | 34.093 |
| [research_results/doppler_basis_cpu/four_links.json](four_links.json) — Renderer call (basis) | historical | 5 | 8.333500 | 0.041668 | 0.652329 | 15.656 |
| [research_results/doppler_basis_cpu/four_links.json](four_links.json) — Renderer call (direct) | historical | 5 | 8.333500 | 0.041668 | 14.566788 | 349.596 |
| [research_results/doppler_basis_cpu/one_link.json](one_link.json) — Renderer call (basis) | historical | 5 | 8.333500 | 0.041668 | 0.164990 | 3.960 |
| [research_results/doppler_basis_cpu/one_link.json](one_link.json) — Renderer call (direct) | historical | 5 | 8.333500 | 0.041668 | 3.473311 | 83.358 |
| [research_results/doppler_basis_cpu/paths_4096.json](paths_4096.json) — Renderer call (basis) | historical | 5 | 8.333500 | 0.041668 | 0.403660 | 9.688 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->


See [model, scaling, timings and limits](../../DOPPLER_BASIS_FFT.md).

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
