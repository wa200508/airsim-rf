# End-to-end RF pipeline result

**Timing scope:** RF fleet-update wall service; stage columns are independent statistics. [Common measurement definitions](../../../../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are in milliseconds per complete fleet update.**

Measurement mode: unprofiled_end_to_end_benchmark. Instrumented runs are separate from throughput results.

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 TX × 2 RX, basis-cuda; trajectory source | 0.00 ± 0.00 | 0.82 ± 0.14 | 9.36 ± 0.49 | 11.86 ± 0.36 | 1.38 ± 0.08 | 1.39 ± 0.11 | 1.68 ± 0.32 | 26.77 ± 0.80 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 TX × 2 RX, basis-cuda; trajectory source | 0.00 | 1.21 | 10.48 | 12.55 | 1.56 | 1.53 | 2.48 | 28.21 |

Measured windows: 30; simulated duration: 250.0000 ms.

Wall time / simulated time: **3.24×**. Deadline misses: 30/30.

Propagation backend: Sionna RT CUDA/OptiX. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).

Measurement units and scope: [timing definitions](../../../../../docs/timing.md); [wall cost per simulated signal second](../../../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
