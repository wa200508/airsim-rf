# End-to-end RF pipeline result

deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are wall milliseconds per RF fleet update, generating ~8.333 ms of signal per receiver.**

Measurement mode: unprofiled_end_to_end_benchmark. Instrumented runs are separate from throughput results.

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 TX × 10 RX, basis-cuda; trajectory source | 0.00 ± 0.00 | 38.27 ± 0.60 | 30.97 ± 1.41 | 438.68 ± 5.99 | 9.24 ± 0.78 | 67.82 ± 3.88 | 7.37 ± 0.70 | 592.58 ± 7.67 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 TX × 10 RX, basis-cuda; trajectory source | 0.00 | 39.31 | 33.81 | 448.42 | 10.58 | 74.70 | 8.86 | 603.15 |

Measured updates: 30; actual signal duration per receiver: 0.250000 seconds; total measured fleet wall service: 17.800179 seconds.

Wall seconds / simulated signal second: **71.20×**. Deadline misses: 30/30.

Propagation backend: Sionna RT CUDA/OptiX. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).

Measurement units and scope: [timing definitions](../../../../docs/timing.md); [wall cost per simulated signal second](../../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
