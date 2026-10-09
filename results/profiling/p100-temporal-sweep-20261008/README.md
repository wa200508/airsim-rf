# P100 GPU execution controls: p100-temporal-sweep-20261008

| Trial / raw data | Measured signal s | Measured wall s | Wall s / simulated signal s | Renderer mean ms/update | Source revision |
| --- | ---: | ---: | ---: | ---: | --- |
| [fixed_before](fixed_before/measurements.json) | 0.250000 | 16.563137 | 66.253 | 396.685 | `4cf6306c89fb38584d47dd9a0690f802b5af8bc2` |
| [adaptive](adaptive/measurements.json) | 0.250000 | 12.543056 | 50.172 | 264.425 | `4cf6306c89fb38584d47dd9a0690f802b5af8bc2` |
| [adaptive_single](adaptive_single/measurements.json) | 0.250000 | 12.331932 | 49.328 | 258.003 | `4cf6306c89fb38584d47dd9a0690f802b5af8bc2` |
| [fixed_single](fixed_single/measurements.json) | 0.250000 | 16.395130 | 65.581 | 393.710 | `4cf6306c89fb38584d47dd9a0690f802b5af8bc2` |
| [adaptive_fused](adaptive_fused/measurements.json) | 0.250000 | 12.563432 | 50.254 | 262.512 | `4cf6306c89fb38584d47dd9a0690f802b5af8bc2` |
| [fixed_after](fixed_after/measurements.json) | 0.250000 | 16.594010 | 66.376 | 399.102 | `4cf6306c89fb38584d47dd9a0690f802b5af8bc2` |

All trials have matching epochs, output sample counts and physical path-count maps. All retain 1,028 diffuse attempts/link, every physical path including zero-gain returns, FP64/complex128, 32 interpolation taps, 100 µs declared delay and ±2,500 Hz Doppler validation limits, 1e-10 temporal tolerance, private input uploads and private transforms. Commands and bracketing controls are in [manifest.json](manifest.json). Processes run sequentially with shared disk JIT cache; recurring timed work remains counted. All cases miss all 30 deadlines.

Adaptive temporal rank uses the largest absolute Doppler among all current supplied paths, with the original conservative tail bound and coefficient-aliasing budget; no frequencies are rounded or averaged. Full-range inputs still require full-range work. Small numerical tests and high-rank/Unix-epoch/boundary cases passed; per-update fleet checks establish continuity, finiteness, ADC range, payload hashes and readback, not a complete numerical oracle for every fleet window.

Decision: enable adaptive rank and automatic 8/16/32-lane projection groups in the CUDA RF pipeline. Retain double sorting, full declared delay support and the existing FFT policy by default. Fused projection/single sorting showed only small gains; trimming alone was slower because the selected FFT lengths were unfavorable for cuFFT. GPU-friendly padding repaired that regression, but did not establish a worthwhile default gain.

The first aborted temporal sweep used a placeholder revision label and was excluded; its diagnostic files remain under `/tmp/p100-temporal-sweep-metadata-diagnostic-20261008`. Published trials explicitly identify their actual source revision. Ollama was paused and restored afterward. SC16 captures remain local/ignored.

[Full qualified outcome](../p100-adaptive-pipeline-full-20261008/FINDINGS.md) · [Measurement definitions](../../../docs/timing.md#timing-conventions).

Measurement units and scope: [timing definitions](../../../docs/timing.md); [wall cost per simulated signal second](../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
