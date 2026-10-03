"""AirSim owns physics time; concurrent RF workers finish before further stepping."""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import time
import warnings

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from airsim_rf.bridge import NED_TO_RF, mount_kinematics, vector3
from airsim_rf.radar import PointTarget
from .client import CaptureBarrier, WorkerClient


@dataclass
class Snapshot:
    time_ns: int
    poses: dict
    targets: tuple
    entities: tuple = ()


def interpolate(previous, current, epoch):
    """Linear position/velocity and shortest-arc rotation between physics truth."""
    if not previous.time_ns <= epoch <= current.time_ns:
        raise ValueError("RF epoch is outside the physics truth interval")
    alpha = 0 if current.time_ns == previous.time_ns else (epoch-previous.time_ns)/(current.time_ns-previous.time_ns)
    poses = {}
    for name, (p, v, e) in previous.poses.items():
        q, w, f = current.poses[name]
        rotations = Rotation.from_euler("ZYX", np.asarray([e, f]))
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Gimbal lock detected")
            orientation = Slerp([0, 1], rotations)(alpha).as_euler("ZYX")
        poses[name] = (np.asarray(p)*(1-alpha)+np.asarray(q)*alpha,
                       np.asarray(v)*(1-alpha)+np.asarray(w)*alpha, orientation)
    new_targets = {t.name: t for t in current.targets}
    if set(new_targets) != {t.name for t in previous.targets}:
        raise ValueError("Targets changed within the truth interval")
    targets = tuple(PointTarget(t.name,
        tuple(np.asarray(t.position_m)*(1-alpha)+np.asarray(new_targets[t.name].position_m)*alpha),
        t.rcs_m2,
        tuple(np.asarray(t.velocity_m_s)*(1-alpha)+np.asarray(new_targets[t.name].velocity_m_s)*alpha))
        for t in previous.targets)
    return poses, targets


def run_simulation(source, barrier, *, duration_ns, physics_hz=120, output=None,
                   publisher=None, pace=False):
    if not isinstance(physics_hz, int) or isinstance(physics_hz, bool) or not 1 <= physics_hz <= 1_000_000:
        raise ValueError("physics_hz must be an integer in 1..1000000")
    if duration_ns < 0:
        raise ValueError("duration_ns must be nonnegative")
    pri_ns = round(barrier.profile["pri_s"]*1e9)
    if pri_ns <= 0 or abs(pri_ns/1e9-barrier.profile["pri_s"]) > 1e-15:
        raise ValueError("RF PRI must be representable in integer nanoseconds")
    previous = source.snapshot()
    start, end = previous.time_ns, previous.time_ns+duration_ns
    wall_start = time.monotonic()
    records = []
    directory = None if output is None else Path(output)/barrier.run_id
    if directory:
        directory.mkdir(parents=True, exist_ok=False)
        for client in barrier.clients:
            (directory/client.receiver_id).mkdir()

    def capture(epoch, left, right):
        poses, targets = interpolate(left, right, epoch)
        wall = time.monotonic()
        results = barrier.capture(epoch, poses, targets)
        record = {"sequence": barrier.sequence-1, "sim_time_ns": epoch,
                  "truth_interval_ns": [left.time_ns, right.time_ns],
                  "barrier_ms": (time.monotonic()-wall)*1000,
                  "compute_ms": {name: result.metadata["compute_ms"] for name, result in results.items()}}
        records.append(record)
        if directory:
            for name, result in results.items():
                (directory/name/f"{record['sequence']:08d}.npz").write_bytes(result.payload)
            # Append only fully acknowledged epochs; failed partial updates have no manifest entry.
            with (directory/"epochs.jsonl").open("a") as stream:
                stream.write(json.dumps(record)+"\n")
        if pace:
            delay = (epoch-start)/1e9-(time.monotonic()-wall_start)
            if delay > 0:
                time.sleep(min(delay, pri_ns/1e9))

    capture(start, previous, previous)
    if publisher:
        publisher.publish(previous.time_ns, previous.entities)
    next_rf, step, physics_steps = start+pri_ns, 1, 0
    while previous.time_ns < end:
        requested = min(end, start+(step*1_000_000_000)//physics_hz)
        step += 1
        if requested <= previous.time_ns:
            continue  # AirSim can pause on a physics tick after the requested epoch.
        source.advance(requested)
        current = source.snapshot()
        if current.time_ns < requested or current.time_ns <= previous.time_ns:
            raise RuntimeError("Physics did not advance to a valid paused truth epoch")
        physics_steps += 1
        while next_rf <= min(current.time_ns, end):
            capture(next_rf, previous, current)
            next_rf += pri_ns
        if publisher:
            publisher.publish(current.time_ns, current.entities)
        previous = current
    elapsed = time.monotonic()-wall_start
    barriers = np.array([r["barrier_ms"] for r in records])
    summary = {"run_id": barrier.run_id, "receivers": len(barrier.clients),
               "physics_hz_requested": physics_hz, "physics_steps": physics_steps,
               "rf_chirps_per_receiver": len(records), "rf_pri_ns": pri_ns,
               "simulated_s": duration_ns/1e9, "wall_s": elapsed,
               "barrier_ms_p50": float(np.percentile(barriers, 50)),
               "barrier_ms_p95": float(np.percentile(barriers, 95)),
               "barrier_ms_max": float(barriers.max()),
               "physics_step_budget_ms": 1000/physics_hz,
               "rf_epoch_budget_ms": pri_ns/1e6,
               "recordings": None if directory is None else str(directory)}
    if directory:
        (directory/"run.json").write_text(json.dumps({**summary, "profile": barrier.profile}, indent=2)+"\n")
    return summary


class DemoSource:
    """Analytic moving-drone truth for testing transport without an AirSim server."""
    def __init__(self, receivers, targets):
        self.receivers, self.target_config, self.time_ns = receivers, targets, 0

    def advance(self, requested):
        self.time_ns = requested

    def snapshot(self):
        seconds = self.time_ns/1e9
        poses = {}
        for index, receiver in enumerate(self.receivers):
            poses[receiver["receiver_id"]] = (np.array([seconds, index*0.5, 0]), np.array([1, 0, 0]), np.zeros(3))
        targets = tuple(PointTarget(t["name"],
            tuple(NED_TO_RF @ (np.asarray(t["position_ned_m"])+seconds*np.asarray(t.get("velocity_ned_m_s", [0, 0, 0])))),
            t["rcs_m2"], tuple(NED_TO_RF @ t.get("velocity_ned_m_s", [0, 0, 0]))) for t in self.target_config)
        return Snapshot(self.time_ns, poses, targets)


class AirSimSource:
    def __init__(self, world, robots, receivers, targets):
        self.world, self.robots, self.receivers, self.target_config = world, robots, receivers, targets
        world.pause()
        self.start_ns = world.get_sim_time()

    def advance(self, requested):
        self.world.continue_until_sim_time(requested, wait_until_complete=True)

    def snapshot(self):
        if not self.world.is_paused():
            raise RuntimeError("AirSim must be paused for distributed truth collection")
        epoch = self.world.get_sim_time()
        states = {name: robot.get_ground_truth_kinematics()["kinematics"] for name, robot in self.robots.items()}
        poses = {r["receiver_id"]: mount_kinematics(states[r["robot"]], r.get("mount_body_m", [0, 0, 0]))
                 for r in self.receivers}
        targets = []
        for target in self.target_config:
            if "robot" in target:
                p, v, _ = mount_kinematics(states[target["robot"]], target.get("mount_body_m", [0, 0, 0]))
            else:
                v_ned = np.asarray(target.get("velocity_ned_m_s", [0, 0, 0]))
                p = NED_TO_RF @ (np.asarray(target["position_ned_m"])+v_ned*((epoch-self.start_ns)/1e9))
                v = NED_TO_RF @ v_ned
            targets.append(PointTarget(target["name"], tuple(p), target["rcs_m2"], tuple(v)))
        entities = []
        # One body truth entity per robot, independent of receiver antenna mount.
        definitions = {r["robot"]: r for r in self.receivers if "dis_entity_id" in r}
        definitions.update({t["robot"]: t for t in self.target_config if "robot" in t and "dis_entity_id" in t})
        if len({tuple(d["dis_entity_id"]) for d in definitions.values()}) != len(definitions):
            raise ValueError("DIS entity IDs must be unique across robots")
        for name, definition in definitions.items():
            state = states[name]
            q = state["pose"]["orientation"]
            entities.append({"entity_id": definition["dis_entity_id"], "marking": name,
                "position_ned_m": vector3(state["pose"]["position"]),
                "velocity_ned_m_s": vector3(state["twist"]["linear"]),
                "body_to_ned": Rotation.from_quat([q[k] for k in ("x", "y", "z", "w")]).as_matrix()})
        if not self.world.is_paused() or self.world.get_sim_time() != epoch:
            raise RuntimeError("AirSim advanced during distributed truth collection")
        return Snapshot(epoch, poses, tuple(targets), tuple(entities))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--demo", action="store_true", help="Use analytic truth; no live AirSim server")
    parser.add_argument("--duration-s", type=float, default=1)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pace", action="store_true", help="Best-effort pacing; overruns slow simulation")
    args = parser.parse_args()
    if not np.isfinite(args.duration_s) or args.duration_s < 0:
        parser.error("duration-s must be finite and nonnegative")
    config = json.loads(args.config.read_text())
    receivers, targets = config["receivers"], config.get("targets", [])
    clients = [WorkerClient(r["url"], r["receiver_id"]) for r in receivers]
    connection, publisher, world = None, None, None
    try:
        with CaptureBarrier(clients, timeout_s=config.get("timeout_s", 30),
                            scene_id=config.get("scene_id", "empty-free-space-v1")) as barrier:
            if args.demo:
                source = DemoSource(receivers, targets)
            else:
                from projectairsim import Drone, ProjectAirSimClient, World
                airsim = config["airsim"]
                connection = ProjectAirSimClient(address=airsim["address"])
                connection.connect()
                world = World(connection, airsim["scene"], sim_config_path=airsim["sim_config"])
                names = {r["robot"] for r in receivers} | {t["robot"] for t in targets if "robot" in t}
                source = AirSimSource(world, {n: Drone(connection, world, n) for n in names}, receivers, targets)
                if "dis" in config:
                    from airsim_rf.ams.dis import TruthPublisher
                    publisher = TruthPublisher(**config["dis"], start_sim_time_ns=source.start_ns)
            print(json.dumps(run_simulation(source, barrier, duration_ns=round(args.duration_s*1e9),
                physics_hz=config.get("physics_hz", 120), output=args.output, publisher=publisher, pace=args.pace), indent=2))
    finally:
        if world is not None:
            world.pause()  # Completion and failures both leave physics paused.
        if publisher:
            publisher.close()
        if connection:
            connection.disconnect()


if __name__ == "__main__":
    main()
