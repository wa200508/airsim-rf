<a id="timing-conventions"></a>

# Timing and measurement conventions

A time must name its **operation, clock, workload, backend, statistic and sample count**. A GPU backend label identifies where a stage executes; its synchronized wall time also includes host preparation, dispatch, synchronization and transfers. It is not a GPU kernel time or a median across the test suite.

| Scope | Timed operation | Work outside this timer |
| --- | --- | --- |
| Renderer call | Validate/pack supplied channels and private input waveforms, upload, construct delay/temporal filters, project paths, private FFT convolution, coherent sum and synchronized output download | Source/channel generation, ray tracing, receiver noise/filter/ADC, simulator and delivery |
| Local RF service call | Local pose writes, synchronized propagation/export, rendering and receiver processing, as specified by that historical harness | Live simulator RPC/physics, queues, network consumer and storage |
| RF fleet update | Trajectory/mount mapping, private source generation/copies, propagation/export, rendering, continuous receiver noise/filter/ADC, loopback HTTP acknowledgement and SC16 write/readback for all receivers | Initialization, live AirSim physics/RPC for trajectory runs, WAN/native distributed workers, unequal-clock resampling and durable fsync |
| Propagation call | Proposals/sampling, intersections, fields and synchronized channel export for the configured links | Signal rendering and receiver processing; scaling-only runs may also exclude pose/source work |
| CUDA event span | Device-clock interval between recorded events for a named stage | Not equivalent to isolated kernel execution: dispatch/idle gaps can lie between events |
| Dr.Jit event history | Recorded native operations, with execution/code generation/backend compilation reported separately | CuPy renderer/counter operations and other host work; overlapping/nested records are not an additive wall-time breakdown |

The exact harness/JSON defines boundaries when it differs from this table. A report must state that difference. “End-to-end” means the listed RF stages, never an implicit live simulator, long flight or distributed deployment.

For the latest 100-TX × 10-RX P100 measurement, **371.859 ms is the unprofiled median synchronized wall service time for one RF fleet update**, generating about 8.333 ms of signal per receiver. Thirty measured updates cover 0.250 signal seconds per receiver and consume 11.1696 wall seconds: **44.678 wall seconds per signal second**. Ten receiver jobs execute serially, but their signal durations are concurrent and count once. These are warmed trajectory-source RF updates, not a live AirSim flight. [Current scope, stack and qualification](performance.md). The earlier 553.685 ms median used the same GPU dependency stack and is a matched workload control. The 843.630 ms result used LLVM propagation and different dependencies; that comparison cannot isolate an optimization gain.

Report wall times in **ms per named operation**. State TX/RX, output samples/rate, attempts versus actual valid paths, precision, declared delay/Doppler support and tolerance, hardware, dependency versions, worker limits and source revision. A configured update frequency or RF sample rate does not prove wall-clock throughput. Synthetic 1,028 valid paths/link are a different workload from 1,028 diffuse attempts/link producing variable scene returns.

Use unprofiled repeated calls for service time and throughput. Label instrumented series separately. Report median, sample SD (n−1), p95 with linear interpolation and n **per case**, not pooled across the suite. Single captures have no SD or qualified tail distribution. Small samples remain screening evidence; thirty updates are not long-run tail or sustained-flight qualification. Report first use and warmup separately. Excluding startup does not exclude recurring JIT compilation within a timed call; record cache reuse between processes and whether epochs repeat.

Sum each stage across links/blocks/receivers **within an update**, then calculate its statistics. Independently calculated stage medians/p95 do not sum to the total median/p95. Subtotals and nested host ranges must not be counted twice. Missing/unmeasured stages are unavailable, not zero. Percentages need matched per-update components and denominators; ratios of separate medians are descriptive, not exact per-update attribution.

**Serial throughput = n / sum(service seconds). Wall/simulated-time ratio = sum(service seconds) / sum(samples per receiver / sample rate)** for concurrent receivers. Deadline misses compare each update's service time with its actual signal duration (or explicitly named scheduling deadline). Renderer-only ratios describe renderer capacity. Historical fixed-16,667-sample reports used the nominal 120-Hz scheduling denominator; this is a scheduling-cost ratio, slightly different from the exact sample-duration ratio. Ten-minute costs extrapolate mean service cost over the assumed update count; they are not measured flights. Delivery latency additionally includes source accumulation, interpolation lookahead, queueing and transport outside the timer.

Claim an optimization gain only from a matched control: same scene epochs, sample/path/support budgets, model/precision, hardware, backend/versions, worker settings, qualification, instrumentation and comparable cache/GPU contention state. Name any changed dimension. Cold versus reused disk-cache results cannot isolate an algorithm change. Record failed runs as diagnostics without assigning successful throughput or extrapolated latency.

Correctness qualification is separate from speed. Distinguish final-window numerical reference checks, per-update continuity/hash/range checks, solver/integration tests and untested live deployment. Telemetry is sampled whole-device utilization/memory and can miss short activity; 0% sampled utilization does not establish zero GPU execution.

Regenerate the single measurement index with `python3 scripts/update_timing_context.py`; verify it with `--check`. The runtime and stage table generators have their own `--check` commands. Normalization reads recorded samples and never reruns or changes numerical measurements.
