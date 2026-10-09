# Qualified adaptive P100 CUDA RF pipeline

| TX × RX | Simulated signal s | Measured wall s | Wall s / simulated signal s | Median wall ms/update | p95 wall ms/update |
| --- | ---: | ---: | ---: | ---: | ---: |
| [100 × 10](profiles/cuda-100tx-10rx-unprofiled/measurements.json) | 0.250000 | 11.169603 | 44.678 | 371.859 | 384.061 |
| [10 × 4](profiles/cuda-10tx-4rx-unprofiled/measurements.json) | 0.250000 | 1.608367 | 6.433 | 53.446 | 56.101 |
| [2 × 2](profiles/cuda-2tx-2rx-unprofiled/measurements.json) | 0.250000 | 0.763550 | 3.054 | 25.304 | 27.123 |

Source `197be36d3fbfda28ed74f6d80c48a4012da28259`, clean mounted code; Sionna RT 2.2.0 / Mitsuba 3.8.0 / Dr.Jit 1.3.1 / CuPy on P100. CUDA preflight, 30 integration/reporting/counter tests, seven worker-protocol correctness tests in a separate LLVM process, and all six 30-update GPU series passed. No CPU-only performance run was added. The expanded CUDA renderer/reporting suite passed 147 tests.

The prior same-stack GPU configuration used 16.5899 wall seconds for 0.250 simulated seconds (66.360 wall s/simulated s). The new default uses **11.1696 wall seconds (44.678 wall s/simulated s)**: approximately 32.7% less measured service cost. Physical path-count maps and sample counts match that prior collection. Matched controls isolate adaptive rank and projection grouping separately; this comparison summarizes the combined code changes, not a CPU-to-GPU backend switch.

Target mean stage costs per ~8.333 ms signal update: source generation 38.031 ms, GPU propagation/export 30.438 ms, renderer call 220.678 ms, receiver processing 8.934 ms, bridge/private waveform preparation/other RF work 66.894 ms, and loopback delivery/readback 7.340 ms. These are matched means; rendering remains about 59.3% of measured service. GPU renderer wall time includes host packing and waits, not just kernels. Independently calculated medians and CUDA-event spans must not be added to the unprofiled total.

Every instrumented target update records four OptiX-enabled events. Backend compilation time and missing cache-hit metadata are distinct fields; missing flags are no longer counted as compilation misses in new captures.

Adaptive rank and automatic projection groups are enabled for `SDRNetworkReceiver(renderer="basis-cuda")` and the end-to-end GPU collector. The standalone CUDA renderer retains its fixed-range default for historical benchmark controls. Declared validation limits, all paths, all private traffic/transforms, precision, tolerance, noise/filter/ADC, sample continuity and actual consumer delivery are preserved. All scenarios still miss all 30 120-Hz deadlines.

Tracing identifies FFT filtering, projection, host waveform copies/packing and GPU-queue waits as the major costs. The final target still uploads about 286.6 MB of private input/channel data per update; its host PCIe link reports Gen3 ×8. Device-resident/private ingestion and overlapping preparation are candidates for the next investigation, requiring explicit traffic accounting and correctness checks.

[Call trace and diagnostic evidence](../p100-call-trace-20261008/README.md) · [Complete stage distributions](REPORT.md) · [Timing definitions](../../../docs/timing.md#timing-conventions).

Measurement units and scope: [timing definitions](../../../docs/timing.md); [wall cost per simulated signal second](../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
