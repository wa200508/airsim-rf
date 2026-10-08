# P100 CUDA propagation and rendering

The P100 can run the current Sionna RT 2.2.0 first-order terrain solver on
CUDA/OptiX with an explicit compatibility environment. The previous
end-to-end collections used LLVM CPU propagation; `basis-cuda` selected GPU
signal rendering only. These are different backend configurations.

```bash
bash scripts/run_p100_docker.sh --end-to-end --p100-gpu \
  --run-id p100-gpu-full
```

This selects CUDA propagation and rendering, builds the existing pinned
profiling environment plus `Dockerfile.p100-gpu`, and installs Mitsuba 3.8.0 /
Dr.Jit 1.3.1 from `requirements-p100-propagation.txt`. Sionna RT remains 2.2.0.
Production dependency pins remain unchanged. The older pair is an explicitly
tested compatibility configuration, not a claim of upstream support for every
Sionna feature. The launcher provides writable old-Dr.Jit cache storage without
changing the user's home directory or driver. It never silently falls back to
CPU tracing. GPU-only performance rows are collected; CPU worker protocol
fixtures run as correctness tests in a separate process.

The [final collection](results/profiling/p100-gpu-pipeline-opaque-full-20261007/FINDINGS.md)
measures 30 windows per fleet size, plus separate 30-window instrumented series.
For 100 TX / 10 RX, full median latency is **553.685 ms**, p95 **563.363 ms**,
versus **843.630 ms** for the earlier hybrid configuration. GPU propagation
wall time is **31.223 ms** and GPU-renderer wall time **398.271 ms**. Every
instrumented target window records four OptiX-enabled events. This remains
about 66 times slower than the 120 Hz fleet deadline on one P100.

The implementation retains every physical path, 1,028 diffuse attempts per
link, independent source allocations/FFTs, FP64/complex128 rendering, declared
100 us delay / 2,500 Hz Doppler ranges, 1e-10 temporal tolerance, and continuous
receiver filtering/noise/ADC and actual consumer delivery. No path pruning or
sample-budget reduction is used. The compatibility counter uses GPU uint32
atomics instead of an unsupported Volta warp-match instruction. Optional Metal
backend checks are handled for the older API, and evaluated loops keep native
reference traversal/arithmetic on the GPU. Path storage capacity is padded,
not the physical path set.

Repeated local-direction draws are reused only when antenna probabilities,
seed and dimensions match exactly. Antenna tables and all geometry/visibility/
fields are recomputed. Moving GPU poses are made opaque so new values do not
trigger fresh compiler specialization; they are never cached or frozen.
Per-receiver pinned/device workspaces reuse storage. Fused coefficient
projection remains optional because its short-run improvement was marginal.
See [all experiments and qualifications](results/profiling/p100-gpu-system-20261007/README.md).

Source generation/preparation, receiver filtering/noise/ADC, bridge/control and
HTTP/file I/O remain host stages. GPU propagation/rendering is not a claim that
every operation is device-resident. Live AirSim physics/RPC, WAN/AMS-GRA workers
and unequal-clock resampling remain outside this qualification. Raw SC16 files
stay local; reports, JSON, logs and checksums are published.
