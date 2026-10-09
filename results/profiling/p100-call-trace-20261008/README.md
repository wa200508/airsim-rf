# P100 execution call trace and FFT diagnostics

**Timing scope:** separate instrumented 100-TX × 10-RX RF fleet traces, ten measured updates each covering **0.083333 simulated signal seconds**. Each update covers ~8.333 ms per receiver. cProfile covers the main-thread measured phase plus between-update bookkeeping; CUDA events are device-clock spans including possible dispatch gaps. Neither substitutes for the unprofiled fleet cost. Startup/warmup are excluded. Sources, geometry, paths, receiver state and loopback delivery change/run normally.

The call chain is `benchmark.run → AirSimSDRBridge.capture → SDRNetworkReceiver.capture → solver/CIR export`, then per receiver `SampledWaveform` private copies, `CudaDopplerBasisRenderer.render → _pack → delay sorting → temporal coefficients → project → private FFTs → reconstruct/sum → asnumpy`, followed by noise/filter/ADC and HTTP delivery/readback.

The original trace attributes 2.280 seconds across 100 `asnumpy/get` calls; the follow-up attributes 0.659 seconds. These are queue-draining waits, not measured PCIe download costs. Separate export event spans are about **0.91 ms per fleet update** generating **8.333 ms of signal**. Do not add inclusive call times or interpret the largest blocking call as the underlying kernel.

| Separate trace: stage CUDA-event median | Original ms / fleet update | Follow-up ms / fleet update |
| --- | ---: | ---: |
| Pack/upload span (includes host work/gaps) | 109.57 | 105.89 |
| Delay map | 20.89 | 20.98 |
| Temporal coefficients | 21.44 | 9.64 |
| Path projection | 86.24 | 42.50 |
| Private FFT filters | 150.69 | 48.04 |
| Reconstruction/sum | 16.74 | 7.03 |
| Export | 0.92 | 0.91 |

Each row is a component cost for the same ~8.333 ms signal interval. Stage medians are from separate instrumented runs and are not additive unprofiled fleet service. Adaptive actual-Doppler rank and subgroup projection address real GPU work; avoiding redundant full source clears addresses host preparation. Source generation (~38 ms/update), immutable private waveform cloning/validation (~44 ms/update in the follow-up function trace), host packing, and propagation remain substantial. cProfile attribution includes synchronization and Python/native transitions; wall timers and events provide the complementary boundaries.

The isolated FFT helper tests 100 private transforms with rank 8/27, 2,048 nominal output samples (1.024 ms nominal signal interval), synthetic filter data and no propagation/projection/receiver/delivery. For rank 8/support 35, 2,100-point filtering averaged 1.251 ms/chain (1.22 wall s per nominal signal s for this component); 2,304 points averaged 0.658 ms (0.64). This is a diagnostic component ratio, not measured RF throughput. CPU-oriented fast-length choices can be slower for cuFFT despite fewer points. Corrected padding repaired the trimmed-filter regression, but the default keeps full declared support because its extra end-to-end gain was marginal.

[Original call statistics](trace/python_calls.txt) and [follow-up call statistics](followup_trace/python_calls.txt) list cumulative/internal timings and callees. [FFT lengths](fft_lengths.json) retain all twenty-repeat wall/event results, after three warmups. Profiling binaries stay in ignored `raw/`. Qualification logs record 116, 131 and finally 147 passing renderer/reporting tests as changes accumulated; these counts overlap and must not be summed. Thirteen new adaptive tests, thirteen trimming tests and sixteen subgroup/padding tests cover full range, high rank, zero-gain paths, Unix epochs, split captures, private outputs, changed data, boundary padding and error guards. Final full collector integration/worker outcomes are separate.

The published full collection is [here](../p100-adaptive-pipeline-full-20261008/FINDINGS.md). No Nsight kernel-instruction attribution is claimed. Ollama was paused during measurements and restored afterward; other GPU-resident services were idle. See [common definitions](../../../TIMING_CONVENTIONS.md).

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [results/profiling/p100-call-trace-20261008/followup_trace/measurements.json](followup_trace/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 10 | 8.333300 | 0.083333 | 4.187018 | 50.244 |
| [results/profiling/p100-call-trace-20261008/trace/measurements.json](trace/measurements.json) — RF fleet update | instrumented_end_to_end_profile | 10 | 8.333300 | 0.083333 | 5.920980 | 71.052 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->
