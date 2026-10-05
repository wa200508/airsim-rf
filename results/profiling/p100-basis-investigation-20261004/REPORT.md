# P100 renderer latency and timestamp investigation

The previous updates were verified published at `cc5efad`. This investigation runs the same numerical code in the immutable full-run image (source `b4d48f5`), with the same Pascal-compatible CuPy/CUDA libraries and LLVM-reference startup workaround. No production renderer algorithms, precision, path budgets or accuracy thresholds were changed.

## Exactly what the median measures

One wall-clock timed capture for 100 independent TX streams coherently summed into one RX output: 16,667 samples at 2 MS/s, 1,028 valid paths per link, arbitrary sampled complex input with 32-tap interpolation, FP64/complex128, maximum delay 100 microseconds, physical Doppler +/-2,500 Hz. The numerical path arrays change between captures, but capture time starts at zero; this is not an advancing simulation clock or live source pipeline.

The timed region starts after synthetic channel updates and includes host validation/packing, private copies/uploads, delay sorting and interpolation maps, basis construction, path projection, private FFT filtering, reconstruction, coherent receiver sum, and synchronized final output download. It excludes input source generation, synthetic channel-array update generation, path tracing, CPU reference calculations, correctness tests, first-use/JIT, warmups, receiver noise/filter/ADC, sample-clock resampling, AirSim, transport and queues. It is synchronized renderer wall time, not pure GPU kernel time.

## Why 100 TX is still slow

The default kernel groups eight links and divides each window into nine temporal blocks: eight 2,048-sample blocks and one 283-sample block. Thirteen link groups produce 117 projection launches and 117 reconstruction launches. There are 27 temporal basis coefficients for a full block and 12 for the tail, over 233 delay coefficients. Each of 102,800 physical paths contributes to all 32 interpolation taps for every temporal basis coefficient. The projector evaluates **750,028,800 weighted complex contributions per output window**. This basis reduces path/sample expansion but still rebuilds a substantial path-dependent filter bank each window.

The original separate capture reported projection 64.74 ms, FFT/filtering 23.45 ms, delay mapping 19.88 ms, temporal construction 13.57 ms, packing/upload 7.64 ms, reconstruction/sum 3.63 ms and final export 0.088 ms. These spans may include host dispatch/idle gaps and cannot be added to the unprofiled median.

A tighter separate instrumented capture placed events immediately around warmed raw kernel calls, excluding surrounding array allocation/stage work: **117 projection calls summed to 67.52 ms**, and **117 reconstruction calls to 2.73 ms**. Its wall time was 140.64 ms. Small dispatch gaps remain possible, so these are kernel-call event spans rather than Nsight instruction-level measurements. Projection is materially expensive; allocation or final download alone cannot explain the result.

## Same-workload batch sweep

Each configuration uses three warmups, ten timed captures, all independent input streams, all paths, the same output budget and capture-level CPU/direct references. Only link grouping changes.

| Links/group | Median | p95 | Capture checks |
|---:|---:|---:|---|
| 8 | 123.329 ms | 124.500 ms | PASS |
| 16 | 136.393 ms | 138.081 ms | PASS |
| 32 | 135.350 ms | 138.759 ms | PASS |
| 100 | 138.002 ms | 143.128 ms | PASS |

Increasing the batch size does not recover the target; it slightly worsens these observations. This argues against link-group launch count being the dominant explanation. It does not prove that host overhead is zero, or that eight links is optimal for every configuration.

## Correctness failure isolated

The required suite's split capture starts 68,500 ns after Unix epoch 1,790,000,000,000,000,000 ns with a 12,000 Hz oscillator offset. The code first converts the absolute timestamp to floating-point seconds and multiplies it by the oscillator frequency before reducing modulo one cycle. This loses the small phase increment.

The predicted excess phase is **0.0139408174 radians**, giving predicted relative complex error **0.0139407045110980**. The GPU reproduction's observed relative RMS error is **0.0139407045110990**. Applying only that predicted phase rotation leaves **6.20e-12** relative residual; changing only oscillator offset to zero also leaves **6.20e-12**. This isolates the reported failure to absolute-time oscillator phase precision, rather than path projection approximation. See `timestamp_diagnosis.json` and reproducible `diagnose.py`.

No repair is applied here. The required suite remains failed. Per-capture comparisons at zero-based times passing do not qualify coherent split streaming at Unix-scale timestamps. The original failing test also contains later finite-boundary/equal-clock assertions that were not reached after its first failure.

## What the evidence supports next

1. Repair absolute-time oscillator phase calculation using integer nanoseconds and stable modular phase before conversion to floating point, consistently across GPU/CPU basis and direct references. Re-run the full mandatory suite without relaxing tolerances.
2. Optimize the projector's repeated interpolation/basis accumulation, testing shared reuse/tiled layouts or a mathematically equivalent matrix formulation while retaining all paths and FP64. Benchmark against the original outputs and timing budgets.
3. Profile private FFTs and delay-map construction next: projection optimization alone does not establish the roughly 15x overall improvement needed for the 100-TX deadline.
4. Only after renderer qualification, integrate scene propagation and mandatory receiver DSP. The 1-/4-TX timing success is a renderer observation, not complete RF service at 120 Hz.

No wider transmitter scaling was performed. The earlier near-16-GiB boundary belonged to legacy ray tracing; this renderer collection sampled only 625 MiB of whole-GPU memory. Memory capacity and numerical correctness are distinct from this computation cost.

[Original full report](../p100-basis-full-20261004/REPORT.md) · [Summary](summary.json) · [Kernel diagnosis](kernel_diagnosis.json) · [Timestamp diagnosis](timestamp_diagnosis.json) · [Checksums](checksums.json)
