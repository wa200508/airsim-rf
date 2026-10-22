# Development and CI

GitHub Actions builds the CPU container, runs tests offline as the unprivileged
container user, smoke-tests radar, distributed workers, SDR and terrain examples,
and then publishes the tested image. [Workflow](../.github/workflows/container.yml).
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
