# Paused chase-camera regression — 2026-10-22

The original `set_camera_pose('Chase', pose)` call returned `False` after
1.386 seconds in the actual packaged Blocks 1.0.1 simulator with the steppable
world paused. This reproduces the failure on the first dashboard mission step.
The SDK defaults `wait_for_pose_update=True`. The server accepts the desired
pose, but returns failure if Unreal has not applied it before the renderer wait
expires. Our stepping owner cannot advance the world until the RPC returns.

The fix queues the pose with `wait_for_pose_update=False` before advancing the
simulation. Preparation exercises the same call before the settling step and
requires a camera frame before READY. Explicit `--no-render` mode skips camera
operations. RF, geometry, waveform and stepping intervals are unchanged.

[Recorded results](camera-check.json) from the reusable
[live check](../../../scripts/qualify_dashboard_camera.py):

- All ten camera requests accepted while paused; each took 0.8–7.2 ms here.
- World advanced 1.2 simulated seconds.
- An actual 960×540×3 camera image arrived.
- Its horizontal camera position matched the requested chase view within
  0.000014 m, distinguishing the applied view from the original fixed camera.
- 28 focused dashboard, container, launcher and HTTP tests passed.

This ran with software Vulkan/Xvfb and the pinned ProjectAirSim SDK inside the
local dashboard runtime image, using the working-tree source. It is a camera
integration check, not a CUDA/RF mission, rootless GPU qualification, or an RF
performance measurement. CI runs the same live camera check before publication.

Source SHA-256 at qualification:

```text
36c4d675c9854d40d39a8b6f855af384fcf008aa772c0da76862374e54656227  src/airsim_rf/dashboard_view.py
a0d1e0178f90d4c5146c0aabddb316806410f0581f766957233d295e9f0ab228  src/airsim_rf/dashboard_producer.py
176a8c7dfa12042a2095133b7836e6e5e5fdb9b0b72279086342f6d0f632ba20  scripts/qualify_dashboard_camera.py
```

Upstream implementation at the pinned SDK commit:

- [SDK `Robot.set_camera_pose`, default renderer wait](https://github.com/iamaisim/ProjectAirSim/blob/cfb865f29f255b15ef28ec8fdcfaa01a6b66497f/client/python/projectairsim/src/projectairsim/robot.py).
- [Core camera `SetPose`, pending pose and bounded wait](https://github.com/iamaisim/ProjectAirSim/blob/cfb865f29f255b15ef28ec8fdcfaa01a6b66497f/core_sim/src/sensors/camera.cpp#L776).
- [Unreal camera applies the pending pose during `TickComponent`](https://github.com/iamaisim/ProjectAirSim/blob/cfb865f29f255b15ef28ec8fdcfaa01a6b66497f/unreal/Blocks/Plugins/ProjectAirSim/Source/ProjectAirSim/Private/Sensors/UnrealCamera.cpp#L695).
