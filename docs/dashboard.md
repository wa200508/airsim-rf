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
The RF service connects to the prepared simulator
and skill, then waits with the world paused. Only after this succeeds is
**Launch mission** enabled at http://localhost:8765. It releases the prepared
mission; it does not pull images or create containers.

Failures stop task-owned containers and print the error/log location instead of
presenting a ready button. Normal future hardware/runtime failures remain
possible; startup checks establish readiness rather than a guarantee against
later failures. Stop shuts down the three containers. Use **Prepare services**
to prepare a new mission after stopping. Closing the host launcher also cleans
up its task-owned containers. Logs and metadata are in `recordings/dashboard`.
Use `--run-dir` for another output directory, `--duration 12` for a short flight,
or `--ready-timeout 600` for slower first-use compilation.

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
