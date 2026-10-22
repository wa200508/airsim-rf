# Local RF mission dashboard

The primary use case is an actual ProjectAirSim drone over shared terrain,
Sionna propagation and continuous ADC I/Q, streamed to a separate MUSIC RF Skill process. A Python launcher serves the dashboard at `http://localhost:8765`.
The three process cards report actual supervised processes; the plots and data
rate come from the receiving skill, and the main image is a ProjectAirSim scene
camera. Camera or sensing failure is displayed separately from stream delivery.

## Pull and run (no checkout or local image builds)

Install Docker Engine, a compatible NVIDIA host driver and the NVIDIA Container
Toolkit on Linux x86-64, then run:

```bash
docker pull ghcr.io/wa200508/airsim-rf:dashboard-gpu
docker run --rm --init --gpus all --shm-size=1g \
  -p 127.0.0.1:8765:8765 \
  -v airsim-rf-dashboard:/work/dashboard \
  ghcr.io/wa200508/airsim-rf:dashboard-gpu
```

Open **http://localhost:8765** and click **Launch mission**. The image includes
the checksum-pinned ProjectAirSim Blocks executable and client templates,
Sionna/CuPy CUDA libraries, OpenUSD, the MUSIC dependencies and dashboard assets.
It runs the simulator, RF producer and skill as three supervised processes in
one container. No source mount, Docker socket, `priority2-local` image, first-run
package installation or manual Blocks download is required. The GPU performs
RF propagation/rendering; the bundled Unreal camera uses software Vulkan/Xvfb,
which also supports compute-only cards such as the P100. Pascal compatibility
is enabled by default in this image.

Only the dashboard port is published. AirSim and skill ports remain internal.
The named volume retains run products under `/work/dashboard`; remove it only
when you want to delete those recordings. Pause preserves the simulation clock
and stream. Stop terminates the task-owned child process groups. Container
shutdown also stops them. `--init` reaps any orphaned simulator children.
Use `--duration 12` after the image name for a shorter mission.

The workflow publishes `dashboard-gpu` on successful `main` builds, with an
immutable `dashboard-gpu-sha-<full-commit>` tag. The optional `dashboard-skill`
and `dashboard-render` tags provide the same pinned runtime for the separate
container deployment below. Version tags also publish version-specific image
tags. CPU-only CI checks dependencies, bundled assets, scene preparation and HTTP
startup; it cannot qualify GPU physics/RF performance. A successful GPU mission
requires compatible hardware and is not implied by an idle dashboard health check.

## Optional checkout / separate-container deployment

For development, use the [setup](setup.md) prerequisites and prepare the Blocks
asset on the host, then run the standard-library launcher:

```bash
python3 scripts/prepare_unreal_blocks.py
python3 scripts/launch_dashboard.py --pascal-compat --open
```

The launcher pulls the published `dashboard-gpu`, `dashboard-render` and
`dashboard-skill` tags by default. It no longer assumes any locally built image.
`--build` explicitly rebuilds the optional skill/render wrappers using the
published base. `--cpu-image`, `--rf-image`, `--skill-image` and `--sim-image`
remain available for overriding images during development.

This deployment supervises three Docker containers. Defaults are dashboard
8765, AirSim 8989/8990, coherent I/Q 8811, skill HTTP 8812 and SQUALL control 8813.
The RF deployment uses host networking to reach the local simulator and skill.
The equivalent [three-service Compose file](../deploy/dashboard/compose.yaml)
is supplied after the launcher has generated the run directory. Do not run
Compose and the launcher against the same ports simultaneously.

Default duration is 120 simulated seconds, about two 62.8-second orbits. Use
`--duration 12` for a bounded check. Runtime speed depends on rendering and RF
processing; no real-time claim is made. Logs, actual poses, camera frames,
geometry bundle and receiver metadata are stored in `/work/dashboard` in the pull-and-run image, or `recordings/dashboard`
in a checkout deployment.
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