# Direct path I/Q rendering

Branch: `optimization/direct-path-renderer`, based on `profiling/p100`.

The renderer retains every valid channel path separately. It does not convert
paths into a fixed tapped delay line, merge equal delays, select only the
strongest returns, or discard distinct Dopplers. Propagation remains one-way
for ESM/comms. The optional point-target radar model separately supplies its
round-trip coefficients, delays and Dopplers.

For each transmitter/receiver path, it evaluates:

```text
y_p[n] = sqrt(R * Ptx) * a_p * x(t_start + n/fs - delay_p)
         * exp(j * 2*pi * doppler_p * (t_start + n/fs - channel_epoch))
y_receiver[n] = sum_transmitters sum_paths y_p[n]
```

`a_p` includes carrier-delay phase at `channel_epoch`. No extra carrier phase
is added. Delay, amplitude and Doppler remain fixed within the capture, while
Doppler phase evolves at every sample. Geometry is solved once per capture;
the caller schedules captures once per pulse. This is the accepted narrowband
model, not wideband waveform stretching.

## Implementation and supported signals

`src/airsim_rf/rendering.py` provides `render_paths` and explicit
`ToneWaveform` / `LFMChirpWaveform` descriptions. `backend="numpy"` evaluates
an independent analytic reference. `backend="llvm"` or `"cuda"` runs a
Dr.Jit recurrence kernel using the already-pinned dependency stack. CUDA
requests fail when CUDA is unavailable; there is no implicit CPU fallback.

Default tiles contain 128 paths and 32 consecutive samples. Each path/sample
tile lane initializes the analytic waveform+Doppler phase and advances by
complex multiplication. For LFM, the phase increment itself advances by a
second recurrence. Fractional delays are evaluated analytically, including the
half-open pulse gate. Phase is reinitialized analytically every 32 samples to
bound accumulated error. Phase arithmetic, recurrence and reduction use FP64.

Each lane writes unique locations in two temporary real/imaginary buffers.
The buffers are reduced across paths and added to the receiver waveform.
This avoids a contested atomic addition for every path/sample. Buffers hold
one path tile times the receive-window size, rather than all scene paths
at all sample times. Contribution-buffer storage is approximately
`16 * path_tile * num_samples` bytes: 8.5 MiB for 128 paths and 4,352 samples,
plus recurrence state, reduction/output arrays and runtime allocations.
Work remains O(paths × samples). This implementation is a correctness-first
baseline; tile sizes and launch/reduction overhead require GPU profiling.

An experimental `render_paths(..., accumulation="local")` option replaces the
contribution buffers with SIMD-packet/CUDA-warp local pre-reduction followed by
atomic output addition. It preserves the same waveform, FP64 arithmetic, valid
paths and individual Dopplers. It can introduce atomic contention and small
nondeterministic summation-rounding differences; the default remains
`"partial"`. `SDRNetworkReceiver(..., accumulation="local")` exposes it for
comparison with the full receive chain. No transmitter buffers are shared.
See [the measurements and profiling commands](INDEPENDENT_TX_OPTIMIZATION.md).

Arbitrary Python waveform callbacks continue to work with the existing NumPy
renderer. They are rejected explicitly by the direct backend. Sampled comms
waveforms with fractional-delay interpolation are a subsequent extension;
the current direct GPU implementation is not yet an arbitrary SDR waveform
renderer. One `LFMChirpWaveform` describes one pulse, with an explicit pulse
start epoch; a pulse train needs appropriately scheduled pulses or a future
train descriptor. The caller must select adequate sample rate/bandwidth.

## Coherence between captures

When splitting one channel realization into blocks, supply the same
`channel_epoch_ns` and waveform reference epoch for every block. Doppler phase
then continues across block boundaries. Integer nanosecond epochs are
subtracted before conversion to seconds, preserving LFM timing precision even
at Unix-scale epochs. TX clock error and pre-propagation LO phase are supported.
Very large absolute epochs with nonzero oscillator offsets still have finite
FP64 phase precision; this is not an arbitrary-precision clock model.

When Sionna retraces moving geometry, its new complex coefficient already
includes phase at the new capture epoch. Use that new epoch with the new
coefficient; carrying the old Doppler phase into it again would double count
motion. Newly appearing/disappearing paths and changing diffuse sample
identities still need physical temporal-correlation validation. This kernel
does not establish persistent terrain scatterers across retraces.

## APIs and receiver integration

```python
from airsim_rf.rendering import LFMChirpWaveform, render_paths

iq = render_paths(
    coefficients, delays_s, doppler_hz,
    LFMChirpWaveform(bandwidth_hz=20e6, pulse_width_s=1e-6,
                    reference_time_ns=pulse_start_ns),
    sample_rate_hz=50e6, num_samples=5000,
    sim_time_ns=pulse_start_ns, channel_epoch_ns=channel_epoch_ns,
    amplitude_scale=(50 * transmit_power_w)**0.5,
    backend="cuda",
)
```

`render_paths` returns complex128 values; it does not add noise or normalize
power. `synthesize_voltage(..., renderer="direct-cuda")` applies the usual
RMS voltage scaling/noise and returns the established complex64 `IQBlock`.
`RFReceiver(..., renderer="direct-cuda")` accepts waveform descriptors.
`PointTargetRadar(..., renderer="direct-cuda")` uses compact one-way Sionna
coefficients to form its existing reciprocal point-target radar model, then
renders LFM echoes through this backend.

`SDRNetworkReceiver(..., renderer="direct-cuda")` traces all links once,
renders each transmitter's contribution and sums before receiver noise/filter
and ADC. Emitters must use the explicit waveform descriptions. TX clock/LO
error and the receiver LO are preserved. Its current implementation exports
channels through NumPy, transfers each link to the device, and downloads the
rendered link before CPU diagnostics, filtering and ADC. It is not a fully
GPU-resident, fused 100-transmitter receive chain. Per-link transfers and all
front-end work are included in the service timing.

## Run and profile

```bash
git clone --branch optimization/direct-path-renderer --single-branch \
  https://github.com/wa200508/airsim-rf.git
cd airsim-rf
bash scripts/run_p100_docker.sh --quick --run-id p100-direct-quick
bash scripts/run_p100_docker.sh --run-id p100-direct-full
python3 scripts/publish_gpu_results.py results/profiling/p100-direct-full --push
```

The collector now compares NumPy and direct recurrence for both CPU and CUDA
propagation, at 2 and 100 transmitters per receiver. Direct CPU uses LLVM;
direct GPU uses CUDA. It runs renderer correctness tests after successful GPU
preflight, records synchronized rendering latency separately, and collects
separate instrumented profiles. The report groups CPU/CUDA pairs by renderer
and includes a renderer comparison table. Use `--renderers numpy` to reproduce
the previous implementation alone, or `--renderers direct` for recurrence only.

The pulsed radar example also accepts the renderer:

```bash
.venv/bin/python examples/lfm_radar.py --backend cuda --renderer direct-cuda \
  --output lfm-direct.npz
```

A single case can be measured with:

```bash
.venv/bin/python benchmarks/benchmark_sdr_runtime.py \
  --backend cuda --renderer direct-cuda --tx 100 --rx 1 \
  --samples 4096 --samples-per-link 1028 --warmup 5 --iterations 30 \
  --output results/direct-cuda.json
```

`--path-tile` and `--sample-tile` tune standalone benchmark tiles. The collector
uses the documented defaults. See [the P100 guide](P100_PROFILING.md) for device
passthrough, compatibility checks, telemetry, Nsight and publication details.
No P100 or other CUDA execution has been verified in this CPU-only workspace.

## Validation

Tests compare both implementations with independent waveform equations,
including fractional delays, LFM pulse gates, positive/negative Doppler,
same-delay paths with different Dopplers, coherent cancellation, independent
TX clocks/LOs, phase continuity across blocks and Unix-scale LFM epochs.
The LLVM renderer is compared with the existing Sionna/SDR voltage, link-power
and ADC pipeline. CUDA equation/continuity checks run on a GPU host; local
CUDA cases are explicitly skipped when no device is available.

Useful public implementation precedents include NVIDIA's
[Sionna Research Kit CUDA renderer](https://github.com/NVlabs/sionna-rk/blob/main/plugins/channel_emulation/cuda_emulator/src/chn_emu_cuda.cu),
[Sionna PHY time-channel renderer](https://github.com/NVlabs/sionna/blob/main/src/sionna/phy/channel/apply_time_channel.py)
and [OCUDU GPU Channel](https://github.com/zhouyou-gu/ocudu-gpu-channel).
This implementation uses our own direct-path equations and the existing
Dr.Jit runtime; no source from those renderers was copied.

## Preliminary CPU measurements

The [CPU-only profiling bundle](results/profiling/direct-renderer-cpu-validation/REPORT.md)
compares the original renderer with LLVM recurrence on this workspace's two-core
CPU quota. Both use the same 800-triangle terrain, 1,028 attempts/link,
4,096 output samples plus 256 filter warmup samples, and independent radio clocks.

| 100 TX / 1 RX | Original NumPy | Direct LLVM |
|---|---:|---:|
| Median rendering | 11,069 ms | 310 ms |
| Median complete service | 11,195 ms | 394 ms |
| Sustained serial updates | 0.089 Hz | 2.537 Hz |
| Retained paths | 42,509–42,513 | 42,509–42,513 |

That is approximately 35.7× faster rendering and 28.4× lower median complete
service latency. Only two timed captures were collected in this quick large
case; this is not a reliable p95/tail estimate or a 120 Hz claim. The small
2-TX case also improved, but its three timed captures include a latency spike
and do not establish stable warmed performance. The source was a dirty working
copy based on `720c401`; the bundle records file hashes and exact commands.
These are measured CPU results, not GPU projections or measured P100 behavior.

The completed local suite and offline non-root profiling container each passed
88 tests, with five CUDA cases skipped. The direct LLVM pulsed-radar example
recovered range peaks at 299.79 m and 599.58 m for targets at 300 m and 600 m.
