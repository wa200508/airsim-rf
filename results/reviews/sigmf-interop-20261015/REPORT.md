# Antenna configuration and external SigMF reader — 15 October 2026

The normal live CLI now accepts separate single-element TX/RX antenna pattern
and polarization settings. Omitted settings preserve half-wave dipoles with
vertical polarization. A real Runtime/GPU capture with `tr38901` TX and `iso` RX
completed three windows: **72,000 complex samples spanning 0.036 simulated
seconds** at 2 MS/s. Its [manifest](manifest.json) records the resolved arrays;
[configuration](radios.json) shows the user inputs.

The official **sigmf-python 1.13.0** reader validated and read both this recording
and a prior 960,000-sample/0.480-second turning capture. Raw codes, per-window
scaled volts and simulator epochs agree with the project's reader. New metadata
declares the optional `airsim_rf` 0.1.0 extension. The earlier capture lacks that
declaration and remains readable. Core validation does not independently validate
our custom extension's semantics or physical calibration.

The standalone `examples/process_sigmf.py` ran successfully using only NumPy and
SigMF imports, reporting 72,000 samples and 0.036 signal seconds. It disables
SigMF's automatic integer normalization, then applies each segment's recorded
volts-per-count. This demonstrates external library interoperability; MATLAB,
GNU Radio and physical SDR devices were not run.

Evidence: [new recording](current.json), [prior recording](legacy.json),
[standalone example](external-example.log), [live log](live-client.log),
[test log](standard-tests.log). Tests: **212 passed, 157 skipped** with the
optional SigMF package available. The lock now installs SigMF and its declared
XML dependency so CI exercises the external reader test. No vendor source is
copied into the repository.

Reproduce with the [walkthrough](../../../docs/scenario-to-iq.md), then:

```bash
python scripts/qualify_sigmf.py recordings/my-first-run --output recordings/sigmf-check.json
python examples/process_sigmf.py recordings/my-first-run/rx0.sigmf-meta
```

The first command requires this project and its `interop` extra (or the test
lock); the second requires only NumPy and SigMF. Capture used the P100-compatible
GPU image and real standalone Runtime; readback used CPU with no GPU access.
Raw data remains ignored locally and is identified by [hash](local-artifacts.json).
Service timings remain correctness-run measurements, not throughput comparisons.

The field declaration follows the [SigMF extension rules](https://sigmf.org/);
reader use follows [sigmf-python](https://github.com/sigmf/sigmf-python).
