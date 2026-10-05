# Runtime metrics for one GPU per receiver

**Runtime context (2026-10-05):** Historical channel-only CPU measurements and hypothetical GPU query rates. Sub-millisecond ray arithmetic is not complete GPU renderer latency. See [current runtime and wall-clock costs](RUNTIME_STATUS.md) for comparable measurements, hardware, exclusions and ten-minute estimates.

See [the code-derived scaling model](SDR_COMPLEXITY.md) for stage-by-stage
complexity, CPU prediction checks and explicit GPU implementation estimates.

The CPU benchmark is a correctness and host-cost baseline. It is not a measured
GPU runtime, and CPU deadline misses do not establish GPU deadline misses.
The deployment target is **10 receiver workers, each with one GPU and all 100
transmitters**. A 100-TX/10-RX CPU solve divided by ten does not measure that
deployment. AirSim physics at 120 Hz has an 8.33 ms tick budget; the current
200 Hz pulse cadence has a separate, tighter 5 ms channel budget.

For the newer Pluto-class pipeline including completed I/Q, use [SDR runtime](SDR_RUNTIME.md). The propagation-only figures below exclude its CPU waveform and receiver chain.

## Per-GPU work

For the current single-element, one-bounce ground fixture with N = 1,028 diffuse
attempts per link, T = 100 transmitters and M = 1 specular plane:

```
diffuse attempts = T*N                              = 102,800 / pulse / GPU
visibility queries <= 2*T*N + T*(1+2*M)             = 205,900 / pulse / GPU
candidate paths <= T*(N+1+M)                       = 103,000 / pulse / GPU
compact channel capacity = paths*(8+4+4) bytes      = 1.648 MB / pulse / GPU
```

Each diffuse sample needs a first-hit ray and at most one opposite-leg shadow
ray. LoS adds one query per link; a specular plane adds at most two. Misses and
occlusion reduce active queries. This is a work-count upper bound, not a scene
complexity bound: a detailed land-cover scene's BVH traversal and material/field
cost can differ substantially from a two-triangle ground plane.

At 200 pulses/s, each GPU needs at least **41.18 million queries/s for the ray
stage alone**, if it spends the entire 5 ms on tracing. At 120 solves/s that
becomes 24.71 million queries/s. Field evaluation, proposals and other work
need their own share of those budgets. Ten receivers multiply fleet work by ten,
without dividing each receiver's latency by ten.

Exporting the maximum compact channel every pulse is 329.6 MB/s per worker at
200 Hz, or 3.296 GB/s across ten workers. Actual retained coefficients are fewer;
padded CIR arrays and temporaries can add bytes. These figures cover complex64
gain, float32 delay and float32 Doppler only. They exclude IQ, geometry, BVH,
intermediate field buffers and allocator reservations, so they do not specify
minimum VRAM. Peak host RSS also does not estimate VRAM.

## Measured host cost and conditional GPU cost

The new CPU run used two Dr.Jit threads, a two-core quota and the previously
populated JIT cache. Ten timed moving-platform epochs followed three warmups:

| Region | Median | p95 | Interpretation on a CUDA worker |
| --- | ---: | ---: | --- |
| Total channel + poses + NumPy export | 48.6 ms | 49.2 ms | CPU measurement only |
| NumPy proposal sampling | 15.3 ms | 16.0 ms | Host code remains on CPU |
| Antenna proposal table preparation | 2.03 ms | 2.10 ms | Mixed backend evaluation and host export; changes on CUDA |

The sampling timer covers seed setup, allocation, weighted cell selection,
angular jitter, trigonometry and filling the proposal buffer. It stops before
uploading that buffer to Mitsuba. It adds no stage-wide GPU synchronization.
The full solve timer already synchronizes completion. Other solve work remains
mixed host/device, so subtracting these regions does not produce a pure GPU
kernel time. Per-epoch timings and assumptions are in
[the JSON report](benchmarks/results/scattering_cpu_100tx_1rx_gpu_planning.json).

The following rates are **hypothetical effective scene-query throughput**,
not measured GPU performance or vendor RT-core ratings:

| Assumed effective queries/s | Ray stage at query-count upper bound | Ray stage + unchanged measured host sampling |
| ---: | ---: | ---: |
| 100 million | 2.059 ms | 17.38 ms |
| 250 million | 0.824 ms | 16.14 ms |
| 1 billion | 0.206 ms | 15.52 ms |

The last column is a subtotal under those assumptions, not an end-to-end
prediction. It excludes proposal table preparation, field evaluation,
compaction, launches/synchronization, upload/export, poses, IQ, AirSim and
transport. A different deployment CPU changes the sampling cost. A faster GPU
does not accelerate the current NumPy draws. Moving proposal sampling onto the
device, and caching proposal tables while antenna patterns stay unchanged,
are immediate optimization priorities. Sample count and TX/RX coverage must
remain unchanged while doing that work.

The planning model is:

```
worker latency = host preparation + proposals + scene queries + RF fields
               + compaction + device/host transfers + IQ synthesis + transport
```

Only the channel portion is currently benchmarked. GPU-resident proposals and
IQ synthesis are future work. A 120 Hz physics tick can advance poses while RF
workers schedule pulse epochs separately; this does not remove the required RF
throughput or establish acceptable latency. Neither a specific GPU model nor a
minimum VRAM capacity is validated yet. CUDA capability and compatibility with
the pinned Sionna/Mitsuba/Dr.Jit stack are prerequisites, not a throughput guarantee.

## Measure the actual target

The [DEM terrain scenario](TERRAIN_SCENARIO.md) has 800 specular planes. Its
per-worker query-count upper bound is 365,700 per pulse rather than the flat
fixture's 205,900. Use `--scene terrain` to measure that geometry;
`benchmark_scattering.py` now derives its budgets from the actual plane count.

On a CUDA-capable host, record the GPU name, driver and VRAM, then run a **one
receiver** benchmark on each assigned device. This command refuses CPU fallback:

```bash
nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv
CUDA_VISIBLE_DEVICES=0 .venv/bin/python benchmarks/benchmark_scattering.py \
  --backend cuda --tx 100 --rx 1 --samples-per-link 1028 \
  --deployment-receivers 10 --pulse-hz 200 --warmup 20 --iterations 200 \
  --output ground_gpu_0.json
```

Preserve both cold and cached measurements. Changing retained-path counts can
trigger compilation on either backend; warmups do not guarantee all future
shapes are compiled. Then exercise all ten workers concurrently with their
actual host CPU allocation, terrain, motions and waveform duty cycle. Measure
end-to-end IQ deadlines, queue growth, transport load and peak device memory.
The existing published test image is a CPU image; its successful tests do not
validate CUDA deployment or GPU memory sizing.

`benchmark_scattering.py` now emits `stage_timings` and `gpu_deployment` on both
backends. CPU reports mark GPU channel runtime and deadlines unmeasured. A
multi-receiver batch leaves the per-worker host sampling estimate unset rather
than inventing it by dividing a batched timing.
