# End-to-end RF pipeline result

**Timing scope:** RF fleet-update wall service; stage columns are independent statistics. [Common measurement definitions](../../../../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are in milliseconds per complete fleet update.**

Measurement mode: unprofiled_end_to_end_benchmark. Instrumented runs are separate from throughput results.

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 TX × 2 RX, basis-cuda; trajectory source | 0.00 ± 0.00 | 0.82 ± 0.11 | 7.09 ± 0.49 | 11.52 ± 0.58 | 1.35 ± 0.07 | 1.30 ± 0.07 | 1.72 ± 0.28 | 24.04 ± 1.05 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 TX × 2 RX, basis-cuda; trajectory source | 0.00 | 1.08 | 8.21 | 12.91 | 1.49 | 1.43 | 2.18 | 26.48 |

Measured windows: 30; simulated duration: 250.0000 ms.

Wall time / simulated time: **2.93×**. Deadline misses: 30/30.

Scene propagation is CPU even when rendering uses CUDA. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).

Measurement units and scope: [timing definitions](../../../../../docs/timing.md); [wall cost per simulated signal second](../../../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
