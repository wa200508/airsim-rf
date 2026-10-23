# Development and CI

For a source reading order and precise edit locations in the dashboard/RF/MUSIC
pipeline, start with the [code map](code-map.md). It distinguishes the running
dashboard from offline examples, generic API defaults and benchmark scenarios.

GitHub Actions builds the CPU container, runs tests offline as the unprivileged
container user, smoke-tests radar, distributed workers, SDR and terrain examples,
and then publishes the tested CPU and GPU dashboard images on `main` and version tags. [Workflow](../.github/workflows/container.yml).
CUDA tests skip in CPU CI; their qualification requires a separate run on compatible hardware.

The CPU image now also builds a local wheel. Before any existing publication
stage, CI installs that wheel into an isolated virtual environment (sharing only
the image's tested dependencies), changes to `/tmp`, and exercises packaged
examples, preflight, CPU propagation/receiver processing and recording consumers.
The qualification rejects imports from the source checkout. This catches missing
wheel assets and accidental working-directory dependencies.

For a full fresh-dependency local check, run `scripts/qualify_local_package.sh`
as described in the [priority 2 report](../results/reviews/priority2-20261020/REPORT.md).
It verifies cached upstream source pins and cleanliness, creates an empty Python
environment, installs the lock plus the wheel, runs `pip check`, and executes the
whole CPU suite against that installation. No GPU or simulator is used.
The separate installed-wheel live check reuses the pinned P100 dependency stack;
those versions must not be substituted for the ordinary CPU release-test lock.
All artifacts/images from this consolidation remain local; no publication job
was triggered.

The optional [AoA/tracking example](aoa-emitter-tracking.md) uses the tracking
extra and its separate lock. Its tests skip when those optional packages are
absent. `tests/conftest.py` collects cyclic garbage between tests: the combined
tracking/renderer suite otherwise exposed a native Dr.Jit 1.5.0 abort during GC
inside frozen-kernel capture. This is a test isolation workaround, not a
production runtime fix or an established upstream root cause. The
[priority 3 report](../results/reviews/priority3-20261020/REPORT.md) retains the
failed runs and the complete passing suite with the workaround.

The failure at commit bf58884 was a reporting regression: historical records
without sample rate or measured wall totals caused the basis report to crash.
The report now shows unavailable normalized fields as `—`, retains the invalid
accuracy label, and excludes instrumented records from throughput tables. When
actual per-call totals exist, it uses their sum; median is never substituted for
mean or total wall service.

```bash
python3 scripts/check_docs.py
python3 scripts/update_timing_context.py --check
.venv/bin/python -m pytest tests -q
```

The [measurement index](measurements.md) is generated once from published JSON.
Do not copy its tables into every guide. Historical stage tables live only in
[the runtime archive](archive/runtime.md); update them with
`scripts/update_runtime_docs.py` and `scripts/update_profiling_breakdown.py`.
Keep scopes and simulation-time denominators beside new timing claims.

## Color-map convention

Full-color 2D sensor plots must be spectrum waterfalls (frequency versus
acquisition time, color = spectral power/PSD) or properly processed range–Doppler
maps (range versus Doppler, color = response power). Record window/hop/FFT size,
units and capture duration for waterfalls; record fast-time range processing,
PRF, pulse count, coherent observation length and Doppler ambiguity limits for
range–Doppler maps. FFT padding does not add physical resolution.

Do not relabel geometry/height/along-track intensity or interreceiver TDOA/FDOA
ambiguity surfaces as those displays. Use line profiles for other observables.
Do not fill temporal gaps between short captures to imply a continuous waterfall.
[Definitions and current figures](sensing-plots.md).

## Documentation and scientific product checks

`check_docs.py` checks files, Markdown fragments and duplicate explicit citation
IDs outside code fences. `check_sensing_products.py` checks both gallery
manifests, input hashes, PNG/SVG presence and nonfinite metrics against explicit
status and raw quantizer-zero counts. Run it in the scientific Python environment:

```bash
python scripts/check_sensing_products.py
```

CI exercises both sensing-analysis and physical-scenario generators. Still inspect
rendered outputs: machine checks cannot establish legible labels, meaningful axes,
normalization, scenario interpretation or physical realism. Undefined values are
acceptable only when both metadata and plots explain them. Current guides are
short entry points; dated research is in `docs/archive/`.

## Architecture qualification

Run `python3 scripts/check_architecture.py` to check all first-party package
roles and source/receiver import restrictions. CI also builds the independent
skill and runs `scripts/qualify_skill_boundary.py` with networking disabled: an
actual MUSIC service processes neutral coherent buffers without simulator code
or source dependencies. See [boundary contracts and limits](skill-boundary.md).

## GPU dashboard publication

`Dockerfile.dashboard` layers the pinned CUDA 12.2 CuPy libraries,
Mitsuba 3.8.0 / Dr.Jit 1.3.1 compatibility stack, tracking lock and software
Vulkan/Xvfb over the CPU dependency image. It checksum-verifies and bundles the
upstream Blocks release for the `gpu` and `render` targets. The `skill` target
uses a separate slim Python base with an explicit receiver-source allowlist and
no simulation dependencies.
The main workflow builds/tests the separate service images and publishes
`ghcr.io/wa200508/airsim-rf:dashboard-gpu`, `:dashboard-skill` and
`:dashboard-render`, plus immutable `dashboard-<role>-sha-<full-commit>` tags.
A final anonymous pull verifies public access to the dashboard image.

CI runs the dashboard container smoke test with networking disabled, checking
installed pins, the bundled simulator's shared libraries, scene preparation and
the packaged host launcher assets. It also tests child-process supervision and checkout defaults.
No GPU is present on the hosted runner; this does not certify CUDA execution
or mission performance. The normal CPU test image retains its newer
Mitsuba/Dr.Jit lock, while the dashboard image uses the explicit compatibility
pins rather than changing the CPU release environment.
