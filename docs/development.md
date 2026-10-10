# Development and CI

GitHub Actions builds the CPU container, runs tests offline as the unprivileged
container user, smoke-tests radar, distributed workers, SDR and terrain examples,
and then publishes the tested image. [Workflow](../.github/workflows/container.yml).
CUDA tests skip in CPU CI; their qualification requires a separate run on compatible hardware.

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
