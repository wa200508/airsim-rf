# Profiling result bundles

**Timing scope:** Mixed scope or architecture/reference document; each workload/table retains its stated timed operation. [Common measurement definitions](../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
Use [P100_PROFILING.md](../../docs/setup.md#p100-profiling) to collect measurements.
Each run has its own directory, Markdown report, environment and raw JSON.
Publish with `scripts/publish_gpu_results.py`; large `raw/` artifacts stay local.
CPU-only validation reports and GPU compatibility failures must remain labelled
as such. Do not turn a CUDA selection flag into a GPU-performance claim.

## P100 measurements collected on 2026-10-03/04

- [Pinned-stack compatibility failure](p100-quick-20261003-2005/REPORT.md)
- [Exploratory legacy smoke run, incomplete](p100-legacy-quick-20261003/REPORT.md)
- [Full legacy CPU/CUDA service collection](p100-legacy-full-20261003/REPORT.md)
- [Legacy propagation-only scaling](p100-legacy-scaling-20261003/REPORT.md)

The working P100 stack uses Sionna 0.19.2 native propagation; current Sionna
2.2/custom-solver performance cannot be inferred from it. See the
[legacy harness](../../scripts/p100_legacy/README.md). The full run identifies
the host I/Q bottleneck; scaling omits I/Q to measure simultaneous propagation
and memory boundaries. Read each report's scope before comparing results.

## Updated CuPy Doppler-basis renderer on 2026-10-04

- [Initial quick run and startup investigation](p100-basis-quick-20261004/INVESTIGATION.md)
- [Full 30-window CPU/P100 collection](p100-basis-full-20261004/REPORT.md)
- [Findings and failed correctness qualification](p100-basis-full-20261004/FINDINGS.md)

CuPy executes FP64/complex128 rendering directly on the P100. No legacy Sionna
or ray tracing is involved. All six capture-level reference checks passed,
but the required suite failed its split-capture/Unix-timestamp test (six passes,
one failure). The overall result is **failed qualification**. At 100 TX the
observed GPU median was 122.671 ms versus 1593.948 ms on CPU; this diagnostic
renderer result misses the 8.333 ms target. See the scope and logs before use.

The [follow-up investigation](p100-basis-investigation-20261004/REPORT.md)
confirms substantial projection-kernel cost, finds no benefit from larger
link groups, and isolates the Unix-timestamp failure to oscillator-phase
rounding. It retains all workload budgets and applies no numerical repair.

Measurement units and scope: [timing definitions](../../docs/timing.md); [wall cost per simulated signal second](../../docs/measurements.md). Historical and instrumented records retain their original qualification.
