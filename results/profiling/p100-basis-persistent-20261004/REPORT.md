# P100 persistent-buffer and channel-reuse screening — 2026-10-17

**Status: exploratory screening; no production optimization is qualified.**
The P100 was accessible through `airsim-rf:p100-modern-gpu` (Tesla P100-PCIE-16GB,
driver 580.178.04). Host `nvidia-smi` could not reach the driver, but the NVIDIA
container runtime exposed the card.

## Scope

This is the renderer-only synthetic 100-TX × 1-RX case: 1,028 valid paths per
link, 16,667 output samples at 2 MS/s, 2,048-sample blocks, warp projection,
100 links per batch, FP64/complex128, three warmups and 30 timed captures per
case. The current source revision was `28ef5be0b815955aa4f9679728a659907dab86b2`;
each raw JSON records source-file SHA-256 values and the exact arguments.
Runs used the existing GPU image and did not alter source code.

Each case passed the benchmark's full-window CPU-basis comparison and direct
render checks. The ordinary control and buffer-only cases reported normalized
full-window RMS error `1.9754e-12`. This checks the finite interpolation
operator, not physical RF accuracy. These results exclude propagation,
AirSim, receiver filtering/ADC, and transport.

## Results

| Case | Mean ms | Median ms | p95 ms | Mean change vs control | Accuracy |
| --- | ---: | ---: | ---: | ---: | --- |
| Control, 60 windows across two runs | 64.407 | 63.773 | 68.068 | — | Pass |
| Persistent host/device buffers, 60 windows across two runs | 62.802 | 62.255 | 65.974 | −2.5% | Pass |
| Persistent buffers + fused warp projection, one run | 62.602 | 62.859 | 65.228 | −2.8% | Pass |
| Reuse same channel for four windows; refresh source every window | 57.673 | 56.179 | 65.306 | −10.5% | Pass |
| Stable channel for all windows; refresh source every window | 54.924 | 54.365 | 57.469 | −14.7% | Pass |

The control and buffer-only comparisons were repeated independently. Their
run means were 64.521/64.294 ms and 62.984/62.621 ms, respectively. The fused
case was not repeated, and its small difference from buffer-only does not show
a reliable incremental gain.

Every 30-window series missed the 8.333 ms deadline. Channel-reuse cases are
conditional stationary-channel bounds: they keep the channel fixed for four
windows (about 33 ms) or the entire 250 ms capture while changing source data
each window. They do not represent moving-flight or per-window path solving.
They indicate that reuse can amortize renderer setup when a caller can prove
the channel revision is unchanged; they do not justify skipping channel updates
for moving radios.

## Disposition

Persistent buffers show a small, repeatable renderer-call reduction in this
screening run. Fused projection shows no established incremental improvement.
Neither result closes the substantial gap to 120 Hz, and no default or live
workflow is changed. The largest potential gain here comes from channel reuse,
but it only applies when channel state is genuinely stable. A production change
would need representative end-to-end workloads, repeated controlled timing,
and qualification of cache invalidation and memory lifetime.

Raw benchmark records are in the adjacent JSON files. The initial test log is
retained as `cuda_baseline.log`; it is not a timing record for this comparison.
