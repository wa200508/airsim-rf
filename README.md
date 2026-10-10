# airsim-rf

ProjectAirSim poses → Sionna propagation → complex I/Q → receiver filtering,
noise and ADC → timestamped SDR recordings. The project also provides radar
models and an AMS-GRA radar worker; continuous SDR uses a separate capture API.

| Goal | Start here |
| --- | --- |
| Run an offline example | [Setup](docs/setup.md#reproduce) |
| Record AirSim-driven SDR I/Q | [Two-radio live workflow](docs/live-workflow.md) |
| Understand the physical scenarios and plots | [Sensing gallery](docs/sensing-plots.md) |
| Reproduce measured GPU performance | [Benchmark setup](docs/setup.md#p100-basis-profiling) |

Live capture requires a separate ProjectAirSim server. Numerical/operator tests,
device qualification and actual server interoperability are distinct claims.

The latest measured 100-TX × 10-RX workload costs **44.68 wall seconds per
simulated signal second** on one P100: 11.1696 wall seconds for 0.250 signal
seconds per receiver. Its RF-update median is 371.859 ms for about 8.333 ms of
signal. This original low-relief-scene trajectory benchmark includes GPU propagation and rendering,
host preparation, receiver processing and loopback delivery. Live physics/RPC,
startup and distributed SDR transport remain unmeasured; all 30 updates miss the
120 Hz deadline. See [performance and optimization limits](docs/performance.md).

- [Radar, ESM and passive-geolocation figures](docs/sensing-plots.md)
- [Architecture and integration contracts](docs/architecture.md)
- [Rendering algorithms and reference operators](docs/rendering.md)
- [Terrain and propagation assumptions](docs/terrain.md)
- [External implementation and research references](docs/references.md)
- [Timing definitions](docs/timing.md) and [recorded measurement index](docs/measurements.md)
- [Development and CI](docs/development.md)
- [Historical runtime evidence](docs/archive/runtime.md) and [planning studies](docs/archive/planning.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

Historical reports and raw measurements remain under `results/` and
`research_results/`. They retain their original workloads and qualification;
renderer-only timings cannot be substituted for fleet throughput.
