# airsim-rf

> The direction-finding receiver application is the separately maintained
> [Direction Finding RF Skill](https://github.com/wa200508/DF-Skill), using MUSIC.
> See [repository separation and pinned deployment](docs/direction-finding-skill.md).
> The radar receiver is also separate: [Radar-skill](https://github.com/wa200508/Radar-skill),
> with [ownership and pinned deployment](docs/radar-skill.md).

ProjectAirSim poses → Sionna propagation → complex I/Q → receiver filtering,
noise and ADC → timestamped SDR recordings. The project also provides radar
models and an AMS-GRA radar worker; continuous SDR uses a separate capture API.

The primary workflow is the [localhost RF mission dashboard](docs/dashboard.md).
Select direction finding over shared terrain or a moving 77 GHz radar observing
a passive drone target. Separate containers run ProjectAirSim, Sionna acquisition
and the receiver skill. The launcher displays the actual simulator camera,
received I/Q, algorithm diagnostics and measured throughput.

## Find the code

Start with the **[question-by-question code map](docs/code-map.md)** for the
current dashboard: antennas, waveform, receiver laydown, mover, terrain,
propagation, I/Q generation and MUSIC. It links to the actual source lines,
lists the selected values and flags settings that must be edited together.

| What you need | Open first |
| --- | --- |
| Scenario, receiver locations, flight and transmitted samples | [Scenario catalog](scenarios/README.md); [compiler/engine adapters](src/airsim_rf/dashboard_scenario.py) |
| Native drone flight, antenna pattern, TX power and selected RF backend | [dashboard_producer.py](src/airsim_rf/dashboard_producer.py) — `run()` |
| SDR filtering, noise, ADC and path-to-I/Q dispatch | [sdr.py](src/airsim_rf/sdr.py) — `PlutoSDRProfile`, `SDRNetworkReceiver.capture()` |
| Live received-I/Q processing | [External direction-finding skill](https://github.com/wa200508/DF-Skill); [external radar skill](https://github.com/wa200508/Radar-skill/blob/main/src/radar_skill/app.py) — `RadarSkill.process()` |
| MUSIC algorithm call, steering vector and detection gate | [processing/music.py](src/airsim_rf/processing/music.py) — `estimate_bearing()`, `PhysicalULA`; [full MUSIC trace](docs/code-map.md#find-the-actual-music-algorithm) |

The MUSIC numerical implementation comes from `doa_py`; it is not vendored
here. The dashboard supports the QPSK direction-finding and 77 GHz FMCW radar scenarios; other LFM/FMCW radar and
offline tracking examples have separate configurations.

The **[simulation/skill boundary](docs/skill-boundary.md)** is explicit: skills
consume receiver samples and calibration; the simulator never reads MUSIC
results. Source telemetry and skill results meet only in the observer. The skill
image is built independently without simulation dependencies.

## Edit or select a scenario

Scenario data lives together under **[scenarios/](scenarios/README.md)**. Select the
current direction-finding example (`drone-orbit`) or the
[77 GHz radar racetrack with a passive drone target](scenarios/mmwave-radar/README.md)
(`mmwave-radar`). The dashboard has a **Scenario** drop-down; stop a mission before switching.

```bash
python3 scripts/launch_dashboard.py --list-scenarios
bash scripts/run_dashboard.sh --scenario mmwave-radar --open
```

Each package keeps its terrain, aircraft, radios, waveform and skill wiring nearby:
manifest, DEM/materials, vehicle, flight plans, radios and waveform definitions.
Copy that directory, edit it, and reuse the same containers:

```bash
cp -r scenarios/drone-orbit ~/my-rf-scenario
python3 scripts/launch_dashboard.py --scenario ~/my-rf-scenario --check-scenario
bash scripts/run_dashboard.sh --scenario ~/my-rf-scenario --open
```

The manifest also selects the RF skill image, arguments and ports. Preparation
freezes the full input package; each recording preserves its definition and
pinned image IDs. No image rebuild is needed for scenario edits. A standalone
launcher can export its example with `--export-scenario ~/my-rf-scenario`.
See the **[scenario package guide](docs/scenarios.md)** for arbitrary sampled
waveforms, multiple TX actors, circle/racetrack/waypoint/hold flight and custom skills.

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

The host launcher uses only Python's standard library. To run it from a virtual
environment (no project packages need to be installed there):

```bash
python3 -m venv .venv
source .venv/bin/activate
bash scripts/run_dashboard.sh --open
```

The script explicitly selects `$VIRTUAL_ENV/bin/python` when activated, otherwise
`python3` from `PATH`. It validates Python 3.10+ before pulling images. To select
an unactivated environment explicitly:

```bash
RF_DASHBOARD_PYTHON="$PWD/.venv/bin/python" bash scripts/run_dashboard.sh --open
```

The selected host Python is printed at startup. GPU/numerical dependencies
remain inside the containers; the host environment is used only for the launcher.

### Rootless Docker

The launcher detects rootless Docker automatically and preserves your selected
Docker context and `DOCKER_HOST`. Do **not** run the script with `sudo`:

```bash
docker context use rootless
docker info --format '{{json .SecurityOptions}}'
source .venv/bin/activate
bash scripts/run_dashboard.sh --open
```

The security options should include `name=rootless`. The launcher uses the
correct user-namespace UID for shared-file writes, checks host/container access
in both directions, and connects the services through a dedicated Docker bridge
network. It does not use `--network host` or change directory permissions to 777.
The simulator remains a non-root container user because Unreal requires that.

For NVIDIA access, install NVIDIA Container Toolkit and ensure either native
CDI or NVIDIA's rootless runtime is configured. Auto mode first tries CDI for
rootless Docker, then tests the legacy GPU runtime; it accepts only a working
GPU device/kernel. You can explicitly select either:

```bash
bash scripts/run_dashboard.sh --gpu-mode cdi --open
# Or, with NVIDIA's rootless legacy runtime configured:
bash scripts/run_dashboard.sh --gpu-mode gpus --open
```

See [rootless setup and permission troubleshooting](docs/dashboard.md#rootless-docker)
for NVIDIA setup references. If an older run directory has files owned by the
wrong mapped UID, choose a new directory with `--run-dir "$HOME/airsim-rf-runs/rootless"`;
the launcher checks access before starting the services. From a checkout the
script uses the current checkout launcher, so launcher fixes take effect after
`git pull` without waiting for a rebuilt image. Standalone downloads use the
launcher embedded in the published image.

The script pulls and verifies three images for the selected scenario:

- `ghcr.io/wa200508/airsim-rf:dashboard-render` — ProjectAirSim and camera.
- `ghcr.io/wa200508/airsim-rf:dashboard-gpu` — CUDA propagation and I/Q producer.
- Direction finding: the pinned `ghcr.io/wa200508/df-skill` image from its own repository.
- Radar: `ghcr.io/wa200508/airsim-rf:radar-skill-sha-<source revision>` — a public
  image built directly from the independent [Radar-skill](https://github.com/wa200508/Radar-skill)
  repository. See [source/image pins](docs/radar-skill.md). `dashboard-radar-skill`
  remains a compatibility image alias.

Only one receiver skill is launched for each mission; `dashboard-skill` remains a
legacy alias for the external DF image.

It starts the **three separate containers concurrently**, verifies compatible
image revisions and service health, checks CUDA/OptiX/CuPy, prepares the actual
scene and camera, and delivers an initial full I/Q window to the skill.
**Launch mission stays disabled until those checks pass.** No local image
builds, `priority2-local` image, Docker socket mount or manual simulator asset
download is required. First startup can take several minutes to pull images
and compile GPU kernels. A failed check prints an error and log location
instead of presenting a ready mission.

The dashboard web server runs directly in your **host Python process** and
listens on **127.0.0.1:8765**. Open it in a browser on that same host; no Docker
IP address, container shell or dashboard port mapping is needed. The private
Docker network connects only the simulator, RF service and processing skill.
Use `--port 8766` if the default dashboard port is occupied.

Open **http://localhost:8765** if the browser does not open automatically,
then click **Launch mission**. Pause/Resume computation controls the simulation; Stop shuts
down the task-owned containers. Use **Prepare services** to initialize a new
mission after stopping. Closing the launcher also cleans up its containers.
Logs and run products are stored in `recordings/dashboard` on the host.

The dashboard records every run automatically, even with the browser closed.
Use **Saved run**, **Play / Pause playback**, the time slider and **0.5×–4×**
speed to review recorded camera, map and RF diagnostics without recomputing.
The progress bar shows how much flight time has been computed; playback waits
at the end of the available recording while computation continues. **Latest
computed** follows the newest synchronized frame. Playback pause does not pause
the simulation.

To reopen saved runs immediately, with **no Docker or GPU startup**:

```bash
bash scripts/run_dashboard.sh --replay --run-dir recordings/dashboard --open
# Or use just host Python from a checkout:
python3 scripts/launch_dashboard.py --replay --run-dir recordings/dashboard --open
```

Runs are retained under `recordings/dashboard/replays/<run-id>/`, including
partial runs and previous missions. This records camera images, telemetry and
RF diagnostics for GUI playback. New runs also save bulk receiver I/Q under
`replays/<run-id>/iq/` by default (`mission.record_iq` in the scenario controls it).
These exact samples can be replayed into an unchanged RF skill without AirSim,
Sionna or a GPU. For **GNU Radio**, open the generated `view.grc` or `replay.grc`
in the saved `iq/` directory; the samples feed stock Complex File Sources
directly. See [GNU Radio development](docs/gnuradio.md) and
[capture and I/Q replay](docs/iq-replay.md) for Python and
container commands, disk requirements and SDR development tools. Older runs
have only the products saved at the time; their raw I/Q cannot be recovered.

The receiver dropdown switches the spectrum and waterfall between the two
receiving sites. MUSIC uses a circular 360° search with explicit front/back
ambiguity; its radius is relative power in dB. The chase camera sits 5 metres
from the drone, with darker terrain and terrain-occluded TX/RX labels. New
recordings include both receiver spectra; older recordings retain their
original data and camera view.

The terrain map below the camera uses the same DEM as AirSim and Sionna and
shows receiver sight lines and terrain intersections. Each receiver reports
direct elements and reflected paths; a blocked direct path can still deliver
echoes, or only receiver noise when no modeled echo exists. Camera and RF plots
are paired by simulation timestamps, with their time offset displayed (at most
60 ms). The simulator waits for each RF window's generic stream acknowledgement before
advancing. The browser decodes the paired image before updating the camera,
terrain map, plots, clock and counters together; if either stream falls behind,
it holds the last synchronized view. This favors alignment over wall-clock speed.

Quit the launcher with **Ctrl+C** to close the dashboard and remove its containers
and private network. Cleanup also runs on termination, terminal hangup, and
startup failure. Closing only the browser tab leaves the launcher running.
You can relaunch using the same run directory: generated geometry is rebuilt
safely, and recordings/logs are retained. **Stop** keeps the dashboard open so
you can use **Prepare services** for another mission.

For a short mission or slower first-use compilation:

```bash
bash scripts/run_dashboard.sh --open --duration 12 --ready-timeout 1200
```

See the [dashboard guide](docs/dashboard.md) for image overrides, output
locations and the sensing/modeling limits. Startup readiness is checked on
your hardware; CPU CI alone does not qualify a live GPU mission.

| Goal | Start here |
| --- | --- |
| Find the implementation or change antennas, signal, laydown or mover | [Question-by-question code map](docs/code-map.md) |
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

FMCW acquisition: [delayed echoes across pulse boundaries](docs/radar-late-echoes.md).
