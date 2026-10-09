# P100 GPU execution controls: p100-kernel-sweep-20261008

**Timing scope:** 100 TX × 10 RX, sequential receivers on one P100, CUDA/OptiX propagation and CUDA rendering. Every trial processes 30 updates covering **0.250 simulated signal seconds per receiver**. Each update produces about 8.333 ms of signal. Startup/first capture/three warmups are excluded; host preparation, rendering, receiver processing and loopback HTTP/file readback remain included. No live AirSim physics/RPC or WAN workers.

| Trial / raw data | Measured signal s | Measured wall s | Wall s / simulated signal s | Renderer mean ms/update | Source revision |
| --- | ---: | ---: | ---: | ---: | --- |
| [adaptive_before](adaptive_before/measurements.json) | 0.250000 | 12.138095 | 48.552 | 252.897 | `eeb15d8fdc98b8c4042330fe845e8663c629be43` |
| [auto](auto/measurements.json) | 0.250000 | 11.077463 | 44.310 | 217.327 | `eeb15d8fdc98b8c4042330fe845e8663c629be43` |
| [auto_radix23](auto_radix23/measurements.json) | 0.250000 | 11.137921 | 44.552 | 218.136 | `eeb15d8fdc98b8c4042330fe845e8663c629be43` |
| [auto_trim_radix23](auto_trim_radix23/measurements.json) | 0.250000 | 11.035508 | 44.142 | 216.792 | `eeb15d8fdc98b8c4042330fe845e8663c629be43` |
| [auto_trim_power2](auto_trim_power2/measurements.json) | 0.250000 | 12.024273 | 48.097 | 247.260 | `eeb15d8fdc98b8c4042330fe845e8663c629be43` |
| [adaptive_after](adaptive_after/measurements.json) | 0.250000 | 12.198137 | 48.793 | 252.804 | `eeb15d8fdc98b8c4042330fe845e8663c629be43` |

All trials have matching epochs, output sample counts and physical path-count maps. All retain 1,028 diffuse attempts/link, every physical path including zero-gain returns, FP64/complex128, 32 interpolation taps, 100 µs declared delay and ±2,500 Hz Doppler validation limits, 1e-10 temporal tolerance, private input uploads and private transforms. Commands and bracketing controls are in [manifest.json](manifest.json). Processes run sequentially with shared disk JIT cache; recurring timed work remains counted. All cases miss all 30 deadlines.

Adaptive temporal rank uses the largest absolute Doppler among all current supplied paths, with the original conservative tail bound and coefficient-aliasing budget; no frequencies are rounded or averaged. Full-range inputs still require full-range work. Small numerical tests and high-rank/Unix-epoch/boundary cases passed; per-update fleet checks establish continuity, finiteness, ADC range, payload hashes and readback, not a complete numerical oracle for every fleet window.

Decision: enable adaptive rank and automatic 8/16/32-lane projection groups in the CUDA RF pipeline. Retain double sorting, full declared delay support and the existing FFT policy by default. Fused projection/single sorting showed only small gains; trimming alone was slower because the selected FFT lengths were unfavorable for cuFFT. GPU-friendly padding repaired that regression, but did not establish a worthwhile default gain.

The first aborted temporal sweep used a placeholder revision label and was excluded; its diagnostic files remain under `/tmp/p100-temporal-sweep-metadata-diagnostic-20261008`. Published trials explicitly identify their actual source revision. Ollama was paused and restored afterward. SC16 captures remain local/ignored.

[Full qualified outcome](../p100-adaptive-pipeline-full-20261008/FINDINGS.md) · [Measurement definitions](../../../TIMING_CONVENTIONS.md).

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [results/profiling/p100-kernel-sweep-20261008/adaptive_after/measurements.json](adaptive_after/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 12.198137 | 48.793 |
| [results/profiling/p100-kernel-sweep-20261008/adaptive_before/measurements.json](adaptive_before/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 12.138095 | 48.552 |
| [results/profiling/p100-kernel-sweep-20261008/auto/measurements.json](auto/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 11.077463 | 44.310 |
| [results/profiling/p100-kernel-sweep-20261008/auto_radix23/measurements.json](auto_radix23/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 11.137921 | 44.552 |
| [results/profiling/p100-kernel-sweep-20261008/auto_trim_power2/measurements.json](auto_trim_power2/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 12.024273 | 48.097 |
| [results/profiling/p100-kernel-sweep-20261008/auto_trim_radix23/measurements.json](auto_trim_radix23/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 11.035508 | 44.142 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->
