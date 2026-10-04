# Profiling result bundles

Use [P100_PROFILING.md](../../P100_PROFILING.md) to collect measurements.
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
