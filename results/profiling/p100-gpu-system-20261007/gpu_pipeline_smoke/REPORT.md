# End-to-end RF pipeline result

deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are in milliseconds per complete fleet update.**

Measurement mode: unprofiled_end_to_end_benchmark. Instrumented runs are separate from throughput results.

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 TX × 2 RX, basis-cuda; trajectory source | 0.00 ± 0.00 | 0.80 ± 0.01 | 46.14 ± 0.70 | 11.93 ± 0.29 | 1.43 ± 0.02 | 1.37 ± 0.06 | 1.79 ± 0.08 | 63.47 ± 0.29 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 TX × 2 RX, basis-cuda; trajectory source | 0.00 | 0.81 | 46.58 | 12.11 | 1.45 | 1.41 | 1.84 | 63.66 |

Measured windows: 2; simulated duration: 16.6670 ms.

Wall time / simulated time: **7.62×**. Deadline misses: 2/2.

Propagation backend: Sionna RT CUDA/OptiX. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).
