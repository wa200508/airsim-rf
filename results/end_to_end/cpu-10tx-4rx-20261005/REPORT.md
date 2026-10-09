# End-to-end RF pipeline result

**Timing scope:** RF fleet-update wall service; stage columns are independent statistics. [Common measurement definitions](../../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are in milliseconds per complete fleet update.**

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 TX × 4 RX, basis-cpu; trajectory source | 0.00 ± 0.00 | 6.08 ± 0.59 | 105.79 ± 32.76 | 493.21 ± 18.24 | 4.57 ± 1.25 | 7.24 ± 0.78 | 6.47 ± 1.21 | 620.59 ± 32.69 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 TX × 4 RX, basis-cpu; trajectory source | 0.00 | 7.04 | 126.51 | 520.59 | 6.85 | 8.56 | 8.90 | 654.25 |

Measured windows: 10; simulated duration: 83.3335 ms.

Wall time / simulated time: **73.84×**. Deadline misses: 10/10.

Scene propagation is CPU even when rendering uses CUDA. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).

Measurement units and scope: [timing definitions](../../../docs/timing.md); [wall cost per simulated signal second](../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
