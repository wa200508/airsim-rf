# End-to-end RF pipeline result

deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are wall milliseconds per RF fleet update, generating ~8.333 ms of signal per receiver.**

Measurement mode: unprofiled_end_to_end_benchmark. Instrumented runs are separate from throughput results.

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 TX × 2 RX, basis-cuda; trajectory source | 0.00 ± 0.00 | 0.86 ± 0.03 | 9.17 ± 0.36 | 11.38 ± 0.40 | 1.54 ± 0.16 | 1.42 ± 0.04 | 1.83 ± 0.13 | 25.92 ± 0.56 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 TX × 2 RX, basis-cuda; trajectory source | 0.00 | 0.86 | 9.41 | 11.53 | 1.70 | 1.48 | 1.90 | 26.50 |

Measured updates: 3; actual signal duration per receiver: 0.025000 seconds; total measured fleet wall service: 0.077947 seconds.

Wall seconds / simulated signal second: **3.12×**. Deadline misses: 3/3.

Propagation backend: Sionna RT CUDA/OptiX. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).
