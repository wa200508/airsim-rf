"""Attach a Sionna receiver to ProjectAirSim ground-truth kinematics."""
import warnings

import numpy as np
from scipy.spatial.transform import Rotation

from .receiver import RFReceiver, Waveform

# Explicit right-handed scene convention: x north, y west, z up, meters.
NED_TO_RF = np.diag([1.0, -1.0, -1.0])


def vector3(value):
    return np.array([value[key] for key in ("x", "y", "z")], dtype=float)


def mount_kinematics(kinematics, offset_body_m=(0, 0, 0)):
    """Convert AirSim pose/twist including omega cross lever-arm velocity."""
    pose, twist = kinematics["pose"], kinematics["twist"]
    q = pose["orientation"]
    body_to_ned = Rotation.from_quat([q[k] for k in ("x", "y", "z", "w")]).as_matrix()
    lever = body_to_ned @ np.asarray(offset_body_m, dtype=float)
    position = NED_TO_RF @ (vector3(pose["position"]) + lever)
    # Fast Physics angular kinematics are body-frame; linear velocity is NED.
    omega_ned = body_to_ned @ vector3(twist["angular"])
    velocity = NED_TO_RF @ (vector3(twist["linear"]) + np.cross(omega_ned, lever))
    rotation = NED_TO_RF @ body_to_ned @ NED_TO_RF.T
    # Sionna uses Rz(alpha) Ry(beta) Rx(gamma).
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Gimbal lock detected")
        orientation = Rotation.from_matrix(rotation).as_euler("ZYX")
    return position, velocity, orientation


def snapshot_mount(world, robot, offset_body_m):
    if not world.is_paused():
        raise RuntimeError("Pause AirSim before capture so pose and timestamp agree")
    time_ns = world.get_sim_time()
    message = robot.get_ground_truth_kinematics()
    mount = mount_kinematics(message["kinematics"], offset_body_m)
    if not world.is_paused() or world.get_sim_time() != time_ns:
        raise RuntimeError("Simulation advanced during RF snapshot")
    return time_ns, mount


class AirSimRFBridge:
    """Pull I/Q while the simulation is paused; caller controls stepping.

    Propagation geometry is frozen over each short block. Velocity drives local
    Doppler. Recompute at each new sim epoch; never add absolute-time Doppler
    again, since geometry already supplies carrier phase at that epoch.
    """

    def __init__(self, world, robot, receiver: RFReceiver, rx_device,
                 offset_body_m=(0, 0, 0)):
        self.world = world
        self.robot = robot
        self.receiver = receiver
        self.rx_device = rx_device
        self.offset_body_m = offset_body_m

    def capture(self, waveform: Waveform):
        time_ns, (position, velocity, orientation) = snapshot_mount(self.world, self.robot, self.offset_body_m)
        self.rx_device.position = position.tolist()
        self.rx_device.velocity = velocity.tolist()
        self.rx_device.orientation = orientation.tolist()
        return self.receiver.capture(waveform, time_ns)


class AirSimRadarBridge:
    """One LFM pulse or FMCW ramp using the current drone antenna state."""

    def __init__(self, world, robot, radar, offset_body_m=(0, 0, 0)):
        self.world, self.robot, self.radar = world, robot, radar
        self.offset_body_m = offset_body_m

    def capture(self, targets):
        time_ns, (position, velocity, orientation) = snapshot_mount(self.world, self.robot, self.offset_body_m)
        return self.radar.capture(targets, position_m=position, velocity_m_s=velocity,
                                  orientation_rad=orientation, sim_time_ns=time_ns)
