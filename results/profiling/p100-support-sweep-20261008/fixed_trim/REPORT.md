# End-to-end RF pipeline result

deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are wall milliseconds per RF fleet update, generating ~8.333 ms of signal per receiver.**

Measurement mode: unprofiled_end_to_end_benchmark. Instrumented runs are separate from throughput results.

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 TX × 10 RX, basis-cuda; trajectory source | 0.00 ± 0.00 | 38.06 ± 0.56 | 29.72 ± 1.50 | 535.27 ± 5.03 | 9.16 ± 0.73 | 69.03 ± 2.94 | 7.03 ± 0.57 | 690.05 ± 6.38 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 TX × 10 RX, basis-cuda; trajectory source | 0.00 | 38.95 | 33.61 | 541.04 | 10.28 | 73.90 | 8.34 | 699.59 |

Measured updates: 30; actual signal duration per receiver: 0.250000 seconds; total measured fleet wall service: 20.714566 seconds.

Wall seconds / simulated signal second: **82.86×**. Deadline misses: 30/30.

Propagation backend: Sionna RT CUDA/OptiX. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).

Measurement units and scope: [timing definitions](../../../../docs/timing.md); [wall cost per simulated signal second](../../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
