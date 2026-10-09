# End-to-end RF pipeline result

deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are wall milliseconds per RF fleet update, generating ~8.333 ms of signal per receiver.**

Measurement mode: unprofiled_end_to_end_benchmark. Instrumented runs are separate from throughput results.

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 TX × 10 RX, basis-cuda; trajectory source | 0.00 ± 0.00 | 38.33 ± 0.53 | 30.40 ± 1.45 | 696.44 ± 5.40 | 9.52 ± 0.75 | 68.10 ± 3.66 | 7.25 ± 0.68 | 850.87 ± 7.74 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 TX × 10 RX, basis-cuda; trajectory source | 0.00 | 39.19 | 33.29 | 706.63 | 10.38 | 74.71 | 8.79 | 865.72 |

Measured updates: 30; actual signal duration per receiver: 0.250000 seconds; total measured fleet wall service: 25.544428 seconds.

Wall seconds / simulated signal second: **102.18×**. Deadline misses: 30/30.

Propagation backend: Sionna RT CUDA/OptiX. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).

Measurement units and scope: [timing definitions](../../../../docs/timing.md); [wall cost per simulated signal second](../../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
