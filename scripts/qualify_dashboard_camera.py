"""Live paused-world camera regression using packaged Unreal software rendering.

Exercises the actual SDK/renderer without CUDA, RF generation or a full mission.
Run inside the dashboard GPU image; no NVIDIA device is needed for this check.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


async def check_camera(output):
    from projectairsim import ProjectAirSimClient, World, Drone
    from projectairsim.utils import unpack_image
    from airsim_rf.bridge import mount_kinematics, normalize_kinematics
    from airsim_rf.dashboard_view import queue_chase_camera_pose
    from dashboard_scene_probes import add_probes,spawn_environment,compare_probes

    probes=add_probes(output)
    arrays = json.loads((output / 'arrays.json').read_text())
    receivers = [site['center_rf_m'] for site in arrays['sites']]
    client = ProjectAirSimClient()
    client.connect()
    try:
        world = World(client, 'scene.jsonc', sim_config_path=str(output / 'sim_config'))
        world.pause()
        alignment=spawn_environment(output,world)
        drone = Drone(client, world, 'OrbitDrone')
        frames = []
        probe_messages={p['name']:[] for p in probes};probe_drones={}
        for probe in probes:
            name=probe['name'];probe_drones[name]=Drone(client,world,name)
            client.subscribe(probe_drones[name].sensors['lidar']['lidar'],lambda _,message,n=name:probe_messages[n].append(message))
        client.subscribe(drone.sensors['Chase']['scene_camera'],
                         lambda _, message: frames.append(message))
        timings = []
        origin = int(world.get_sim_time())
        # Same paused queue -> render/physics step order as the RF producer.
        for _ in range(10):
            kinematics = normalize_kinematics(drone.get_ground_truth_kinematics())
            position, _, _ = mount_kinematics(kinematics)
            started = time.monotonic()
            eye, _ = queue_chase_camera_pose(drone, position, receivers, kinematics)
            timings.append(time.monotonic() - started)
            epoch = int(world.get_sim_time())
            world.continue_until_sim_time(epoch + 120_000_000, wait_until_complete=True)
            await asyncio.sleep(.2)
        deadline = time.monotonic() + 30
        while not frames and time.monotonic() < deadline:
            await asyncio.sleep(.1)
        if not frames:
            raise RuntimeError('No actual camera frame after queued poses and ten simulator steps')
        frame = frames[-1]
        image = unpack_image(frame)
        # The configured fixed camera is roughly 140 m away horizontally from
        # the requested inward view. Verify rendering applied the requested pose,
        # rather than accepting an old frame from the original fixed camera.
        horizontal_error = float(np.linalg.norm(np.array([frame['pos_x'], frame['pos_y']]) - eye[:2]))
        elapsed = (int(world.get_sim_time()) - origin) * 1e-9
        checks = {
            'ten_paused_camera_requests_accepted': len(timings) == 10,
            'simulation_advanced_1_2_seconds': abs(elapsed - 1.2) < .01,
            'real_960_by_540_image_received': image.shape == (540, 960, 3),
            'requested_camera_position_rendered': horizontal_error < 3,
        }
        alignment.update(compare_probes(output,probes,probe_messages,probe_drones))
        checks['unreal_collision_and_sionna_dem_match']=True
        report = {'status': 'passed' if all(checks.values()) else 'failed', 'checks': checks,
                  'metrics': {'camera_frames': len(frames), 'sim_elapsed_s': elapsed,
                              'pose_request_wall_s': timings,
                              'horizontal_camera_position_error_m': horizontal_error},
                  'scene_alignment':alignment,
                  'scope': 'Actual Unreal/software Vulkan, CPU LiDAR terrain probes and Sionna mesh; '
                           'no CUDA, RF generation or full-mission qualification'}
        (output / 'camera-check.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2), flush=True)
        if not all(checks.values()):
            raise RuntimeError('Live camera checks failed')
    finally:
        client.disconnect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('/work/camera-check'))
    parser.add_argument('--blocks-dir', type=Path, default=Path('/opt/blocks'))
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    from airsim_rf.dashboard_scenario import prepare
    prepare(output, Path('/opt/airsim-rf/.deps/ProjectAirSim'))
    # The SDK opens projectairsim_client.log relative to its current directory.
    os.chdir(output)
    env = dict(os.environ, RF_BLOCKS_DIR=str(args.blocks_dir.resolve()))
    with (output / 'render.log').open('w') as log:
        renderer = subprocess.Popen([sys.executable, str(ROOT / 'deploy/dashboard/render-entrypoint.py')],
                                    env=env, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        try:
            deadline = time.monotonic() + 120
            while True:
                if renderer.poll() is not None:
                    raise RuntimeError('Renderer exited: ' + (output / 'render.log').read_text()[-4000:])
                try:
                    with socket.create_connection(('127.0.0.1', 8989), timeout=.5):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        raise RuntimeError('Simulator startup timed out; see ' + str(output / 'render.log'))
                    time.sleep(.25)
            asyncio.run(check_camera(output))
        finally:
            # Includes the Xvfb child created by the renderer entrypoint.
            try:
                os.killpg(renderer.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                renderer.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(renderer.pid, signal.SIGKILL)
                renderer.wait(timeout=5)


if __name__ == '__main__':
    main()
