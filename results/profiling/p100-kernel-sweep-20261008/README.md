# P100 GPU execution controls: p100-kernel-sweep-20261008

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

[Full qualified outcome](../p100-adaptive-pipeline-full-20261008/FINDINGS.md) · [Measurement definitions](../../../docs/timing.md#timing-conventions).

Measurement units and scope: [timing definitions](../../../docs/timing.md); [wall cost per simulated signal second](../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
