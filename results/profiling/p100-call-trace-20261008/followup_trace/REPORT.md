# End-to-end RF pipeline result

deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are wall milliseconds per RF fleet update, generating ~8.333 ms of signal per receiver.**

Measurement mode: instrumented_end_to_end_profile. Instrumented runs are separate from throughput results.

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 TX × 10 RX, basis-cuda; trajectory source | 0.00 ± 0.00 | 39.16 ± 0.71 | 32.83 ± 1.28 | 242.50 ± 5.67 | 9.57 ± 0.98 | 81.65 ± 4.47 | 10.31 ± 0.72 | 419.24 ± 6.41 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 TX × 10 RX, basis-cuda; trajectory source | 0.00 | 40.36 | 34.99 | 252.30 | 11.25 | 89.22 | 11.70 | 427.58 |

Measured updates: 10; actual signal duration per receiver: 0.083333 seconds; total measured fleet wall service: 4.187018 seconds.

Wall seconds / simulated signal second: **50.24×**. Deadline misses: 10/10.

Propagation backend: Sionna RT CUDA/OptiX. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).

Measurement units and scope: [timing definitions](../../../../docs/timing.md); [wall cost per simulated signal second](../../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
