# Legacy P100 profiling harness

**Timing scope:** Historical local RF service; model/backend and timed region are specified below. [Common measurement definitions](../../../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
This is an external adapter for repository commit 720c4011522ad25c1e9c5c470bc20f4f34d480c5. It substitutes Sionna 0.19.2 native first-order propagation while retaining repository I/Q and receiver code. Repository code and lockfiles are not edited. Original Sionna 2.2/custom-solver performance cannot be inferred from these measurements.

Container: `airsim-rf:p100-legacy-metrics`. Packages and image metadata are saved in the bundle. Start with the pinned branch profiling image (`bash scripts/run_p100_docker.sh` builds it), build the legacy Python 3.11 image with the supplied legacy Dockerfiles, then build the supplied metrics Dockerfile. The legacy image needs TensorFlow's matched CUDA 12.2 packages for GPU tensor interchange.

`sitecustomize.py` is loaded from PYTHONPATH only for the benchmark, preflight and example scripts. `launch.py` supplies the CUDA-library search path. CPU cases disable TensorFlow GPUs before legacy Sionna imports; CUDA cases use cuda_ad_rgb. Each benchmark process uses two Dr.Jit threads. Other library thread defaults are retained.

The adapter loads the unchanged terrain mesh through a temporary legacy scene XML. It sets epsilon_r=5, conductivity=.01 and scattering=.3; thickness has no legacy equivalent. Native Fibonacci tracing launches 1028 rays per TX (multiply by TX count in num_samples), not 1028 bidirectional importance-sampling attempts per link. Scattering paths are kept with probability 1 and random scatter phases disabled. The original dipole patterns, moving-platform positions and clocks are retained. Platform Doppler is supplied from legacy departure/arrival directions; no numerical equivalence validation has been run.

Full collector arguments: `--run-id p100-legacy-full-20261003 --output-root /work/results`. This runs 20 warmups/200 epochs per 2-TX backend, 5 warmups/30 epochs per 100-TX backend, separate CUDA-event profiles (3 warmups/5 epochs), hardware/package/source metadata, 1-second GPU telemetry, preflight, and the 12-epoch 2-TX/2-RX example. Nsight is optional and was absent.

After the collector exits, run `analyze_legacy.py <bundle>` to attach scope notes, remove inapplicable custom-solver workload estimates and placeholder sampling timers from summary fields, write REPORT.md, create the timing chart, and regenerate checksums. Raw timed samples and event metadata remain in the bundle. Dr.Jit histories do not include TensorFlow CUDA kernel events. Timing comparisons do not establish physical/numerical equivalence.

Measurement units and scope: [timing definitions](../../../../docs/timing.md); [wall cost per simulated signal second](../../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
