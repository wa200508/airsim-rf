# Local RF mission dashboard

The primary use case is an actual ProjectAirSim drone over shared terrain,
Sionna propagation and continuous ADC I/Q, streamed to a separate MUSIC RF Skill process. A Python launcher serves the dashboard at `http://localhost:8765`.
The three process cards report actual supervised processes; the plots and data
rate come from the receiving skill, and the main image is a ProjectAirSim scene
camera. Camera or sensing failure is displayed separately from stream delivery.
For the actual scenario, antenna, waveform, mover and MUSIC implementation
locations, use the [question-by-question code map](code-map.md).

## Select or edit a scenario

Pass `--scenario /path/to/input-directory` to the launcher. All scenario inputs
are together under [scenarios/drone-orbit](../scenarios/drone-orbit); copy that
directory to change terrain, vehicles, flight, radios, waveforms, camera or RF
skill wiring without rebuilding containers. `--check-scenario` validates the
package without starting services; `--export-scenario DIR` exports the example.
Each mission saves its frozen inputs and pinned image IDs for reproduction.
See the [scenario package guide](scenarios.md). The values below describe the
packaged example, rather than fixed runtime constants.

## Recording and playback

Every new mission records automatically, independently of browser polling.
The RF producer journals source telemetry/camera; the skill independently
journals application results. Only the observer joins these records. The dashboard acts as a player for that saved output. The
**Saved run** selector opens the current or an older mission. **Play / Pause
playback**, the seek slider and the **0.5×, 1×, 2×, 4×** speed selector control
only the displayed simulation time. **Latest computed** follows the newest
available synchronized frame. The separate header **Pause computation / Resume
computation** buttons control flight/RF generation; playback can continue while
computation is paused.

The progress bar shows computed flight seconds against the requested mission
duration. The slider covers the portion with matching camera and RF data. A
slow renderer can leave computed RF ahead of the playable portion. At the
available end the player holds its coherent frame until more output arrives.
Seeking backward restores the camera, terrain track, telemetry, visibility,
MUSIC/PSD/eigenvalues/phase, waterfall, counters and original performance metrics
for that time. Playback does not rerun ray tracing or signal processing.

Replay-only startup skips all image pulls, GPU checks and service launches:

```bash
bash scripts/run_dashboard.sh --replay --run-dir recordings/dashboard --open
# No Docker installation is needed with the checkout launcher:
python3 scripts/launch_dashboard.py --replay --run-dir recordings/dashboard --open
```

Python 3.10+ with only its standard library is sufficient. An already-used
standalone script can replay using its cached host launcher, without contacting
Docker. A first standalone extraction still needs Docker and the published
image; use a checkout for a fresh machine without Docker. Replay-only mode
does not acquire the simulation run lock, write stop commands or remove any
containers, so a second player can inspect a recording while its producer is
still running. Use a different `--port` for an additional player.

Archives live at `<run-dir>/replays/<16-hex-run-id>/`:

- `manifest.json`: schema, creation time, requested duration, status and computed
  extent.
- `scenario.json`: saved terrain/map and receiver description.
- `frames/<simulation-nanoseconds>.json`: original per-window RF diagnostics and
  producer telemetry. Rolling histories and waterfall are rebuilt from the
  saved frames up to the selected epoch, with their original display limits.
- `camera/<frame-key>.jpg` and `.json`: immutable actual camera images and
  timestamp/geometry metadata. Replay retains the whole run; the live
  128-frame buffer does not truncate these files.

Each file is published by atomic rename. Temporary files and orphan JPEGs are
ignored, and already-published frames in stopped or interrupted runs remain
playable. A new mission gets a new directory; preparation and shutdown preserve
earlier recordings. Copy the run's `replays` directory to another machine to
review it, or remove individual archived run directories to reclaim space.
The reader indexes small summaries and bounds its full-diagnostic cache to 32
frames, rather than loading every spatial spectrum into memory.

This is a **dashboard recording**, containing camera, RF analysis results and
telemetry. It does **not** save the full continuous raw ADC I/Q stream or support
reprocessing it with a different skill. The displayed payload counters describe
the original stream, not bytes saved on disk. Historical runs made before this
recorder existed lack the required data and cannot be reconstructed completely.
Camera pairing still requires the same geometry hash and at most 60 ms of
simulation-time offset; playback does not interpolate RF data or fabricate
missing camera frames.
See the [recording and playback validation](../results/reviews/dashboard-playback-20261022/REPORT.md)
for the real stream-to-archive regression, replay-only restart checks and browser controls.

## Pull and run separate containers

Install Docker Engine, a compatible NVIDIA driver, NVIDIA Container Toolkit and
Python 3 on Linux x86-64. From a checkout run:

```bash
bash scripts/run_dashboard.sh --open
```

Or download only the standalone run script:

```bash
curl -fsSLo run_dashboard.sh https://raw.githubusercontent.com/wa200508/airsim-rf/main/scripts/run_dashboard.sh
bash run_dashboard.sh --open
```

The launcher honors an activated virtual environment by selecting
`$VIRTUAL_ENV/bin/python`; otherwise it uses `python3` from `PATH`. Set
`RF_DASHBOARD_PYTHON=/path/to/venv/bin/python` to choose an unactivated environment.
Python 3.10+ is checked before any image pulls; no numerical packages are needed
in the host environment. GPU libraries remain in their containers.

The script pulls the GPU RF service and extracts its standard-library dashboard
launcher and static assets to the host cache. The launcher pulls and inspects
**three separate published images**: `ghcr.io/wa200508/airsim-rf:dashboard-render`,
`:dashboard-skill`, and `:dashboard-gpu`. It requires matching source revision
labels and pins their local image IDs so tags cannot change underneath a run.
No source checkout, local image build, Docker socket mount into a container,
`priority2-local` image or host Blocks download is needed.

The simulator, skill and RF service containers are started concurrently. Before
the dashboard is offered, startup verifies simulator endpoints, a real camera
frame, skill health/ingress, configured geometry, CUDA/OptiX propagation and a
CPU-referenced CuPy render. A full initial scene-derived eight-channel ADC block
is delivered to and processed by the skill as a stationary startup snapshot.
That same window is reused at mission T+0 without duplicate transmission.
Before importing the DEM, the dedicated dashboard world removes the pinned
Blocks map's physical buildings, primitives and ground. Sky/lighting and engine
infrastructure remain. Clearing the native map and compiling kernels can take
several minutes; the default preparation timeout is 600 seconds.
The RF service connects to the prepared simulator
and skill, then waits with the world paused. Only after this succeeds is
**Launch mission** enabled at http://localhost:8765. It releases the prepared
mission; it does not pull images or create containers.

Chase-camera poses are queued with `wait_for_pose_update=False` and applied on
the next simulator/render step. Waiting synchronously for a renderer update
while the stepping owner holds the world paused can time out and report
`Chase camera gimbal pose update failed`. Preparation now exercises this camera
RPC before the first settling step and checks for an actual image before READY.
`--no-render` skips camera subscription and pose updates. The RF container uses
the writable `/run` directory for the SDK's `projectairsim_client.log`.

CI also runs `scripts/qualify_dashboard_camera.py` in the dashboard GPU image
without an NVIDIA device: packaged Unreal/software Vulkan, ten paused camera
updates, 1.2 simulated seconds, and a real 960×540 image with the requested camera
position. Independent CPU LiDAR probes check clear and terrain-blocked receiver
sight lines and three asymmetric terrain elevations against the shared triangle
mesh within 1 mm. Sionna's loaded mesh vertices and topology are also checked.
This checks SDK/render/geometry integration; it does not qualify a full
GPU mission. See the [recorded camera regression](../results/reviews/dashboard-camera-20261022/REPORT.md).

Failures stop task-owned containers and print the error/log location instead of
presenting a ready button. Normal future hardware/runtime failures remain
possible; startup checks establish readiness rather than a guarantee against
later failures. Stop shuts down the three containers. Use **Prepare services**
to prepare a new mission after stopping. Closing the host launcher also cleans
up its task-owned containers. Logs and metadata are in `recordings/dashboard`.
Use `--run-dir` for another output directory, `--duration 12` for a short flight,
or `--ready-timeout 1200` for slower first-use compilation.

Quit the host launcher with **Ctrl+C**. SIGTERM and terminal SIGHUP use the same
cleanup path, including during image pulls, preparation and service startup.
Cleanup stops/removes the three service containers and any active temporary
probe/preparation containers, reaps Docker client processes, removes the private
network and releases the host HTTP socket and run-directory lock. Cleanup errors
are printed, and later cleanup steps still run if one Docker command fails.
The standalone script also removes its extraction container if interrupted.
Closing a browser tab alone leaves the launcher running; **Stop** intentionally
keeps the web dashboard open for **Prepare services**.

The same `--run-dir` can be reused. Preparation builds a new geometry bundle in
a staging directory and replaces the previous generated bundle only after export
finishes; a partial previous bundle is replaced too. It retains recordings and
logs rather than deleting the run directory. Do not delete `/run/bundle` inside a
container to make normal restarts work. A filesystem lock prevents simultaneous
launchers from changing the same directory. After an untrappable SIGKILL or a
host crash, a later launcher holding that lock removes leftover containers and
networks carrying its run-directory label. It does not prune unrelated Docker
resources; resources from older, unlabeled launcher versions are outside that
automatic recovery mechanism.

`python3 scripts/qualify_dashboard_lifecycle.py --image ghcr.io/wa200508/airsim-rf:dashboard-gpu`
checks repeated preparation, cancellation, cleanup, reopening and stale-resource
recovery against real Docker. It uses CPU stand-ins for the services and does
not require or qualify CUDA. CI runs this check with its freshly built CPU image.
See the [recorded lifecycle results](../results/reviews/dashboard-lifecycle-20261022/REPORT.md).

The dashboard HTTP server runs in the **host Python process**, bound directly
to `127.0.0.1:8765`. A browser on the Docker host can open
**http://localhost:8765** without entering a container or finding a Docker IP.
The UI is served outside the Docker network for both rootful and rootless
Docker. To choose another host port, run
`bash scripts/run_dashboard.sh --open --port 8766` and open
`http://localhost:8766`. The loopback binding is for browsers on the same
machine; when running on a remote machine, forward its dashboard port over SSH
(`ssh -N -L 8765:127.0.0.1:8765 user@simulation-host`) and open localhost locally.

All service ports are published to loopback. All three containers use a private
Docker bridge with internal service DNS names; they do not depend on the
host network namespace. The camera uses bundled
software Vulkan/Xvfb; the GPU is used for RF. The simulator/RF images share their runtime assets. The CPU skill image uses an
independent Python base and contains no simulator or propagation dependencies.
CPU CI qualifies packaging and supervision; live GPU readiness is checked on
the actual machine every time the run script prepares the services.

Default duration is 120 simulated seconds, about two 62.8-second orbits. Use
`--duration 12` for a bounded check. Runtime speed depends on rendering and RF
processing; no real-time claim is made. Logs, actual poses, camera frames,
geometry bundle and receiver metadata are stored in the host `recordings/dashboard` directory.
Camera appearance uses presentation-only glTF color/emission; these values do
not set RF dielectric properties. Explicit UVs and tangent frames keep imported
meshes visible in the packaged renderer.
Use `--run-dir` for separate runs. The first run exports and places the same
terrain triangles in Unreal and RF.

## Scene and signal interpretation

The drone starts at RF `(250,0,200)` metres over the existing hills-and-valleys terrain. The native
Fast Physics path follower follows a 250 m radius left-hand circle sampled at
3° waypoint intervals, with a 25 m/s speed command, 12 m lookahead and heading
aligned to flight direction. Actual simulator pose and velocity readback,
rather than the ideal commanded circle, drive Sionna. The same `demo_terrain()` DEM used by the other examples supplies the hills and
drainage valley. Horizontal coordinates are scaled by four (800 m scene width),
heights by three (90 m relief), with RF base elevation 100 m. The exact transformed
triangles are shared by Unreal and Sionna. Natural hills partially shadow the
ground arrays during the orbit; there is no artificial ridge screen. The RF solver retains direct visibility
and all its supported first-order specular paths. Materials are illustrative.

The airborne QPSK emitter is observed by two stationary four-element ULAs at
915 MHz and 2 MS/s. Every 120 ms block contains 240,000 complex ADC samples per
channel. Counter-indexed QPSK generation supplies overlapping private finite
buffers with continuous symbol identity and TX FIR history/lookahead. Sources
are not silently looped. The consumer receives every ADC sample; its declared
24,000-sample snapshot bounds MUSIC/plot work per window.

The **Receiver I/Q stream** dropdown selects Site 0 or Site 1 (element 0 of
that coherent array). Spectrum and waterfall switch together at the displayed
RF epoch, including when paused or seeking saved runs. Old archives that stored
only Site 0 disable Site 1; they cannot reconstruct its missing spectra.

The **MUSIC Spatial Search** is a full **−180° to +180° circular search**. Angle
is around the circle; radius is the relative pseudospectrum (dB), with 0 dB on
the outer ring and −65 dB at the center. Zero degrees is each array's local
broadside. A linear array has paired front/back lobes: this view shows that
ambiguity rather than claiming a unique full-circle bearing. The scalar
cone-angle candidate searches −90° to +90°, removing the former artificial
±70° cutoff. Older saved partial searches remain partial arcs and are labeled
with their stored angular coverage. The eigenvalue and phase panels explicitly
label their vertical units as relative power (dB) and phase (rad).

MUSIC outputs an arrival **cone-angle candidate**. The full orbit introduces
ULA front/back and elevation ambiguity, and coherent reflections can bias peaks.
The demo does not infer successful sensing from the existence of a peak. The
visibility indicator is an independent shared-triangle direct-ray diagnostic,
not information supplied to MUSIC. When the direct path is blocked, propagation
and thermal receiver noise still produce ADC I/Q and data-plane traffic.

Each RF window verifies the AirSim terrain actor's transform, and compares
Sionna's actual direct-path count for **each of the eight antenna elements** with
independent intersections of the shared triangles. A mismatch fails capture.
The dashboard reports direct elements and reflected paths per element, rather
than inferring a direct path from MUSIC detection or received power. A blocked
link retains every supported first-order specular echo; if none exists in this
model, it contains receiver noise. Diffuse scattering, diffraction and terrain
transmission remain disabled. A visible/strong echo or a MUSIC candidate does
not establish an unobstructed direct path. The point-antenna RF model excludes
vehicle bodies and presentation-only receiver beacons.

The 2D map is below the camera, using the actual DEM grid and receiver positions
exported by preparation. The old hard-coded orange screen is removed. Dashed
amber lines and intersection crosses show blocked receiver-to-transmitter rays;
the camera's own view direction is a separate geometric question.

Camera frames carry their **simulation timestamps**, and image URLs identify
immutable frames. Both camera and skill retain 128 timestamped frames. The host
chooses the newest completed RF truth/skill epoch that has a camera within 60 ms
(half a 120 ms update interval), using the closest image. Buffered older images
remain eligible when the newest camera is ahead of processing. Presentation
never rewinds within a mission. It shows the measured camera/RF offset and how
far the displayed RF epoch trails the newest result. These are bounded-time
pairs, not a claim of identical capture times: propagation uses the window-start
pose; MUSIC/PSD use its first 12 ms of samples.

The stepping owner waits for a **generic TCP window acknowledgement** before
advancing the next 120 ms of flight. The consumer acknowledges only after its
handlers and complete-channel validation return. MUSIC finishes in that handler,
but the simulator never requests or reads MUSIC diagnostics or algorithm HTTP
responses. Any conforming consumer can acknowledge the same stream. TCP send
completion alone does not release the barrier. Stop cancels the wait; processing
failure or the 120-second timeout fails explicitly. Camera pose updates remain
asynchronous so a paused simulator cannot deadlock waiting for rendering.

The browser loads and decodes the selected immutable JPEG first, then commits
it with the map, clock, position, visibility, RF plots, waterfall, throughput,
payload/window counters and processing latency in one animation frame. Failed
or delayed images hold the entire previous mission view. Per-epoch diagnostics
include frozen histories and counters; they do not age or change while held.
Service health, errors and mission controls stay live so a stalled mission can
still be stopped. TX/RX labels are projected using the native image pose and
the applied camera mount, and are hidden when the shared terrain blocks their
anchor from the camera. This visibility check is separate from radio propagation.
This coordination can reduce simulation/wall-clock speed; it does not
change generated samples, waveform continuity, Doppler, terrain, trajectory,
reflection order or receiver sensitivity. The scene update remains 120 ms;
this dashboard does not claim 120 Hz operation.
The camera overlay and waterfall use the same mission-relative T+ origin.
See the [shared-scene and occlusion validation](../results/reviews/dashboard-scene-20261022/REPORT.md)
for independent probe measurements, the orbit scan and echo-only I/Q regression.
See the [synchronization validation](../results/reviews/dashboard-sync-20261022/REPORT.md)
for the earlier delayed-camera and HTTP-barrier baseline. The replacement generic
stream barrier and independent image qualification are documented in the
[boundary audit](../results/reviews/skill-boundary-20261022/REPORT.md).

The speedometer shows actual received cf32 payload bytes per wall second measured
at the displayed RF epoch (it is held with that frame);
configured rate and simulation/wall-clock ratio are separate. Eight channels at
2 MS/s require 128 MB/s of cf32 payload at real time. It does not count camera
traffic, headers, bytes only attempted by the sender, or simulated seconds as
wall seconds. Frequency plots use two-sided Hann-windowed PSD in V²/Hz.

## SQUALL / AMS-GRA boundary

The RF Skill is packaged as an independent CPU Docker container with a health
endpoint and the pinned `SquallRfControl` gRPC schema; see
[skill manifest](../deploy/dashboard/skill-manifest.json). It is a MUSIC consumer,
so acquisition commands and dynamic bare-UDP destination requests return explicit
unsupported responses. Status reflects the configured receiver rate/carrier; acquisition control is
explicitly rejected. The skill receives only receiver geometry/calibration and
post-ADC I/Q, with a separate result-only output mount. See the comprehensive
[boundary guide](skill-boundary.md) for code, packaging and compatibility limits.

The actual coherent data plane is the project's acknowledged framed TCP v2:
channel IDs, sequences, sample offsets, neutral acquisition timestamps, rate and
carrier are retained. Legacy v1 is translated at ingress. Stock SQUALL's bare SC16 UDP omits that coherent-array metadata.
This is a documented extension, not a claim of native RF MEL/VITA conformance.
The existing [native starter-kit overlay](../deploy/compose.ams-overlay.yaml)
remains the independently qualified radar integration; its fixed radar profile
must not be substituted for this MUSIC stream. A complete native coherent-array
MEL bridge would require an agreed synchronization/metadata extension.

`--no-render` is a diagnostic option only. It shows rendering disabled rather
than replacing the AirSim camera with a fabricated scene. A graphics-capable
Unreal/Vulkan environment is needed for the full requested view; the render
image also includes a software Vulkan/X display path for qualification.

The Chase camera follows **5 metres from the drone**, slightly above and behind
it, aimed at the midpoint of the two receiving sites. The relative mount
compensates for body attitude when each view is queued. The terrain uses a darker
visual base color and much lower emission to keep the nearby drone distinct.
These presentation changes do not modify RF materials, geometry or propagation.

## Rootless Docker

Use the rootless context owned by your login user, with no `sudo docker`:

```bash
docker context use rootless
docker info --format '{{json .SecurityOptions}}'
bash scripts/run_dashboard.sh --open
```

The launcher reads Docker security options to detect rootless mode. RF, skill
and scene-preparation containers use namespace UID 0, which maps to the
non-root login user on the host. Passing the host UID as the container UID
would instead select an unrelated subordinate UID and cause bind-mount
permission errors. The Unreal simulator uses namespace UID 10001 and reads
only its packaged assets. No dashboard container needs `--privileged`.

A temporary file confirms that the host can write a marker, the container can
read and replace it, and the host can read the result. A failure stops startup
with directory/context guidance. Existing wrong-owner files are not recursively
chowned or made world-writable: use a new `--run-dir`, or repair an old directory
using your administrator's normal ownership procedures.

The containers communicate through a task-owned Docker bridge and the aliases
`projectairsim` and `rf-skill`. The RF service connects directly to container
ports 8989/8990 and 8811, even when published host ports differ. This avoids
rootless host-network and host-loopback routing assumptions. Only the launcher’s
network and containers are removed on shutdown.

### NVIDIA access

With Docker 28.3+ and a recent NVIDIA Container Toolkit, native CDI is the
preferred rootless path. Toolkit 1.18+ normally refreshes its CDI specification
automatically. Check the device list and GPU access:

```bash
nvidia-ctk cdi list
docker run --rm --device=nvidia.com/gpu=0 ubuntu:24.04 nvidia-smi
bash scripts/run_dashboard.sh --gpu-mode cdi --open
```

If CDI devices are missing, follow the official
[NVIDIA CDI guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/cdi-support.html).
For installations using the legacy `--gpus` runtime, NVIDIA documents this
rootless configuration (these are host administration steps; the launcher
does not change daemon/runtime configuration):

```bash
nvidia-ctk runtime configure --runtime=docker --config="$HOME/.config/docker/daemon.json"
systemctl --user restart docker
sudo nvidia-ctk config --set nvidia-container-cli.no-cgroups --in-place
bash scripts/run_dashboard.sh --gpu-mode gpus --open
```

See NVIDIA's [rootless installation instructions](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html#rootless-mode)
and Docker's [rootless documentation](https://docs.docker.com/engine/security/rootless/).
The legacy `no-cgroups` setting is system-wide; follow NVIDIA's guidance for
hosts that also run rootful GPU workloads.

Default `--gpu-mode auto` tests CDI first on rootless Docker and then the legacy
runtime. A real CuPy device/kernel check must pass before any service starts;
full OptiX, scene-I/Q, camera and skill checks still gate Launch mission.
`--gpu-device 0` selects the GPU index or UUID (`all` is also accepted). A driver
or device permission failure is reported explicitly; there is no CPU fallback.

### Check rootless permissions and networking without a GPU

```bash
sh scripts/check_rootless_dashboard.sh
```

This optional diagnostic uses small temporary CPU containers to reproduce the
old UID failure and verify the corrected mount permissions, non-root service,
private service DNS and published loopback port. It cleans up its test containers
and network. [Recorded rootless qualification](../results/reviews/rootless-20261022/REPORT.md)
passed these checks on a real rootless daemon; full NVIDIA execution remains a
host-specific startup check rather than a claim from the CPU test environment.
