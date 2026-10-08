# P100 complete RF pipeline findings

Measured source: `b70637d4cdec31edbd051c71b85f15b758b087e4`, clean build. All 11 required tasks passed: CUDA preflight, 35 integration tests, three CPU unprofiled series, three CUDA unprofiled series, and three separate CUDA instrumented series. Every series has 30 timed windows after first use and three warmups, representing 250 ms of simulated signal. This is not a sustained real-time or long-flight qualification.

| TX / RX | CPU median ms | P100 hybrid median ms | CPU / hybrid ratio | Hybrid p95 ms |
|---|---:|---:|---:|---:|
| 2tx-2rx | 72.217 | 24.045 | 3.00 | 26.480 |
| 10tx-4rx | 375.551 | 65.192 | 5.76 | 67.897 |
| 100tx-10rx | 7348.740 | 843.630 | 8.71 | 860.181 |

All hybrid cases miss the 120 Hz deadline in all 30 measured windows. The target 100-TX/10-RX fleet executes 101.43 times slower than simulated time. Receivers execute serially on one P100; no receiver-parallel speedup is credited.

Target hybrid median stages are rendering 392.762 ms, LLVM CPU propagation 330.469 ms, private sources 37.848 ms, bridge/other RF work 66.550 ms, noise/filter/ADC 8.556 ms, and delivery/storage 7.410 ms. Independently calculated stage medians need not add to the total median. Propagation uses Sionna RT 2.2.0 on LLVM CPU for both backends, while P100 CUDA runs CuPy rendering. This collection does not use legacy Sionna. The historical legacy measurements retain their separate scope.

CPU and CUDA cases retained identical physical path counts at matching epochs. Target links have 199–388 returns, median 293 across link/window observations. The 1,028 diffuse attempts per link are not 1,028 valid returns, so these numbers are not directly comparable to the synthetic all-valid-path stress test. The different CPU propagation wall times with CPU versus CUDA rendering remain unisolated; they must not be described as CUDA ray-tracing acceleration.

Repeated instrumented target-fleet event spans have medians: pack/upload 119.437 ms, delay map 19.790 ms, temporal construction 24.664 ms, projection 57.101 ms, private FFT filters 150.876 ms, reconstruction/sum 16.780 ms, and export 0.841 ms. Each stage is summed over receivers/blocks within a window, then summarized across 30 windows. Events include dispatch gaps, are not pure kernel times, and come from separate instrumented runs. Do not mix them into unprofiled throughput. [REPORT.md](REPORT.md) contains all median, standard-deviation and p95 tables.

The pipeline includes fresh private continuous I/Q, the pose/mount bridge, terrain multipath, persistent filtering/noise/12-bit ADC, loopback HTTP acknowledgements, and consumer file write/readback. Deterministic trajectories implement the AirSim interface; live AirSim physics/RPC, WAN/AMS-GRA workers, clock-rate resampling and fsync durability remain outside this qualification. Integration tests compare moving-scene basis rendering to the direct all-path oracle and test receiver continuity. Benchmark windows check sample accounting, shapes/finiteness, retained paths, ADC payload limits, hashes and file readback; they do not each run a full-fleet direct numerical oracle.

The unfinished persistent-buffer/fused-projection experiment was saved in Git stash before updating the branch. It is not part of the measured source or these results. Raw SC16 captures remain local and ignored; reports, measurements, logs, hardware/source metadata, and compressed telemetry are published.
