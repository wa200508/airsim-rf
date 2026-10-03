"""A paused AirSim snapshot feeding every device in a one-way SDR network."""
from .bridge import mount_kinematics


class AirSimSDRBridge:
    def __init__(self, world, robots, receiver, *, mounts_body_m=None):
        """Map scene radio names to ProjectAirSim robot handles and body offsets."""
        self.world, self.receiver = world, receiver
        self.robots = dict(robots)
        self.devices = dict(receiver.scene.transmitters) | dict(receiver.scene.receivers)
        if set(self.robots) != set(self.devices):
            raise ValueError("Map every RF transmitter and receiver to an AirSim robot")
        mounts = {} if mounts_body_m is None else dict(mounts_body_m)
        if set(mounts)-set(self.devices):
            raise ValueError("Unknown radio mount")
        self.mounts = {name: mounts.get(name, (0., 0., 0.)) for name in self.devices}

    def capture(self, *, num_samples=4096):
        if not self.world.is_paused():
            raise RuntimeError("Pause AirSim before collecting the network snapshot")
        epoch = self.world.get_sim_time()
        poses = {}
        for name, robot in self.robots.items():
            data = robot.get_ground_truth_kinematics()
            poses[name] = mount_kinematics(data['kinematics'], self.mounts[name])
        if not self.world.is_paused() or self.world.get_sim_time() != epoch:
            raise RuntimeError("AirSim advanced while collecting the network snapshot")
        for name, (position, velocity, orientation) in poses.items():
            self.devices[name].position = position.tolist()
            self.devices[name].velocity = velocity.tolist()
            self.devices[name].orientation = orientation.tolist()
        return self.receiver.capture(int(epoch), num_samples=num_samples)
