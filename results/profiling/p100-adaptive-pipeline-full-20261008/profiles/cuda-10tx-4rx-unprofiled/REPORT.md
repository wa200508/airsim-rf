# End-to-end RF pipeline result

deterministic AirSim-contract trajectory; physics/RPC not exercised.

**All stages are wall milliseconds per RF fleet update, generating ~8.333 ms of signal per receiver.**

Measurement mode: unprofiled_end_to_end_benchmark. Instrumented runs are separate from throughput results.

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 TX × 4 RX, basis-cuda; trajectory source | 0.00 ± 0.00 | 3.90 ± 0.23 | 10.71 ± 0.64 | 27.75 ± 0.54 | 2.89 ± 0.14 | 4.63 ± 0.24 | 3.19 ± 0.26 | 53.45 ± 1.28 |

## p95

| Configuration / stage (ms) | advance_ms | source_ms | channel_ms | rendering_ms | receiver_ms | other_rf_ms | delivery_storage_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 TX × 4 RX, basis-cuda; trajectory source | 0.00 | 4.39 | 11.95 | 28.80 | 3.14 | 5.03 | 3.76 | 56.10 |

Measured updates: 30; actual signal duration per receiver: 0.250000 seconds; total measured fleet wall service: 1.608367 seconds.

Wall seconds / simulated signal second: **6.43×**. Deadline misses: 30/30.

Propagation backend: Sionna RT CUDA/OptiX. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.

Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.

Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.

[Raw captures and per-step measurements](measurements.json).

Measurement units and scope: [timing definitions](../../../../../docs/timing.md); [wall cost per simulated signal second](../../../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
