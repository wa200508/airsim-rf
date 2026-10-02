"""Capture one drone-mounted FMCW ramp or LFM pulse using a live AirSim pose."""
import argparse
from pathlib import Path

from projectairsim import Drone, ProjectAirSimClient, World

from airsim_rf.bridge import AirSimRadarBridge, NED_TO_RF
from airsim_rf.radar import PointTarget, PointTargetRadar, RadarConfig, range_compress
from airsim_rf.fmcw import FMCWRadar, range_fft


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--scene", required=True)
    parser.add_argument("--sim-config", required=True)
    parser.add_argument("--robot", default="Drone1")
    parser.add_argument("--model", choices=["distance2gol", "pulsed"], default="distance2gol")
    parser.add_argument("--target-ned", nargs=4, type=float, action="append", metavar=("N", "E", "D", "RCS"),
                        required=True, help="Repeat for each point target: N/E/D meters and RCS square meters")
    parser.add_argument("--mount-body", nargs=3, type=float, default=[0, 0, 0])
    parser.add_argument("--rf-scene", help="Aligned Mitsuba scene for line-of-sight blockage")
    parser.add_argument("--output", type=Path, default=Path("airsim_lfm_radar.npz"))
    args = parser.parse_args()
    targets = [PointTarget(f"target_{i}", tuple(NED_TO_RF @ item[:3]), rcs_m2=item[3])
               for i, item in enumerate(args.target_ned)]
    radar = (FMCWRadar(rf_scene=args.rf_scene) if args.model == "distance2gol"
             else PointTargetRadar(RadarConfig(), rf_scene=args.rf_scene))
    client = ProjectAirSimClient(address=args.address)
    try:
        client.connect()
        world = World(client, args.scene, sim_config_path=args.sim_config)
        robot = Drone(client, world, args.robot)
        world.pause()
        bridge = AirSimRadarBridge(world, robot, radar, offset_body_m=args.mount_body)
        capture = bridge.capture(targets)
        capture.save(args.output)
        if args.model == "distance2gol":
            ranges, profile = range_fft(capture.adc_iq_volts, radar.profile)
            epoch = capture.sim_time_ns
        else:
            ranges, profile = range_compress(capture.block.iq_volts, radar.config)
            epoch = capture.block.sim_time_ns
        print(f"Saved raw I/Q at sim time {epoch} ns to {args.output}")
        if abs(profile).max() > 0:
            print(f"Strongest processed return at {ranges[abs(profile).argmax()]:.2f} m")
        else:
            print("No received target echoes in this window")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
