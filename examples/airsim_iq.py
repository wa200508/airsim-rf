"""Capture one block from an AirSim vehicle in a matching open RF scene."""
import argparse
from pathlib import Path

import numpy as np
from projectairsim import Drone, ProjectAirSimClient, World
from sionna.rt import PlanarArray, Receiver, Transmitter, load_scene

from airsim_rf import ReceiverConfig, RFReceiver
from airsim_rf.bridge import AirSimRFBridge, NED_TO_RF


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--scene", required=True, help="AirSim scene JSONC filename")
    parser.add_argument("--sim-config", required=True, help="Directory holding scene and robot configs")
    parser.add_argument("--robot", default="Drone1")
    parser.add_argument("--tx-ned", nargs=3, type=float, default=[100, 0, -10])
    parser.add_argument("--rf-scene", help="Optional matching Mitsuba XML in meters, x north/y west/z up")
    parser.add_argument("--output", type=Path, default=Path("airsim_iq.npz"))
    args = parser.parse_args()
    client = ProjectAirSimClient(address=args.address)
    try:
        client.connect()
        world = World(client, args.scene, sim_config_path=args.sim_config)
        robot = Drone(client, world, args.robot)
        world.pause()
        scene = load_scene(args.rf_scene)
        scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
        scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
        scene.add(Transmitter("tx", position=(NED_TO_RF @ args.tx_ned).tolist()))
        rx = Receiver("rx", position=[0, 0, 0])
        scene.add(rx)
        receiver = RFReceiver(scene, ReceiverConfig(), max_depth=1 if args.rf_scene else 0)
        bridge = AirSimRFBridge(world, robot, receiver, rx)
        block = bridge.capture(lambda t: np.exp(2j * np.pi * 10000 * t))
        block.save(args.output)
        print(f"Saved {block.iq_volts.size} samples at sim time {block.sim_time_ns} ns to {args.output}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
