# Priority 3 acceptance — 20 October 2026

Priority 3 is complete for the user's chosen **Python MUSIC angle-of-arrival and
emitter-tracking example**, with links to official SDR University Challenge
resources. This replaces the proposed generic comms-demodulation example with a
noncooperative ESM consumer. No BER/EVM result, MathWorks implementation or
challenge-entry affiliation is claimed. Everything remains local; nothing was
published or delivered. Priorities 4–6 remain open.

## Concrete result

Independent pulse-shaped QPSK passes through the production propagation,
continuous sampled-waveform renderer, receiver filter/noise and 12-bit ADC,
separately for eight receive elements. The completed ADC recording feeds
external **doa_py 0.5.0 MUSIC**, two-bearing geometric fusion and an external
**FilterPy 1.4.5** constant-velocity Kalman filter. The estimator receives no
emitter positions, velocities, symbols, source samples, traced gains or delays.
The waveform is generated independently; truth scoring is a separate function.

The ready-made [guide](../../../docs/aoa-emitter-tracking.md) includes installation,
CPU/CUDA commands, outputs, calibration/coordinate conventions, algorithm and
waveform replacement guidance, and official links:

- [SDR University Challenge resources](https://www.mathworks.com/academia/student-competitions/sdr-university-challenge.html)
- [Official MUSIC/TwinRX example](https://www.mathworks.com/help/wireless-testbench/ug/estimate-direction-of-arrival-using-music-algorithm-and-twinrx-daughterboards.html)
- [Official monopulse emitter tracking](https://www.mathworks.com/help/phased/ug/monopulse-tracking-of-500-mhz-emitter.html)
- [Official passive RF tracking using TDOA](https://www.mathworks.com/help/fusion/ug/source-localization-and-tracking-with-passive-receivers.html)

The last two are related examples using different algorithms; no source was
copied from them. External Python libraries remain dependencies, not vendored code.

## Scope and measured results

This uses a **supplied kinematic RF trajectory, not live simulator physics**.
Two stationary four-element half-wavelength ULAs observe a single 915 MHz emitter
at 2 MS/s. The emitter moves 14.4 m in 1.2 seconds at 12 m/s. One hundred 12 ms
windows produce 2.4 million complex samples per element, 76.8 MB raw I/Q total.
All eight streams have independent receiver noise. The arrays have ideal common
clocks/LOs and calibrated response, known positions and near-zero source elevation.
The complete shared mesh is loaded; the positive baseline uses direct visibility.

| Held-out metric | Qualified direct baseline | Retained first-order specular stress | Fixed gate |
| --- | ---: | ---: | ---: |
| Bearing RMSE | 0.0150864° | 1.9448243° | <1° |
| Track position RMSE | 0.0018141 m | 0.2754854 m | <0.5 m |
| Track velocity RMSE | 0.0077577 m/s | 1.0439797 m/s | <2 m/s |
| Bearing detection | 100% | 100% | ≥95% |
| Paired-bearing position measurements | 100% | 100% | ≥95% |
| Post-settling track coverage | 100% | 100% | ≥95% |
| Result | **Pass** | **Fail: bearing gate** | All gates required |

Track error excludes the first 0.240 seconds; bearing scoring includes every
window at its midpoint. Track RMSE is the RMS Euclidean error. Fixed gates were
not relaxed after the stress result. Retained path counts verify that the
specular case actually includes multiple paths. Plain MUSIC is biased by
coherent multipath here; this is an exposed limit, not qualified general
multipath performance. Millimetre ideal-baseline errors do not establish
hardware accuracy. Multiple emitters, unknown elevation/hemisphere, moving-array
geometry, hardware calibration and real-time capacity remain outside this example.

The qualified GPU recording uses the pinned P100 stack (Sionna RT 2.2.0,
Mitsuba 3.8.0, Dr.Jit 1.3.1, explicit Pascal compatibility). It took about
16.80 wall seconds per signal second excluding preparation and consumer/plot
work. This is an example timing, not fleet throughput or a capacity result.
The CPU installed example uses the ordinary pinned stack (Mitsuba 3.9.1,
Dr.Jit 1.5.0, NumPy 2.5.3, SciPy 1.18.1, OpenUSD 26.8), Python 3.12.14.

## Independent consumption and controls

`qualified/` is authoritative: its capture manifest excludes emitter positions
and velocities. `isolated-consumer/estimates.json` was produced by a fresh venv
installing the local wheel, with **only** the capture, receiver array metadata,
optional dependencies, wheel, check script and output directory mounted.
The container had no GPU/network access, no checkout, no source waveform and no
original truth/scenario files. Its package imported from site-packages, outside
the checkout. Its CPU replay matches the complete GPU-recording estimates exactly.
After that replay, the same installed package generated and processed its own
32-window CPU example, passing every gate (0.0157501° bearing, 0.0040551 m position,
0.0365350 m/s velocity). This separate demo necessarily generates its own
held-out truth; it cannot access the original GPU run's truth.

Reversing the first array's actual sample-channel order fails the same gates:
38.8853° bearing RMSE, 89.5123 m position RMSE, only 42% fused measurements.
The negative control passes by rejecting that result. Independent geometric
phase-source tests check MUSIC angles and reversed signs, noise-only rejection,
ambiguous spacing, forward/parallel/backward intersections, nontrivial complex
channel calibration and cross-channel metadata synchronization.

The [machine audit](closure.json) passes all checks. Official SigMF 1.13.0
validates all eight files and reads every actual ADC sample, agreeing with the
project voltage reader. All channels have expected counts/bytes and zero
reported clipping. Geometry identity matches every window; waveform and wheel
hashes, raw-I/Q hashes and algorithm versions are retained. The wheel's consumer,
demo and CLI byte contents matched the production modules at acceptance,
before the visualization follow-up described below.

## Tests and native runtime limitation

- Focused final AoA tests: **9 passed** (`aoa-tests-final.log`).
- Earlier combined consumer/package/live selection: 39 passed (`consumer-tests.log`).
- Initial complete CPU suite before the final calibration test: 261 passed,
  158 CUDA/hardware skips (`full-cpu-tests.log`).
- After adding calibration coverage, two combined-suite runs aborted natively
  during cyclic garbage collection inside Dr.Jit frozen-kernel capture
  (`full-cpu-tests-final.log`, `full-cpu-tests-retry.log`). Thread limits did not
  resolve it. These are failures, not passes or ordinary pytest skips.
- A test-only cyclic-GC boundary fixture resolved the observed interaction:
  the complete suite with the probe passed **262 tests, 158 hardware skips**
  (`full-cpu-tests-gc-boundaries.log`). The upstream root cause is not established.
  Automatic GC remains enabled during every test; no assertions or tests were
  removed. The retained repository fixture is `tests/conftest.py`.
- The final ordinary suite with that repository fixture passed **262 tests,
  158 hardware skips** in 48.58 seconds (`full-cpu-tests-qualified.log`).

This fixture does not modify the RF renderer or production process. No claim
of a new full GPU suite, native upstream fix, calibrated hardware equivalence or
sustained-operation qualification is made.

## Reproduction and artifact map

The guide gives the end-user workflow:

```bash
python3.12 scripts/bootstrap.py --geometry
source .venv/bin/activate
python -m pip install -r requirements-tracking-lock.txt -e '.[tracking]'
airsim-rf track-demo --output recordings/aoa-demo
airsim-rf track recordings/aoa-demo/capture --arrays recordings/aoa-demo/arrays.json \
  --output recordings/replayed-estimates.json
```

For the local qualification, dependency installation was isolated in
`.deps/aoa-consumer`; `dependency-install.log` preserves the operation.
`requirements-tracking-lock.txt` records all resolved optional packages. The
local wheel is in `local-build/`, with `wheel-build.log`. The narrow-mount check
is `scripts/qualify_tracking_consumer.sh`; set `RF_RUN_TRACK_DEMO=1` to also run
the installed CPU demo after replay. `isolated-consumer.log` retains both runs.
No registry pull, source checkout or online install occurred inside that check.

Audit the artifacts using the qualified CPU environment with optional tracking
and SigMF installed:

```bash
python scripts/qualify_tracking_example.py results/reviews/priority3-20261020 \
  --output results/reviews/priority3-20261020/closure.json
python scripts/check_docs.py
python -m pytest tests -q -rs
```

`qualified/` contains final direct recording, truth, estimates, controls and plots.
`specular/` retains the failed stress and diagnostics, produced before the final
capture-provenance redaction and added explicit reversed-control gate; its
estimator still never read truth. `pilot/`, `direct/`, `cpu/` and their logs are
preserved earlier runs, not substituted for the final isolation evidence.
`source-hashes.json` records the implementation/check inputs. Unrelated services
were left running; no task simulator was started for this supplied-trajectory
example. GPU runs completed; no background task-owned GPU job remains.


## RF processing visualization follow-up — 20 October 2026

The user requested figures centered on what MUSIC extracts from generated I/Q.
The default example now also generates `iq-frequency.png` and
`music-processing.png` (with SVG exports), before the secondary tracking figure.
The `music-plots` CLI can process an existing recording without propagation.

[Frequency plots](music-visuals/iq-frequency.png) show the four site-0 complex
channel PSDs and the continuous element-0 frequency waterfall. PSD is two-sided,
in input-referred V²/Hz, using a 4096-sample Hann window, 2048-sample hop and no
FFT padding. [MUSIC processing](music-visuals/music-processing.png) shows actual
external MUSIC pseudospectra for both sites at three acquisition epochs,
covariance eigenvalues and measured spatial phase versus the MUSIC angle fit.
All six displayed peaks exactly match the ordinary consumer. Only saved ADC I/Q
and receiver geometry/calibration enter these products; no emitter truth is read.

The existing authoritative 100-window capture was replayed on CPU. The figures
were visually inspected. All 11 focused spectrum-unit and AoA tests pass in
`music-visual-tests.log`: the new tests verify positive/negative complex-I/Q
sidebands, integrated PSD voltage power and STFT hop timing. Documentation links
and whitespace checks pass. Numerical arrays, processing settings, input hashes
and implementation hashes are retained in `music-visuals/`. Earlier wheel and
closure hashes remain historical acceptance evidence and were not overwritten.
The plotting follow-up changes visualization and its entry points, not the
propagation, MUSIC estimator, tracker or previously reported accuracy metrics.
