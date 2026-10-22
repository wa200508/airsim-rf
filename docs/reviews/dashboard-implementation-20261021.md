# Primary localhost RF dashboard — implementation checkpoint

User-directed work is on `main`, with periodic pushes to origin/main. Baseline
checkpoint a1b16f7 contains priorities 1–3. Dashboard foundation 5e0e96f contains
the Python stdlib launcher, local HTTP UI, three-process supervision, shared
terrain/large left orbit scenario, actual AirSim/Sionna producer, CPU MUSIC
container and SQUALL-derived control-schema boundary. Image publication now
requires a version tag; ordinary main checkpoints do not publish containers.

Current qualification is in progress, not complete. The UI serves at localhost
8765. Preparing the shared scene exposed and corrected a simulator-binding
schema mismatch. Software Vulkan is available (Mesa llvmpipe); the current Blocks
binary exits before emitting a camera frame. Render image debugging is ongoing;
no substitute image or fabricated telemetry is supplied. The user requested a
real AirSim rendered 3D scene, not a schematic as the main display.

Main files: `src/airsim_rf/dashboard.py`, `dashboard_scenario.py`,
`dashboard_producer.py`, `dashboard_skill.py`, `dashboard_static/`,
`deploy/dashboard/`, `scripts/launch_dashboard.py`, `docs/dashboard.md`.
The stdlib host launcher is running in a retained process and uses Docker for
numerical work. `.deps/ProjectAirSim-runtime` and Blocks are the pinned existing
assets. The task-created render probe container is `airsim-rf-dashboard-sim`
(exited; retained for diagnostics). Do not touch unrelated comfyui,
gitlab-runner or immich containers. GPU was idle except 263 MiB baseline.

Local images: airsim-rf:dashboard-render (software Vulkan/X11 + Blocks mount),
airsim-rf:music-skill (CPU-only MUSIC), airsim-rf:p100-modern-gpu (actual Sionna
producer), airsim-rf:priority2-local (CPU preparation/tests).

Remaining: finish actual-render startup, qualify 12-second live flight through
three processes with camera/IQ/MUSIC/blocked-to-clear transitions; test
pause/resume/stop and explicit failure states; numerical continuity and transport
checks; browser visual QA at desktop/mobile; fix errors, save acceptance evidence,
update status docs, push final changes on main. Earlier auto-review rejected
broad staging of historical results and a potential duplicate simulator launch.
The safe alternatives are explicit reviewed source-file staging and restarting
only owned probe containers, with one Unreal process per container.
