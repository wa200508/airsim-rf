# Profiling result bundles

Use [P100_PROFILING.md](../../P100_PROFILING.md) to collect measurements.
Each run has its own directory, Markdown report, environment and raw JSON.
Publish with `scripts/publish_gpu_results.py`; large `raw/` artifacts stay local.
CPU-only validation reports and GPU compatibility failures must remain labelled
as such. Do not turn a CUDA selection flag into a GPU-performance claim.
