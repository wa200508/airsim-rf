# Optimized P100 GPU RF pipeline findings

**Timing scope:** RF fleet-update wall service; serial receivers; trajectory source and loopback consumer. [Common measurement definitions](../../../docs/timing.md#timing-conventions) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.
Measured source: `6cc6707`; clean code mounted read-only over the isolated compatibility image. Propagation and signal rendering both execute on the P100. All required collector tasks and all six 30-window CUDA series passed. Initialization, the first capture and three warmups are excluded from steady-state tables; each measured series contains 250 ms of simulated signal. No CPU-only end-to-end timing run was added.

| TX / RX | Fleet-update wall median ms | p95 ms | Propagation wall median ms | Renderer-call wall median ms |
|---|---:|---:|---:|---:|
| 2tx-2rx | 26.772 | 28.206 | 9.363 | 11.861 |
| 10tx-4rx | 61.692 | 64.455 | 10.670 | 35.264 |
| 100tx-10rx | 553.685 | 563.363 | 31.222 | 398.267 |

The current configuration measures 553.685 ms per fleet update; the earlier hybrid CPU-propagation/P100-rendering configuration measured 843.630 ms. The backend, Mitsuba/Dr.Jit stack and optimization settings changed. These are two configuration measurements, not a controlled 1.52× optimization speedup. Each update generates ~8.333 ms of signal per receiver, with ten receivers processed sequentially on one P100. The small 2-TX/2-RX case is slower than the prior hybrid result (26.772 vs 24.045 ms); GPU traversal does not automatically benefit small fleets.

GPU-specific opaque pose inputs address recurring JIT work: the preceding new-trajectory CUDA run measured 1,259.17 ms total and 740.88 ms propagation, while reusing its epochs measured about 576 ms total. With changing pose arrays materialized rather than embedded as compiler literals, the final new-trajectory run measured 31.223 ms propagation. Positions, velocities, orientations and channels are still updated every window. [Comparisons and qualification](../p100-gpu-system-20261007/README.md) retain cold/warm-cache differences and all provisional failures.

Actual backend evidence: `cuda_ad_mono_polarized`, Sionna RT 2.2.0, Mitsuba 3.8.0, Dr.Jit 1.3.1, P100 compute capability 6.0. Every instrumented target window records four OptiX-enabled events, not merely successful CUDA library loading. Dr.Jit history excludes the CuPy atomic counter and CuPy renderer operations. Its event spans are not the full propagation wall time. `cache_misses` in this collection counts entries with a false or missing cache-hit field and must not be interpreted as a count of compiled kernels; actual median recorded backend compilation time is zero in the instrumented target run.

The default keeps the original material/scattering model, every physical path, 1,028 attempts per directed link, independent source allocations/FFTs, 2 MS/s, 120 Hz integer sample accounting, continuous receive state and FP64/complex128 rendering. Storage padding adds no physical paths and changes no supplied delays/Dopplers. The ray-index workaround uses CUDA uint32 atomics; it is not a CPU path-construction fallback. Sionna propagation retains its native floating-point precision.

Remaining work is mostly signal rendering: 398.271 ms per target fleet update. Host source generation, path export/private input preparation, noise/filter/ADC, bridge/control and loopback delivery/storage remain included host stages. This is not a claim that every operation runs on GPU. Receivers execute serially on one P100. All configurations miss 120 Hz in all thirty measured windows; 553.685 ms is about 66.4 times the 8.333 ms fleet deadline. Live AirSim physics/RPC, WAN/AMS-GRA worker execution and clock-rate resampling remain unqualified.

The isolated environment is reproducible with:

```bash
bash scripts/run_p100_docker.sh --end-to-end --p100-gpu --run-id p100-gpu-full
```

The launcher builds the pinned profiling image, applies only the explicit Mitsuba/Dr.Jit compatibility wheels, provides writable old-Dr.Jit cache storage, and requests CUDA propagation without fallback. Raw SC16 captures remain local and ignored. Ollama was restored after profiling.

Measurement units and scope: [timing definitions](../../../docs/timing.md); [wall cost per simulated signal second](../../../docs/measurements.md). Historical and instrumented records retain their original qualification.
