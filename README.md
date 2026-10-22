# airsim-rf

ProjectAirSim poses → Sionna propagation → complex I/Q → receiver filtering,
noise and ADC → timestamped SDR recordings. The project also provides radar
models and an AMS-GRA radar worker; continuous SDR uses a separate capture API.

The primary workflow is the [localhost RF mission dashboard](docs/dashboard.md):
a large left-hand drone orbit in ProjectAirSim, shared-terrain multipath through
Sionna, and received I/Q processed by an independent CPU MUSIC RF Skill process. The
Python launcher displays the actual simulator camera, RF spectra/MUSIC diagnostics
and measured simulation-to-skill throughput.

## Launch the dashboard

On **Linux x86-64**, install Docker Engine, a compatible NVIDIA driver,
NVIDIA Container Toolkit and Python 3. Verify that your user can run Docker
and that NVIDIA GPU passthrough is configured.

From a fresh checkout:

```bash
git clone https://github.com/wa200508/airsim-rf.git
cd airsim-rf
bash scripts/run_dashboard.sh --open
```

Or launch without cloning the repository:

```bash
curl -fsSLo run_dashboard.sh https://raw.githubusercontent.com/wa200508/airsim-rf/main/scripts/run_dashboard.sh
bash run_dashboard.sh --open
```

The script pulls and verifies three published images:

- `ghcr.io/wa200508/airsim-rf:dashboard-render` — ProjectAirSim and camera.
- `ghcr.io/wa200508/airsim-rf:dashboard-gpu` — CUDA propagation and I/Q producer.
- `ghcr.io/wa200508/airsim-rf:dashboard-skill` — CPU MUSIC processing.

It starts the **three separate containers concurrently**, verifies matching
image revisions and service health, checks CUDA/OptiX/CuPy, prepares the actual
scene and camera, and delivers an initial full I/Q window to the skill.
**Launch mission stays disabled until those checks pass.** No local image
builds, `priority2-local` image, Docker socket mount or manual simulator asset
download is required. First startup can take several minutes to pull images
and compile GPU kernels. A failed check prints an error and log location
instead of presenting a ready mission.

Open **http://localhost:8765** if the browser does not open automatically,
then click **Launch mission**. Pause/Resume controls the simulation; Stop shuts
down the task-owned containers. Use **Prepare services** to initialize a new
mission after stopping. Closing the launcher also cleans up its containers.
Logs and run products are stored in `recordings/dashboard` on the host.

For a short mission or slower first-use compilation:

```bash
bash scripts/run_dashboard.sh --open --duration 12 --ready-timeout 600
```

See the [dashboard guide](docs/dashboard.md) for image overrides, output
locations and the sensing/modeling limits. Startup readiness is checked on
your hardware; CPU CI alone does not qualify a live GPU mission.

| Goal | Start here |
| --- | --- |
| Complete setup → matching geometry → recording → CPU processor | [Shared-scene quickstart](docs/quickstart.md) |
| Check what is qualified and what remains open | [Capability and acceptance matrix](docs/capabilities.md) |
| Integrate waveforms, radios and processing code | [Configuration and API interfaces](docs/interfaces.md) |
| Diagnose setup or capture failures | [Troubleshooting](docs/troubleshooting.md) |
| Run MUSIC AoA and emitter tracking on modulated I/Q | [Python challenge-inspired example](docs/aoa-emitter-tracking.md) |
| Run an offline example | [Setup](docs/setup.md#reproduce) |
| Build a scenario and process its I/Q | [Scenario-to-I/Q walkthrough](docs/scenario-to-iq.md) |
| Feed a separate signal processor | [TCP I/Q adapter](docs/iq-stream.md) |
| Configure the live recorder and server | [Live workflow reference](docs/live-workflow.md) |
| Understand the physical scenarios and plots | [Sensing gallery](docs/sensing-plots.md) |
| Reproduce measured GPU performance | [Benchmark setup](docs/setup.md#p100-basis-profiling) |

Live capture requires a separate ProjectAirSim server. Numerical/operator tests,
device qualification and actual server interoperability are distinct claims.
The installed `airsim-rf` command generates complete bundled inputs, checks a
capture plan, inspects recordings and reads I/Q on CPU. The shared-geometry
workflow uses static environment meshes with moving radios; priority 1 is
[qualified](results/reviews/priority1-20261020/REPORT.md). This is a local
experimental package; no publication or delivery is part of consolidation.

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
`research_results/`. They retain th