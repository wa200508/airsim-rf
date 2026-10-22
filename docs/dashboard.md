# Local RF mission dashboard

The primary use case is an actual ProjectAirSim drone over shared terrain,
Sionna propagation and continuous ADC I/Q, streamed to a separate Docker MUSIC
RF Skill. A Python launcher serves the dashboard at `http://localhost:8765`.
The three process cards report actual supervised processes; the plots and data
rate come from the receiving skill, and the main image is a ProjectAirSim scene
camera. Camera or sensing failure is displayed separately from stream delivery.

## Prepare and launch

Use the qualified Linux/Docker/NVIDIA environment in [setup](setup.md), with the
pinned ProjectAirSim source and Blocks asset already prepared. The CPU base image
is `airsim-rf:priority2-local`; the P100 producer image is
`airsim-rf:p100-modern-gpu`. Their qualification and build commands are in setup.
Then, from the checkout:

```bash
python3 scripts/prepare_unreal_blocks.py
python3 scripts/launch_dashboard.py --build --pascal-compat --open
```

The host launcher uses Python's standard library; numerical work stays in the
containers. `--build` builds the simulator rendering and CPU skill images from
those local base images. The skill's locked Python dependencies need network
access during the image build. Click **Launch mission** to start the three
processes. Pause preserves the simulation clock and stream; Stop terminates
only containers created by this launcher. Closing the launcher also cleans up
its processes. Do not run another stepping owner against this dedicated world.
All HTTP/control ports are published to loopback. Defaults are dashboard 8765,
AirSim 8989/8990, coherent I/Q 8811, skill HTTP 8812 and SQUALL control 8813.
The RF deployment uses host networking to reach the local simulator and skill.

Default duration is 120 simulated seconds, about two 62.8-second orbits. Use
`--duration 12` for a bounded check. Runtime speed depends on rendering and RF
processing; no real-time claim is made. Logs, actual poses, camera frames,
geometry bundle and receiver metadata are stored in `recordings/dashboard`.
Use `--run-dir` for separate runs. The first run exports and places the same
terrain and ridge triangles in Unreal and RF.

## Scene and signal interpretation

The drone starts at RF `(250,0,160)` metres over ground around z=100 m. A Fast
Physics controller receives 25 m/s body-forward and −0.1 rad/s NED yaw-rate
commands: a large left-hand circle. Actual simulator pose and velocity readback,
rather than the ideal commanded circle, drive Sionna. The shared terrain spans
1.2 km; a 10 × 170 × 85 m ridge at north 150 m shadows part of the orbit without
intersecting the nominal flight path. The RF solver retains direct visibility
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
