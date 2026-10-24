[Documentation](README.md) · [Scenarios](../scenarios/README.md) · [Run dashboard](dashboard.md)

# Run the dashboard

Choose **[direction finding](../scenarios/drone-orbit/README.md)** or
**[FMCW radar](../scenarios/mmwave-radar/README.md)**. The launcher pulls the
published simulator, RF source and selected independent skill images, then
starts the three containers together.

## Pull and run separate containers

On Linux x86-64, install Docker Engine, a compatible NVIDIA driver and NVIDIA
Container Toolkit. The host needs Python 3.10+ with only its standard library.

```bash
# From a checkout:
bash scripts/run_dashboard.sh --scenario drone-orbit --open
# Or:
bash scripts/run_dashboard.sh --scenario mmwave-radar --open
```

Without cloning:

```bash
curl -fsSLo run_dashboard.sh https://raw.githubusercontent.com/wa200508/airsim-rf/main/scripts/run_dashboard.sh
bash run_dashboard.sh --scenario mmwave-radar --open
```

The selected host Python is printed at startup. An activated virtual environment
uses `$VIRTUAL_ENV/bin/python`; otherwise the launcher uses `python3` from `PATH`.
An explicit selection also works:

```bash
RF_DASHBOARD_PYTHON=/path/to/venv/bin/python bash scripts/run_dashboard.sh --open
```

Open **http://localhost:8765**. The web server runs in host Python, bound to
`127.0.0.1`, outside the private container network. Use `--port 8766` for another
port. For a remote host, forward it with
`ssh -N -L 8765:127.0.0.1:8765 user@simulation-host` and browse localhost locally.

Preparation checks image identities, file permissions, simulator endpoints,
shared geometry, a real camera frame, CUDA/OptiX and I/Q rendering, and a complete
initial skill acquisition. **Launch mission** enables only after readiness
passes on your machine. First startup may take several minutes for image pulls
and kernel compilation. Use `--ready-timeout 1200` for slower first-use setup.

The simulator/RF images must match each other. Skills are independently versioned
and pinned by the scenario: [DF image](direction-finding-skill.md) or
[radar image](radar-skill.md). No local image build or manual simulator download
is needed. CPU CI validates packaging; actual GPU readiness is checked locally.

<a id="select-or-edit-a-scenario"></a>

## Select a scenario

Use the **Scenario** dropdown after stopping a mission, or pass `--scenario ID`
or `--scenario /path/to/package`. Each package keeps terrain, aircraft, flight,
radios, waveform/mode and skill wiring together. See [the scenario catalog](../scenarios/README.md),
[editing guide](scenarios.md) and [clearance/noise controls](demo-tuning.md).
**Prepare services** freezes edits for the next mission. Copied packages retain
their own settings; changing the repository defaults does not overwrite them.

## Controls, stopping and restarting

| Control | Effect |
| --- | --- |
| Launch mission | Releases the prepared simulation and RF acquisition |
| Pause/Resume computation | Pauses/resumes generation; playback is independent |
| Stop | Stops mission containers and keeps the dashboard open |
| Prepare services | Reloads inputs and prepares another mission |
| Ctrl+C in the launcher | Removes its containers/network and releases its run lock |

Closing a browser tab leaves the launcher running. Termination, terminal hangup
and startup failure also trigger cleanup. The same run directory is reusable;
generated geometry is rebuilt safely while recordings/logs remain. A later
launcher recovers its labeled resources after a host crash; unrelated Docker
resources are unaffected.

The default directory is `recordings/dashboard`; choose a separate one with
`--run-dir /path/to/run`. Try `--duration 12` for a short first mission. Simulated
acquisition intervals are not wall-clock speed guarantees; see [profiling](profiling.md).

## Recording and playback

Every mission records camera, source telemetry and independent skill results,
even with the browser closed. **Saved run**, **Play/Pause playback**, the seek
slider and **0.5×–4×** speed review already computed output. The progress bar
shows computed flight time; playback holds at the available end. **Latest computed**
follows the newest synchronized view.

```bash
bash scripts/run_dashboard.sh --replay --run-dir recordings/dashboard --open
# Fresh checkout, no Docker or GPU needed:
python3 scripts/launch_dashboard.py --replay --run-dir recordings/dashboard --open
```

An already-used standalone script can replay through its cached launcher. Fresh
standalone extraction needs Docker; use a checkout for fresh CPU-only replay.
Runs live under `replays/<run-id>/`. Bulk post-ADC samples are in `iq/` when
`mission.record_iq` is enabled. Open `view.grc` / `replay.grc` in GNU Radio, or
stream the saved samples into another skill: [I/Q replay](iq-replay.md),
[GNU Radio](gnuradio.md). Review [disk requirements](iq-replay.md) before long runs.

## Scene and signal interpretation

The chase camera stays about 5 m from the drone and aims toward receivers or
targets. Labels may hide behind terrain. Both engines use the same DEM triangles;
actual native poses drive RF. [Scenario pages](../scenarios/README.md) explain
the different displays; [clutter](clutter.md) explains direct blockage and echoes.

Camera, telemetry and skill diagnostics are matched by simulation timestamp and
committed together after the image decodes. The allowed camera mismatch is at
most half the selected RF window. A delayed stream holds the prior coherent
view. A generic complete-window acknowledgement gates the next simulation
advance; the source never reads MUSIC or detection results. [Boundary details](skill-boundary.md).

## Rootless Docker

Use your rootless context without `sudo`:

```bash
docker context use rootless
docker info --format '{{json .SecurityOptions}}'
bash scripts/run_dashboard.sh --open
```

The launcher detects rootless mode and preserves `DOCKER_HOST` / the selected
context. A bidirectional shared-file probe checks permissions before startup.
It uses namespace UID 0 for writable RF/skill mounts, which maps to your host
login; Unreal runs as its required non-root container user. A private Docker
bridge supplies service DNS. Host networking and world-writable permission
changes are not required.

### NVIDIA access

Configure NVIDIA Container Toolkit for rootless Docker. Auto mode tries native
CDI and then the legacy runtime, accepting a working device/kernel check.

```bash
nvidia-ctk cdi list
docker run --rm --device=nvidia.com/gpu=0 ubuntu:24.04 nvidia-smi
bash scripts/run_dashboard.sh --gpu-mode cdi --open
# With NVIDIA's rootless legacy runtime configured:
bash scripts/run_dashboard.sh --gpu-mode gpus --open
```

See NVIDIA's [CDI guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/cdi-support.html)
and [rootless configuration](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html#rootless-mode).
For old wrong-owner files, choose a fresh `--run-dir` or repair ownership using
your normal administration process; the launcher does not recursively chown them.

### Check rootless permissions and networking without a GPU

```bash
python3 scripts/qualify_dashboard_lifecycle.py --image ghcr.io/wa200508/airsim-rf:latest
```

This checks lifecycle/file/network behavior with CPU stand-ins, not GPU readiness.
See [troubleshooting](troubleshooting.md) and [development checks](development.md).

## Skill-owned dashboard display

The selected skill supplies a data-only description of its plots, units, metrics
and selectors. The dashboard renders that description for live and saved frames.
[Display contract](skill-display.md).

## SQUALL / AMS-GRA boundary

The acknowledged TCP I/Q extension preserves coherent channel IDs, offsets,
rates and acquisition timestamps. It is distinct from bare SC16 UDP and is not
native MEL/VITA conformance. The radar skill legitimately commands its own
TX/RX; passive DF consumes I/Q. [Integration contracts](architecture.md#ams-gra-compatibility).
