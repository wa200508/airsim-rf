# End-to-end RF pipeline result

**Timing scope:** RF fleet-update wall service; stage columns are independent statistics. [Common measurement definitions](../../../../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are in milliseconds per complete fleet update.**

Measurement mode: instrumented_end_to_end_profile. Instrumented runs are separate from throughput results.

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 TX × 10 RX, basis-cuda; trajectory source | 0.00 ± 0.00 | 38.23 ± 1.87 | 51.53 ± 1.74 | 401.01 ± 4.93 | 8.79 ± 0.96 | 68.28 ± 3.28 | 7.32 ± 0.69 | 575.80 ± 8.68 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 TX × 10 RX, basis-cuda; trajectory source | 0.00 | 42.55 | 54.65 | 406.99 | 10.95 | 73.13 | 8.71 | 591.28 |

Measured windows: 30; simulated duration: 250.0000 ms.

Wall time / simulated time: **69.30×**. Deadline misses: 30/30.

Propagation backend: Sionna RT CUDA/OptiX. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).

Measurement units and scope: [timing definitions](../../../../../docs/timing.md); [wall cost per simulated signal second](../../../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
