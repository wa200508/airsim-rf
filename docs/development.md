# Development and CI

GitHub Actions builds the CPU container, runs tests offline as the unprivileged
container user, smoke-tests radar, distributed workers, SDR and terrain examples,
and then publishes the tested image. [Workflow](../.github/workflows/container.yml).
CUDA tests skip in CPU CI; their qualification is a separate P100 collection.

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
