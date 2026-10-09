# Legacy harness exploratory smoke run

**FAILED / INCOMPLETE — diagnostic archive, superseded by the full legacy collection.**

This used Sionna 0.19.2 / Mitsuba 3.5.2 / Dr.Jit 0.4.6 / TensorFlow 2.15.1. The external compatibility adapter was being repaired during this run; CPU and 2-TX tasks failed. The adapter revision was not archived per task. Do not use this mixed run for paired performance comparisons or scientific equivalence claims.

The collector originally generated current-solver annotations in the raw JSON/profile summary. Those workload estimates and zero-valued compatibility sampling timers do not describe the legacy solver. CUDA event histories exclude TensorFlow kernels. The original artifacts are retained as diagnostics only.

[Completed full legacy collection](../p100-legacy-full-20261003/REPORT.md) contains the frozen harness, complete task set and corrected scope.

| Task | Outcome |
|---|---|
| cuda_preflight | ok |
| cpu_2tx_1rx | failed |
| cuda_2tx_1rx | failed |
| cuda_2tx_1rx_events | failed |
| nsys_2tx_1rx | unavailable |
| cpu_100tx_1rx | failed |
| cuda_100tx_1rx | ok |
| cuda_100tx_1rx_events | ok |
| nsys_100tx_1rx | unavailable |
| pluto_example | ok |

[Manifest](manifest.json) · [Logs](logs) · [Checksums](checksums.json)
