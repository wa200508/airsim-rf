[Documentation](../README.md) · [Scenarios](../../scenarios/README.md) · [Run dashboard](../dashboard.md)

# MUSIC angle of arrival and emitter tracking

> **Advanced / offline reference.** The two maintained dashboard demos start at the [scenario catalog](../../scenarios/README.md) and [dashboard guide](../dashboard.md). The examples on this page have their own inputs and qualification scope.

This page describes the offline tracking example. For the live drone-orbit
dashboard's different layout and its MUSIC call chain, see the
[code map](../code-map.md#find-the-actual-music-algorithm).

Receiver-only MUSIC and tracking live in `processing/music.py` and
`processing/tracking.py`; `track_windows()` accepts neutral acquisition blocks.
The old `aoa_tracking.consume()` translates completed recordings only; held-out
truth scoring lives separately in `evaluation/tracking.py`. See the
[simulation/skill boundary](../skill-boundary.md).

This ready-made Python example follows the direction-finding theme of the
[SDR University Challenge resource list](https://www.mathworks.com/academia/student-competitions/sdr-university-challenge.html).
Its official reference is MathWorks'
[MUSIC with TwinRX example](https://www.mathworks.com/help/wireless-testbench/ug/estimate-direction-of-arrival-using-music-algorithm-and-twinrx-daughterboards.html),
which uses four phase-synchronized receive channels. Here, independently
propagated simulated array-element I/Q feeds the external Python
[doa_py MUSIC implementation](https://github.com/zhiim/doa_py). Two measured
bearings produce a position measurement; a
[FilterPy](https://github.com/rlabbe/filterpy) constant-velocity Kalman filter
tracks the emitter. No MATLAB or transmitted symbols are needed by the consumer.
This is an independent implementation, without MathWorks code or affiliation.

For related official tracking examples, see
[monopulse tracking of a 500 MHz emitter](https://www.mathworks.com/help/phased/ug/monopulse-tracking-of-500-mhz-emitter.html)
and [passive RF source localization and tracking](https://www.mathworks.com/help/fusion/ug/source-localization-and-tracking-with-passive-receivers.html).
Those use monopulse and TDOA respectively; they illustrate related workflows,
and are not the algorithm implemented here.

## Run the complete example

Use the qualified Python 3.12/Linux environment and system prerequisites in
[setup](../setup.md). From the checkout:

```bash
python3.12 scripts/bootstrap.py --geometry
source .venv/bin/activate
python -m pip install -r requirements-tracking-lock.txt -e '.[tracking]'
airsim-rf track-demo --output recordings/aoa-demo
```

The output directory must be new. The default runs entirely on CPU, including
propagation, receiver DSP and tracking; no simulator server is required. The
tracking lock records the tested optional dependency set. The smaller
`requirements-tracking.txt` pins the two algorithms only, allowing their
transitive dependencies to resolve. This dependency set includes optimization
and imaging libraries imported by doa_py, even though this example uses MUSIC.

In a configured CUDA environment, use:

```bash
airsim-rf-cuda -m airsim_rf.cli track-demo --backend cuda \
  --output recordings/aoa-demo-cuda
```

Add `--pascal-compat` only for the qualified pinned P100 stack described in
[setup](../setup.md#p100-profiling). Install the optional tracking dependencies in
that environment too. `--windows 32` gives a shorter smoke run. The checkout
wrapper `python examples/aoa_emitter_tracking.py --output ...` is equivalent to
`track-demo`. The installed command and bundled geometry also work outside the
checkout.

This moving-emitter example uses a **supplied kinematic RF trajectory**.
It does not run live simulator physics. The generated `inputs/radios.json`
and simulator configurations are complete for a stationary live run at the
initial pose; the live recorder does not automatically execute `scenario.json`.
See the [shared-scene quickstart](../quickstart.md) for actual simulator recording.

## What runs

| Item | Default |
| --- | --- |
| Emitter | Independent random QPSK, 25 ksymbols/s, pulse-shaped and normalized to unit mean sample power; 1 mW configured TX power |
| RF / sampling | 915 MHz carrier, 2 MS/s complex, declared occupied bounds ±100 kHz |
| Arrays | Two stationary four-element ULAs; half-wavelength spacing, about 0.164 m |
| Sites in RF metres | `(0, -10, 120)` and `(0, 10, 120)` |
| Emitter motion | Starts at `(20, -7.2, 120)`, velocity `(0, 12, 0)` m/s |
| Duration | 100 × 12 ms windows = 1.2 s; 14.4 m displacement |
| Capture | Eight individually traced, rendered, filtered, independently noise-added and ADC-quantized element channels |
| Storage | 2,400,000 complex samples per element; 76,800,000 raw I/Q bytes total |
| Consumer | doa_py 0.5.0 MUSIC, two-bearing intersection, FilterPy 1.4.5 Kalman filter |

The complete shared mesh is loaded. Baseline propagation selects direct
visibility. `--reflection` also retains first-order specular paths as a stress
case; it does not promise a passing accuracy gate. Continuous waveform history,
receiver filter state and the production signed 12-bit ADC are used. There is
one emitter; its symbols never enter the estimator.

Coordinates are RF north/west/up in metres. Array elements lie along local +y;
local +x is broadside, with positive bearing towards +y. `yaw_rad` rotates that
frame about +z. MUSIC searches −70° through +70° in 0.05° steps. A front-side,
near-zero-elevation prior resolves the ULA ambiguity. The model assumes common
nominal clocks/LO phase within each array, calibrated channel response, known
receiver positions and synchronized timestamps across sites. Real receiver
calibration, oscillator errors and unknown elevation need additional work.

## See the RF processing

The primary figures are generated from the recorded complex ADC data and
receiver metadata, without emitter truth or transmitted samples:

- **`iq-frequency.png` / `.svg`:** the four site-0 channel PSDs and an element-0
  frequency waterfall over the continuous capture. The two-sided complex-I/Q
  PSD uses a 4096-sample Hann window, 2048-sample hop, no zero padding and
  488.28125 Hz bins at 2 MS/s. Axes show baseband offset from 915 MHz and
  dB relative to 1 V²/Hz, using reconstructed input-referred volts.
- **`music-processing.png` / `.svg`:** actual doa_py MUSIC pseudospectra at the
  beginning, middle and end of the capture for both sites; covariance
  eigenvalues showing the selected signal/noise subspaces; and measured
  inter-element cross-phase against the phase slope of the estimated angle.
  Each angular curve is normalized to its own maximum. Its level is neither
  RF power nor a probability. All displayed peaks are checked against the
  ordinary consumer.

Frequency spectra expose the received signal band. MUSIC uses the complex
phase relationship across elements to estimate direction, so its spatial
search is plotted against angle. The phase overlay is a fit to the same data,
not independent ground-truth validation. Tracking remains a downstream result.

Replot an existing capture on CPU, without rerunning propagation:

```bash
airsim-rf music-plots recordings/aoa-demo/capture \
  --arrays recordings/aoa-demo/arrays.json --output recordings/aoa-plots
```

`music-plot-values.npz` retains the numerical plot arrays; `music-plots.json`
records processing settings, units, input hashes and selected epochs. Plotting
loads one site’s short example capture into memory; it is not the sustained
streaming workflow.

## Outputs and independent replay

| Output | Purpose |
| --- | --- |
| `inputs/` | Generated QPSK, shared USD/bundle, stationary live radio and simulator configurations |
| `arrays.json` | Receiver-only site geometry, ordered channel IDs and complex calibration |
| `capture/` | Completed manifest plus eight SigMF metadata/data pairs; no emitter poses or velocities |
| `estimates.json` | Per-window measured bearings, fused positions, filtered positions/velocities, algorithm versions |
| `truth.json`, `scenario.json` | Held-out evaluator truth and supplied simulation trajectory |
| `channels.json` | Retained path counts for diagnostics; not a consumer input |
| `metrics.json` | Fixed accuracy/coverage gates and held-out errors |
| `reversed-array-control.json` | Wiring-order negative control, expected to reject the accuracy gates |
| `iq-frequency.png`, `.svg` | Received I/Q PSDs and frequency waterfall |
| `music-processing.png`, `.svg` | MUSIC angular peaks, covariance eigenvalues and spatial phase |
| `music-plot-values.npz`, `music-plots.json` | Numerical figure data, processing settings and source hashes |
| `tracking.png`, `tracking.svg` | Secondary track and bearing plots against held-out truth |

Replay on CPU with only the completed capture and array metadata:

```bash
airsim-rf track recordings/aoa-demo/capture \
  --arrays recordings/aoa-demo/arrays.json --output recordings/replayed-estimates.json
```

The output file must be new. This command reads ADC samples, receiver calibration
and timestamps. It does not open emitter truth, the source waveform, scene mesh
or path exports, and needs neither CUDA nor a simulator connection.

```python
from airsim_rf.aoa_tracking import consume, score

estimates = consume("recordings/aoa-demo/capture", "recordings/aoa-demo/arrays.json")
# Optional evaluator, separate from the algorithm:
metrics = score(estimates, "recordings/aoa-demo/truth.json")
```

Each site's calibration entry `[real, imag]` is the measured complex channel
gain: the consumer divides the corresponding voltage samples by that gain.
All channels must have equal epochs, sample offsets/counts, rates and carrier.
Recording corruption, incomplete captures and unsynchronized metadata reject
processing. Rank-one eigenvalue contrast below five rejects a bearing. Nearly
parallel or backward intersections do not produce position measurements.
The tracker starts from the first measured intersection with zero velocity;
subsequent windows can predict through missing measurements. Filter covariance
uses an assumed 0.5° bearing deviation, not a calibrated uncertainty guarantee.

## Acceptance and limits

The [priority 3 evidence](../../results/reviews/priority3-20261020/REPORT.md) records
these measured results on the qualified P100 pipeline, followed by an installed
wheel consumer replay on CPU with only capture and receiver metadata mounted:

| Metric | Direct baseline | First-order specular stress | Fixed gate |
| --- | ---: | ---: | ---: |
| Bearing RMSE | 0.0151° | 1.9448° | <1° |
| Track position RMSE | 0.00181 m | 0.27549 m | <0.5 m |
| Track velocity RMSE | 0.00776 m/s | 1.04398 m/s | <2 m/s |
| Bearing / fusion / track coverage | 100% each | 100% each | ≥95% each |
| Result | Pass | **Fail: bearing gate** | All gates required |

Track error metrics exclude the first 0.240 s for filter settling; bearings
are scored over all windows at window midpoints. Track position/velocity RMSE
use Euclidean errors, not per-axis averages. Coverage includes prediction when
a track exists; fusion coverage separately counts actual paired measurements.
Reversing the first array's channel order must fail the unchanged accuracy
gates. Tests also reject noise-only data, check calibration with independently
generated phase/amplitude offsets, and reject mismatched channel metadata.

The millimetre baseline is an ideal calibrated, single-emitter, line-of-sight
simulation result. It does not establish measured-radio accuracy. Plain MUSIC
has coherent multipath bias in the retained reflection case; no paths were
removed or thresholds loosened to make that case pass. Spatial smoothing,
multipath-aware estimation, arbitrary elevation, ambiguous hemispheres,
multiple emitters/data association, live moving-array pose updates and hardware
calibration are beyond this example. No BER/EVM or real-time capacity claim is
made. A failed accuracy gate returns exit code 1 while preserving the evidence;
setup/input errors return 2.

## Replace the waveform or algorithm

The waveform generation is isolated in `airsim_rf.aoa_example.prepare`.
Replace its QPSK construction with your own finite one-dimensional complex
samples, preserving the declared sample rate, source epoch/history and enough
duration for the requested capture. Update the occupied frequency bounds and
TX power explicitly. Keep the signal narrowband relative to the array's
aperture delay; wideband signals require an appropriate estimator. No symbol
reference is necessary for this noncooperative consumer. General waveform
conventions are documented in [interfaces](interfaces.md).

Replace `estimate_bearing` or the fusion/filter stage in
`airsim_rf.aoa_tracking.consume`, or use `iter_iq_blocks` to feed your own
algorithm. Keep the truth evaluator separate. For live stationary recording,
the supplied radio IDs and body mounts preserve the same channel ordering:
RF +y offsets map to body NED −y at zero yaw. For actual motion, configure a
physics/controller trajectory with one stepping owner, record real platform
epochs/poses, and supply time-varying receiver geometry if the arrays move.
The [live workflow](live-workflow.md) and [interfaces](interfaces.md) describe
those integration points; the supplied RF trajectory is not a flight command.
