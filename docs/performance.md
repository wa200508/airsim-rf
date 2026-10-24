[Documentation](README.md) · [Scenarios](../scenarios/README.md) · [Run dashboard](dashboard.md)

# GPU renderer qualification and optimization limits

The **[profiling page](profiling.md)** owns current timing context and the generated
median/SD and p95 stage tables. This page explains the historical P100 operator,
its qualification and the limits of promoting optimizations. These workloads are
separate from both current dashboard scenarios.

## What the optimizations guarantee

The production GPU path selects temporal rank using the maximum absolute Doppler
of **every** current path and the existing interpolation error bound. It still
rejects paths outside the declared range; zero-gain paths participate in range
checks. Higher Doppler requires higher rank, so the measured speedup is not a
promise for every scene. Warp groups select 8, 16 or 32 lanes from that rank;
all paths remain included. Reused source staging overwrites valid regions and
clears uncovered history/padding. Declared history/lookahead remains required.

Qualification covered changing delays, zero-gain paths, high Doppler/high rank,
boundaries, split captures, Unix epochs, subgroup widths and private inputs.
These tests establish agreement with the declared finite interpolation operator;
they do not establish calibrated RF accuracy or live simulator interoperability.
The [matched historical control and resulting fleet costs](../results/profiling/p100-adaptive-pipeline-full-20261008/REPORT.md) retain the recorded comparison; the profiling page presents the selected timing series.

Delay-support trimming, alternate FFT lengths, single-precision delay mapping and
fused projection remain **disabled experimental controls**. Trimming was slower
in the support sweep; alternate FFT shapes produced small platform-dependent
gains. They are not required by the live workflow. No further scenario tuning is
being promoted as a general optimization.

[Call traces](../results/profiling/p100-call-trace-20261008/README.md),
[temporal controls](../results/profiling/p100-temporal-sweep-20261008/README.md),
[support controls](../results/profiling/p100-support-sweep-20261008/README.md) and
[warp/FFT controls](../results/profiling/p100-kernel-sweep-20261008/README.md)
preserve the evidence. GPU event spans are diagnostic and can include dispatch
gaps; synchronizing download calls can absorb earlier queued GPU work. Neither
is an independent end-to-end throughput measurement.

The P100 compatibility adapter is deliberately version-specific: it replaces an
unsupported path-counter operation and patches Sionna path-storage allocation.
Exact version/layout guards fail on unsupported changes. This remains an
isolated dependency-compatibility constraint, not a portable optimization;
upgrading dependencies requires fresh qualification. The live command records
those versions and whether the adapter was enabled in its manifest.

Remaining costs include host source copies, serial receiver dispatch and private
input transfers. GPU-resident ingestion or overlapping independent work may help,
but each would need representative workloads and explicit traffic accounting.
Live timestamp continuity, recordings and synchronized display are separate integration responsibilities.

## Scene identity for matched comparisons

The published performance captures predate the 0–30 m sensing terrain. Timing
commands now explicitly load `benchmarks/scenes/terrain_benchmark_v1.xml` and its
immutable original low-relief mesh, recovered from revision `150b40e`. New reports
include XML/mesh hashes and a conservative clearance certificate for the full
trajectory interval. The taller `terrain.xml` remains the sensing demonstration.
Changing terrain is a new workload, not an optimization speedup. Historical
result files retain their original metadata and must be interpreted using their
recorded source revision.
