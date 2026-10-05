# Batched private-transmitter rendering

**Runtime context (2026-10-05):** Historical CPU optimization. The 243 ms service case uses tones, about 42,500 surviving paths and 2.048 ms of output; it is not the newer all-valid-path continuous-window GPU case. See [current runtime and wall-clock costs](RUNTIME_STATUS.md) for comparable measurements, hardware, exclusions and ten-minute estimates.

Branch: `optimization/direct-path-renderer`. The new `batched-llvm` and
`batched-cuda` SDR backends batch independent link jobs and replay compiled
execution. They also accept arbitrary sampled I/Q. Existing renderer defaults
are unchanged. This is an implementation and CPU measurement, not a claim of
120 Hz operation or measured GPU performance.

## What changed and why

The [independent-transmitter profiling study](INDEPENDENT_TX_OPTIMIZATION.md)
identified repeated kernel launches, phase setup, temporary contribution arrays
and per-link transfers. This implementation addresses those costs:

- Each job has disjoint path data, private sampled input and private output.
  Packing jobs never aliases transmitter samples or shares their transforms.
- Jobs are grouped under `max_render_lanes`, with configurable path and sample
  tiles. Paths are padded and masked; all valid paths remain. A larger path
  count creates a larger capacity configuration instead of truncating paths.
- Persistent `dr.freeze` callables replay execution for compatible shapes.
  Gains, delays, Dopplers, clocks, input samples and timestamps remain runtime
  inputs. Cache capacity is bounded to 16 configurations. Aligned private input
  allocations avoid retracing caused by inconsistent NumPy buffer alignment.
- Weighted initial phasors and increments are prepared once per path. Within
  a tile, recurrence preserves phase evolution at every sample. LFM retains
  its changing instantaneous frequency and quadratic phase. No low-Doppler,
  common-waveform or short-delay assumption is used to remove work.
- Contributions reduce directly into contiguous job outputs without storing
  a complete path-by-sample array. CPU `auto` uses Dr.Jit's thread-private
  expanded reduction when the output fits its threshold, otherwise local
  reduction. CUDA uses local reduction. CPU thread replicas still consume
  memory: the lane limit is not a total-memory limit.
- Per-link diagnostics remain enabled by default. Explicitly disabling them
  permits coherent device summation and one receiver output export, and omits
  the per-link power report. Noise, receiver filtering and ADC remain enabled.

The receiver retains a `BatchedPathRenderer` between captures. Recreating it
per capture discards the replay cache. Replay does not freeze scene physics:
channel visibility and coefficients still update at each channel epoch.

Sionna channel data still pass through NumPy, preparation is still on the host,
and final receiver filtering/noise/ADC remain CPU work. Captures still use the
existing 256-sample filter warmup and fresh filter state; this change does not
provide a stateful continuous streaming receiver or eliminate distributed
transport latency.

## Arbitrary sampled I/Q

`SampledWaveform` owns a copied, read-only complex128 source buffer. The batched
backend supports different input/output rates, independent transmitter clocks
and carrier offsets. Even jobs given the same descriptor receive disjoint
source allocations; no transmitter sharing savings are assumed.

```python
from airsim_rf.batched_rendering import BatchedPathRenderer, PathRenderJob
from airsim_rf.sampled_waveform import SampledWaveform

wave = SampledWaveform(
    input_iq_with_history_and_lookahead,
    sample_rate_hz=2e6,
    reference_time_ns=first_input_sample_ns,
    interpolation_taps=32,
)
engine = BatchedPathRenderer(backend="cuda")  # Keep this instance alive.
job = PathRenderJob(gains, delays_s, dopplers_hz, wave)
iq = engine.render(
    [job], sample_rate_hz=2e6, num_samples=16667,
    sim_time_ns=output_start_ns, channel_epoch_ns=channel_epoch_ns,
)
```

Fractional delays use normalized Lanczos-windowed sinc interpolation. Every
physical path retains its gain, delay and Doppler; interpolation taps describe
the sampled-waveform reconstruction kernel, not a merged physical channel.
The implementation factors out common sinc terms and advances the remaining
interpolation sine through recurrence, including sample-coordinate wraps.
It avoids trigonometry per interpolation tap and handles nonunit rate ratios.

The finite kernel approximates ideal bandlimited reconstruction. Support is
selectable from 4 to 128 even taps. Agreement with the NumPy reference verifies
the same finite operator, not an ideal-reconstruction error or receiver noise
floor guarantee. A separate 64-tap Fourier test checks normalized RMS error
below 1e-4 for its specific frequencies up to 0.23 times the input sample rate;
that is not a full-band qualification.

The default `boundary="error"` requires valid history and lookahead for every
path and output sample. `boundary="zero"` explicitly represents a finite
transmission surrounded by zero. At 2 MS/s, 32 taps require up to 8 microseconds
of future input support, adding delivery latency for a live input source.
Input amplitude is preserved, not normalized. Use unit mean-square input when
interpreting the SDR emitter's nominal power that way, and declare occupied
frequency bounds correctly for receiver Nyquist checks.

## Matched CPU measurements

Data: [environment](research_results/batched_renderer_cpu/environment.json),
[per-link local](research_results/batched_renderer_cpu/per_link_local.json),
[batched, tile 32](research_results/batched_renderer_cpu/batched_32.json),
[batched, tile 128](research_results/batched_renderer_cpu/batched_128.json).

All three use the same ten scene epochs and identical per-epoch retained path
counts (42,513–42,526). Configuration: 100 independent tone transmitters,
one receiver, 4,096 output samples plus 256 filter-warmup samples, 1,028 diffuse
attempts per link, two Dr.Jit threads and a two-core CPU quota. Per-link
diagnostics, clocks, noise, filtering and ADC are enabled. Two warmups precede
ten unprofiled captures. Complete service includes channel calculation and
channel export, but excludes AirSim physics/RPC, network queues and RF skills.

| Renderer | Median rendering | Median complete service | Serial capture rate |
| --- | ---: | ---: | ---: |
| Per-link recurrence, local reduction | 189.40 ms | 274.03 ms | 3.60 Hz |
| Batched replay, sample tile 32 | 170.32 ms | 247.32 ms | 4.04 Hz |
| Batched replay, sample tile 128 | 169.87 ms | 243.25 ms | 4.03 Hz |

The tile-128 comparison is 1.115 times faster in rendering and 1.127 times
faster in complete service. Earlier 331 ms captures are not a matched baseline
for this run. Tile 128 did not demonstrate a clear CPU throughput advantage
over 32, so the API default stays 32. Neither configuration meets 120 Hz.

The [separate instrumented run](research_results/batched_renderer_cpu/batched_events.json)
uses four replayed rendering kernels per capture, compared with approximately
400 in the earlier per-link profile. Warm captures report no new recordings
and zero replayed code-generation time. Tile 128 fits the hundred jobs in one
435,200-lane group with 512 padded path slots per job. This is a launch-count
improvement to test on a GPU, not a prediction of a hundredfold speedup.
Host preparation alone takes roughly 7–8 ms in that profile. Export/wait time
includes asynchronous device execution and is not a measurement of pure copy
cost. These stages can overlap; do not add them as independent costs.

### Separate sampled-input stress measurement

[Sampled-input data](research_results/batched_renderer_cpu/sampled_input.json)
exercise one private source, **1,028 valid paths**, 4,096 outputs, 32 taps,
delays up to 100 microseconds and Dopplers up to 2,500 Hz, with source clock
offset and random complex input occupying 90% of the sample-rate bandwidth.
Median renderer latency is **166.34 ms**, p95 **171.29 ms**, over ten unprofiled
captures. This is 4,210,688 path/sample contributions with interpolation.
It excludes ray tracing, AirSim, receiver DSP and private source generation.

The finite-operator reference includes all paths of the first link and a
128-sample prefix: normalized RMS disagreement is 6.9e-14. It is not a
100-transmitter/10-receiver continuous-stream benchmark. Arbitrary sampled
rendering remains much more expensive per contribution than analytic tones;
the new engine does not establish feasibility for the target workload.

## Run the GPU comparisons

The [P100 kit](P100_PROFILING.md) now compares NumPy, per-link and batched
rendering by default. Per-link collection defaults to local accumulation;
`--direct-accumulation partial` selects the old buffered implementation.
It separately collects sampled-input stress measurements and includes them
in the report without treating them as complete scene service measurements.
CUDA correctness checks cover both renderer implementations when preflight
successfully exercises a real CUDA/OptiX scene.

```bash
bash scripts/run_p100_docker.sh --quick --renderers direct batched \
  --run-id p100-batched-quick
bash scripts/run_p100_docker.sh --renderers direct batched \
  --run-id p100-batched-full
bash scripts/run_p100_docker.sh --quick --renderers batched \
  --sample-tile 128 --run-id p100-batched-128
python3 scripts/publish_gpu_results.py results/profiling/p100-batched-full --push
```

The collector's full sampled case defaults to 100 independent links, 1,028
valid paths per link, 4,096 outputs and 32 interpolation taps. Pass
`--samples 16667` to the collector to measure approximately one 120 Hz interval
at 2 MS/s in both its scene and sampled cases. The sampled case remains a
renderer-only test. For a separately measured all-1,000-link stress run:

```bash
.venv/bin/python benchmarks/benchmark_batched_rendering.py \
  --backend cuda --links 1000 --paths 1028 --samples 16667 \
  --taps 32 --max-delay-us 100 --max-doppler-hz 2500 \
  --iterations 10 --output results/sampled-gpu-1000links.json
```

That run can be expensive and needs a separate delay/Doppler/bandwidth/support
sweep for qualification. Neither terrain path attrition nor transmitter sharing
is used to reduce its path count. The collector reports unavailable CUDA
explicitly; it does not silently substitute CPU measurements.

## Validation and next priorities

Tests cover changing runtime data under replay, capacity growth, private inputs,
different interpolation supports, arbitrary rate ratios, clock offsets, split
capture continuity, finite-buffer boundaries, coherent summation and complete
SDR receiver outputs against the existing implementation. CUDA cases remain
untested in this CPU workspace.

Before further backend changes, collect real GPU execution, bandwidth and
reduction contention measurements. Next architectural candidates are keeping
channel inputs/preparation and receiver DSP resident on the device, a persistent
streaming receiver with history/lookahead and backpressure, and an optimized
native interpolation kernel if GPU profiling identifies interpolation as the
dominant cost. These require measurements and accuracy qualification; none is
included in the performance claim above.
