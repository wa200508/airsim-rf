# Local RF mission dashboard

The primary use case is an actual ProjectAirSim drone over shared terrain,
Sionna propagation and continuous ADC I/Q, streamed to a separate MUSIC RF Skill process. A Python launcher serves the dashboard at `http://localhost:8765`.
The three process cards report actual supervised processes; the plots and data
rate come from the receiving skill, and the main image is a ProjectAirSim scene
camera. Camera or sensing failure is displayed separately from stream delivery.

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
software Vulkan/Xvfb; the GPU is used for RF. The published service images share
pinned runtime dependencies and assets, but run as independent containers.
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
immutable frames. The skill retains 128 per-window diagnostic snapshots. The
host selects a matching RF truth/skill epoch nearest the image's timestamp,
within 60 ms (half a 120 ms update interval). It shows the measured camera/RF offset and
how far the displayed RF epoch trails the newest result. These are bounded-time
pairs, not a claim of identical capture times. When no pair is available it waits
or keeps the last paired view; it never combines a newer image with unrelated
latest plots. Projected radio labels are removed so they cannot show through a
hill. Live transport counters remain current and separate from the paired
spectrum/MUSIC diagnostics. Alignment affects presentation, not generated I/Q,
waveforms, terrain, trajectory, reflection order or receiver sensitivity.
The camera overlay and waterfall use the same mission-relative T+ origin.
See the [shared-scene and occlusion validation](../results/reviews/dashboard-scene-20261022/REPORT.md)
for independent probe measurements, the orbit scan and echo-only I/Q regression.

The speedometer counts actual received cf32 payload bytes per wall second;
configured rate and simulation/wall-clock ratio are separate. Eight channels at
2 MS/s require 128 MB/s of cf32 payload at real time. It does not count camera
traffic, headers, bytes only attempted by the sender, or simulated seconds as
wall seconds. Frequency plots use two-sided Hann-windowed PSD in V²/Hz.

## SQUALL / AMS-GRA boundary

The RF Skill is packaged as an independent CPU Docker container with a health
endpoint and the pinned `SquallRfControl` gRPC schema; see
[skill manifest](../deploy/dashboard/skill-manifest.json). It is a MUSIC consumer,
so acquisition commands and dynamic bare-UDP destination requests return explicit
unsupported responses. Fixed-profile status/tuning validation is implemented.

The actual coherent data plane is the project's acknowledged framed TCP v1:
channel IDs, sequences, sample offsets, simulation epochs, rate and carrier are
retained. Stock SQUALL's bare SC16 UDP omits that coherent-array metadata.
This is a documented extension, not a claim of native RF MEL/VITA conformance.
The existing [native starter-kit overlay](../deploy/compose.ams-overlay.yaml)
remains the independently qualified radar integration; its fixed radar profile
must not be substituted for this MUSIC stream. A complete native coherent-array
MEL bridge would require an agreed synchronization/metadata extension.

`--no-render` is a diagnostic option only. It shows rendering disabled rather
than replacing the AirSim camera with a fabricated scene. A graphics-capable
Unreal/Vulkan environment is needed for the full requested view; the render
image also includes a software Vulkan/X display path for qualification.

The Chase camera is gimballed inward from 100 m outside and 65 m above the
airborne transmitter, aimed between the drone and the two ground receivers.
Actual body attitude is removed from the relative camera transform. TX/RX la
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
