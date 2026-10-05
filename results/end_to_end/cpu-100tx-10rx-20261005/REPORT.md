# End-to-end RF pipeline result

deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are in milliseconds per complete fleet update.**

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 TX × 10 RX, basis-cpu; trajectory source | 0.00 ± 0.00 | 54.18 ± 2.30 | 1186.28 ± 108.43 | 10615.41 ± 429.41 | 12.07 ± 0.26 | 88.65 ± 1.96 | 15.09 ± 3.19 | 11986.07 ± 499.77 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 TX × 10 RX, basis-cpu; trajectory source | 0.00 | 57.73 | 1353.06 | 11108.16 | 12.20 | 89.48 | 20.94 | 12571.09 |

Measured windows: 5; simulated duration: 41.6670 ms.

Wall time / simulated time: **1443.79×**. Deadline misses: 5/5.

Scene propagation is CPU even when rendering uses CUDA. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).
