# End-to-end RF pipeline result

deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are wall milliseconds per RF fleet update, generating ~8.333 ms of signal per receiver.**

Measurement mode: instrumented_end_to_end_profile. Instrumented runs are separate from throughput results.

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 TX × 4 RX, basis-cuda; trajectory source | 0.00 ± 0.00 | 3.95 ± 0.16 | 11.26 ± 0.62 | 29.57 ± 0.52 | 2.99 ± 0.16 | 4.80 ± 0.37 | 3.24 ± 0.36 | 55.94 ± 1.17 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 TX × 4 RX, basis-cuda; trajectory source | 0.00 | 4.26 | 12.20 | 30.13 | 3.30 | 5.33 | 3.93 | 58.37 |

Measured updates: 30; actual signal duration per receiver: 0.250000 seconds; total measured fleet wall service: 1.682882 seconds.

Wall seconds / simulated signal second: **6.73×**. Deadline misses: 30/30.

Propagation backend: Sionna RT CUDA/OptiX. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).

Measurement units and scope: [timing definitions](../../../../../docs/timing.md); [wall cost per simulated signal second](../../../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
