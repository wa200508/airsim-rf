# Dashboard recording and playback — 22 October 2026

New missions record their actual camera images, per-window RF skill diagnostics,
and platform/visibility/timing data on the host run volume. Recording belongs to
the producer, not to browser status polls. The producer obtains the completed
skill epoch and publishes its diagnostic frame before releasing the next flight
step. An initial preflight window is recorded once and reused at mission T+0.
A compact skill response omits duplicated histories; playback reconstructs them
from the saved individual windows.

The dashboard now presents these recordings with a run selector, play/pause,
backward/forward seek, playback speed and a computed-flight-time progress bar.
Playback pause is separate from computation pause. The same image/measurement
commit barrier applies during seeks. A replay-only host Python process skips
Docker, GPU checks and simulation services entirely. Existing recordings survive
preparation, shutdown, process restarts and the live 128-frame buffer's eviction.

The archive contains GUI playback products, **not the full raw ADC I/Q stream**.
It cannot rerun a different signal processing skill on saved samples. Earlier
missions that did not record these products cannot be reconstructed completely.
No full CUDA/Unreal recording mission was run in this environment.

## Validation

- Supported CPU image, full suite: **312 passed, 170 skipped, 3 signal subtests
  passed**, 88.34 seconds. Optional tracking tests are skipped there. Subsequent
  focused runs cover the final integer-time seeking and live-health regressions.
- Dashboard service image, CPU execution of dashboard/recording/HTTP/lifecycle
  tests: **57 passed, 3 signal subtests passed**, 15.39 seconds. Includes actual
  TCP cf32 ingress, MUSIC/PSD, compact HTTP diagnostic retrieval and archive
  publication before the stub flight step. Two actual 240,000-sample windows
  across eight channels are processed and acknowledged.
- Real replay-only host process test, without bootstrap stubs: opens a saved run,
  seeks backward and forward through HTTP, fetches the corresponding JPEGs,
  shuts down and reopens a second time. A Docker tripwire is never invoked;
  simulation actions are rejected and no stop command is written.
- Archive regressions cover 140 frames beyond live retention, late camera
  pairing, clock/geometry mismatches, interrupted temporary files, partial runs,
  manifest/frame publication interruption, bounded full-frame cache, traversal
  rejection and integer-nanosecond seeking despite floating T+ representation.
- `node --test tests/dashboard_presentation.test.cjs`: **4 passed**, including
  atomic backward playback seek and playback pause making no simulation request.
- Actual Chromium against the real replay-only server and shipped HTML/JS:
  autoplay, pause, seek to T+0.240, matching image/clock/counters, 2× playback,
  older-run selection and latest-frame selection all pass. No simulation POSTs,
  JavaScript errors or mobile horizontal overflow. See [browser.json](browser.json).
  The saved frames in this browser test are presentation fixtures, not an RF
  mission or a performance benchmark.
- Documentation links, host stdlib HTTP tests and whitespace checks pass.
