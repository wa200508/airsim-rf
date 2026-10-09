# P100 GPU fleet-update FFT block sweep — 2026-10-08

**Timing scope:** 100 TX × 10 RX, CUDA/OptiX propagation and CUDA rendering, sequential receivers on one P100. Wall seconds per simulated signal second is the primary cost unit. Each case generates **0.250 simulated seconds per receiver** across 30 timed fleet updates after a separate first capture and three warmups. Every update emits 16,666 or 16,667 samples/RX at 2 MS/s (~8.333 ms). Initialization and live AirSim physics/RPC are excluded; source preparation, propagation, rendering, continuous receiver processing and loopback HTTP/SC16 readback are included.

| Block samples | Trial | Measured signal s | Measured wall s | Wall s / simulated signal s | Wall median ms/update | Renderer wall median ms/update |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 2048 | [control_before](control_before/measurements.json) | 0.250000 | 16.574220 | 66.297 | 552.036 | 397.124 |
| 512 | [block512](block512/measurements.json) | 0.250000 | 21.850550 | 87.402 | 727.016 | 573.492 |
| 1024 | [block1024](block1024/measurements.json) | 0.250000 | 17.800179 | 71.201 | 592.578 | 438.684 |
| 4096 | [block4096](block4096/measurements.json) | 0.250000 | 25.544428 | 102.178 | 850.875 | 696.437 |
| 8192 | [block8192](block8192/measurements.json) | 0.250000 | 29.534887 | 118.140 | 982.058 | 828.174 |
| 2048 | [control_after](control_after/measurements.json) | 0.250000 | 16.645006 | 66.580 | 554.862 | 399.682 |

**Outcome:** retain the existing 2,048-sample default. The bracketing controls measure 66.297 and 66.580 wall seconds per simulated signal second. Alternative blocks are slower. Smaller blocks increase repeated setup/dispatch; larger blocks require higher temporal rank and more FFT/filter work at the unchanged Doppler/tolerance limits. This is a measured configuration sweep, not a kernel-level attribution. Every case misses all 30 update deadlines.

All trials use source revision `92fc595` with Sionna RT 2.2.0, Mitsuba 3.8.0, Dr.Jit 1.3.1 and CuPy on P100. Precision, antenna/material model, all physical paths, 1,028 diffuse attempts/link, 100 µs declared delay support, ±2,500 Hz Doppler and 1e-10 temporal tolerance remain fixed. Each trial is a separate process, run sequentially in one container with a shared Dr.Jit disk cache. First-use/warmup exclude startup; recurring work in timed updates remains included. Exact commands are in [manifest.json](manifest.json).

Qualification: five CUDA block-size tests passed full 16,667-sample comparisons against a fixed 2,048-block CPU basis reference, including changed coefficients and Unix-epoch phase. This is a correctness oracle, not a CPU-only performance series. Per-update integration checks validate continuity, shapes, finiteness, ADC bounds, payload hashes and readback; they are not a full-fleet numerical oracle. All trial epochs, sample counts and physical path-count maps match the bracketing control. Reporting qualification passed 13 tests, including exact sample-duration normalization without multiplying by RX count.

Ollama was paused during timing and restored afterward; other GPU-resident services were idle. A preliminary run inherited stale image revision metadata and was excluded; its diagnostic artifacts remain in `/tmp/p100-gpu-block-sweep-metadata-diagnostic-20261008`. The published repeat explicitly sets revision/dirty metadata. SC16 captures stay local and ignored.

```bash
docker run --rm --gpus all --user 1000:1000 --tmpfs /.drjit:rw,mode=1777 \
  -v "$PWD":/work/repo:ro -v "$PWD/results/profiling":/work/results \
  -w /work/repo -e PYTHONPATH=/work/repo/src \
  -e RF_PROFILE_SOURCE_REV=92fc595 -e RF_PROFILE_SOURCE_DIRTY=false \
  --entrypoint /opt/airsim-rf/.venv/bin/python airsim-rf:p100-modern-gpu \
  scripts/run_p100_block_sweep.py --iterations 30 \
  --output /work/results/p100-gpu-block-sweep-repeat
```

[Timing definitions](../../../TIMING_CONVENTIONS.md).

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** wall seconds per simulated signal second = total measured wall service / total output signal duration per receiver. Receiver durations are concurrent, not added across receivers. This is a processing-cost ratio for the named scope; it is not a whole-flight measurement. Instrumented costs are diagnostic.

| Raw case / timed scope | Mode | Calls | Signal ms/call (mean) | Measured signal seconds | Measured wall seconds | Wall seconds / signal second |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [results/profiling/p100-gpu-block-sweep-20261008/block1024/measurements.json](block1024/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 17.800179 | 71.201 |
| [results/profiling/p100-gpu-block-sweep-20261008/block4096/measurements.json](block4096/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 25.544428 | 102.178 |
| [results/profiling/p100-gpu-block-sweep-20261008/block512/measurements.json](block512/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 21.850550 | 87.402 |
| [results/profiling/p100-gpu-block-sweep-20261008/block8192/measurements.json](block8192/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 29.534887 | 118.140 |
| [results/profiling/p100-gpu-block-sweep-20261008/control_after/measurements.json](control_after/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 16.645006 | 66.580 |
| [results/profiling/p100-gpu-block-sweep-20261008/control_before/measurements.json](control_before/measurements.json) — RF fleet update | unprofiled_end_to_end_benchmark | 30 | 8.333333 | 0.250000 | 16.574220 | 66.297 |

The measured signal seconds column totals processed windows. Synthetic and historical short-capture jobs may reuse epochs or leave gaps; this total does not assert a continuous simulation timeline. First-use/warmup are excluded where the recorded harness excludes them. Stage milliseconds elsewhere use the same signal duration as their parent call; stage median / signal-ms is a median cost ratio, while the final column above uses sums (equivalently mean costs for fixed-duration calls).

<!-- END SIGNAL TIME CONTEXT -->
