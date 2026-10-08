# End-to-end RF pipeline result

deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are in milliseconds per complete fleet update.**

Measurement mode: instrumented_end_to_end_profile. Instrumented runs are separate from throughput results.

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 TX × 2 RX, basis-cuda; trajectory source | 0.00 ± 0.00 | 0.85 ± 0.15 | 9.56 ± 0.58 | 13.19 ± 0.48 | 1.44 ± 0.11 | 1.44 ± 0.13 | 1.77 ± 0.17 | 28.40 ± 1.02 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 TX × 2 RX, basis-cuda; trajectory source | 0.00 | 1.15 | 10.47 | 14.19 | 1.63 | 1.63 | 2.13 | 30.21 |

Measured windows: 30; simulated duration: 250.0000 ms.

Wall time / simulated time: **3.42×**. Deadline misses: 30/30.

Propagation backend: Sionna RT CUDA/OptiX. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).
