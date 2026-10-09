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

    def snapshot(self):
        """Freeze radio geometry at a verified paused epoch and return its ns timestamp."""
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
        return int(epoch)

    def capture(self, *, num_samples=4096):
        return self.receiver.capture(self.snapshot(), num_samples=num_samples)

    def capture_elapsed(self, *, advance_ns, max_samples=2_000_000):
        """Render the actual physics interval from a paused start snapshot.

        Channels use the start pose and evolve by narrowband Doppler within the
        window. Physics tick overshoot is included, never discarded. The caller
        must supply waveform history/lookahead for the entire resulting interval.
        """
        from numbers import Integral
        if isinstance(advance_ns, bool) or not isinstance(advance_ns, Integral) or advance_ns <= 0:
            raise ValueError("advance_ns must be a positive integer")
        if isinstance(max_samples, bool) or not isinstance(max_samples, Integral) or max_samples <= 0:
            raise ValueError("max_samples must be a positive integer")
        rate = self.receiver.profile.sample_rate_hz
        if any(c.error_ppm != 0 for c in self.receiver.clocks.values()):
            raise ValueError("Elapsed live capture requires nominal sample clocks")
        if advance_ns * rate / 1e9 > max_samples:
            raise ValueError("Requested interval exceeds max_samples")
        start = self.snapshot()
        self.world.continue_until_sim_time(start + int(advance_ns), wait_until_complete=True)
        end = int(self.world.get_sim_time())
        if not self.world.is_paused() or end < start + advance_ns:
            raise RuntimeError("AirSim did not advance to the target and pause")
        samples = (end - start) * rate / 1e9
        count = round(samples)
        if count < 1 or abs(samples - count) > 1e-6:
            raise RuntimeError("Actual physics interval is not sample-aligned; choose a compatible sample rate/physics tick")
        if count > max_samples:
            raise RuntimeError("Physics overshoot exceeds max_samples; capture stopped before allocating I/Q")
        return self.receiver.capture(start, num_samples=count)
