# Dashboard presentation synchronization — 22 October 2026

The simulator previously advanced as soon as its I/Q writes returned, before the
skill necessarily finished the window. The host considered only the most recent
camera metadata, and the browser updated its charts before the corresponding
JPEG loaded. Transport counters also showed a newer epoch than the plots.

The producer now waits for a completed eight-channel skill epoch before stepping
flight. Both sides retain 128 timestamped frames. The host chooses the newest
complete RF epoch with an image no more than 60 ms away, without rewinding. It
holds the previous pair when no new pair is available. Counters, throughput,
producer measurements, histories and waterfall belong to the selected epoch.
The browser decodes the image before committing all mission widgets together in
one animation frame. Service health and controls remain responsive while held.

This coordination trades wall-clock speed for alignment. The 120 ms RF window,
240,000 samples per channel at 2 MS/s, waveform continuity, Doppler and geometry
are unchanged. A bounded capture offset remains; the display does not claim
identical camera/RF acquisition times or a 120 Hz scene update.

## Validation

- Supported CPU image, full suite: **305 passed, 169 skipped, 3 signal subtests
  passed**, 87.20 seconds. Optional tracking tests are skipped in that image.
- Dashboard service image, CPU execution of focused dashboard, HTTP, lifecycle
  and synchronization tests: **41 passed, 3 signal subtests passed**. Includes
  optional real MUSIC processing and two complete 120 ms / eight-channel windows.
- Real service regression launches `airsim_rf.dashboard_skill` as a separate
  process. It sends actual cf32 TCP blocks, queries the actual epoch/diagnostics
  HTTP endpoints, and verifies that neither seven channels nor successful TCP
  writes release the stepping barrier. After all eight channels and diagnostics
  complete, the stub stepping owner advances exactly once. Both windows and all
  480,000 samples per channel receive the normal final stream acknowledgement.
- `node --test tests/dashboard_presentation.test.cjs`: **3 passed**. Exercises
  the shipped JavaScript with delayed/failed image decoding, out-of-order status,
  mission restart and working pause/resume controls during image delay. Included
  in the container publication workflow.
- Actual headless Chromium using the shipped HTML/JS and controlled HTTP
  responses: an artificial **1.1-second JPEG delivery delay** leaves the image,
  clock, position, window count, payload count and PSD canvas unchanged. Releasing
  the JPEG advances them together, with no JavaScript errors. See
  [browser.json](browser.json). This is a presentation fixture, not a scientific
  mission or an RF performance measurement.
- Documentation links and whitespace checks pass.

No CUDA device is available in this environment. The service tests run its CPU
MUSIC consumer; the stepping owner is stubbed in the stream/barrier regression.
These checks do not establish full GPU/Unreal mission performance. The existing
software-rendered shared-scene/camera qualification remains in CI.
