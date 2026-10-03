"""DIS v7 EntityState publication for an AirSim world anchored in WGS-84."""
import socket
import struct
import warnings

import numpy as np
from scipy.spatial.transform import Rotation

class LocalEarthFrame:
    def __init__(self, latitude_deg, longitude_deg, altitude_hae_m):
        if not -90 <= latitude_deg <= 90 or not -180 <= longitude_deg <= 180:
            raise ValueError("Invalid WGS-84 origin")
        if not np.isfinite(altitude_hae_m):
            raise ValueError("Origin altitude must be finite ellipsoid height")
        lat, lon = np.radians([latitude_deg, longitude_deg])
        sl, cl, so, co = np.sin(lat), np.cos(lat), np.sin(lon), np.cos(lon)
        a, e2 = 6378137.0, 6.6943799901413165e-3
        n = a / np.sqrt(1-e2*sl*sl)
        self.origin = np.array([(n+altitude_hae_m)*cl*co, (n+altitude_hae_m)*cl*so,
                                (n*(1-e2)+altitude_hae_m)*sl])
        self.ned_to_ecef = np.array([[-sl*co, -so, -cl*co], [-sl*so, co, -cl*so], [cl, 0, -sl]])

    def position(self, position_ned_m):
        return self.origin + self.ned_to_ecef @ position_ned_m


def entity_state_pdu(*, frame, entity_id, position_ned_m, velocity_ned_m_s, body_to_ned,
                     time_unix_ns, marking, exercise_id=1, force_id=1, entity_type=(1, 2, 225, 0, 0, 0, 0)):
    """144-byte fixed EntityState PDU, ECEF state and constant-velocity DR (FPW)."""
    if len(entity_id) != 3 or any(isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 65535 for v in entity_id):
        raise ValueError("DIS entity_id must contain three nonzero u16 identifiers")
    if not 0 <= exercise_id <= 255 or force_id not in (0, 1, 2, 3):
        raise ValueError("Invalid DIS exercise or force ID")
    seconds_past_hour = (time_unix_ns % 3_600_000_000_000) / 1e9
    timestamp = (round(seconds_past_hour * (2147483647 / 3600)) << 1) | 1
    header = struct.pack(">BBBBIHBB", 7, exercise_id, 1, 1, timestamp, 144, 0, 0)
    position = frame.position(np.asarray(position_ned_m, dtype=float))
    velocity = frame.ned_to_ecef @ velocity_ned_m_s
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Gimbal lock detected")
        orientation = Rotation.from_matrix(frame.ned_to_ecef @ body_to_ned).as_euler("ZYX")
    type_bytes = struct.pack(">BBHBBBB", *entity_type)
    name = marking.encode("ascii", errors="ignore")[:11].ljust(11, b"\0")
    body = (struct.pack(">HHHBB", *entity_id, force_id, 0) + type_bytes + type_bytes
            + struct.pack(">fffdddfffI", *velocity, *position, *orientation, 0)
            + bytes([2]) + bytes(39)  # DRM_FPW: fixed orientation, world-frame velocity.
            + bytes([1]) + name + bytes(4))
    return header + body


class TruthPublisher:
    def __init__(self, origin, *, address="239.1.2.3", port=21100, interface=None,
                 exercise_id=1, epoch_unix_ns=0, start_sim_time_ns=0):
        self.frame = LocalEarthFrame(**origin)
        self.destination, self.exercise_id = (address, port), exercise_id
        self.epoch_unix_ns, self.start_sim_time_ns = epoch_unix_ns, start_sim_time_ns
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        if interface:
            self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface))

    def publish(self, sim_time_ns, entities):
        epoch = self.epoch_unix_ns + sim_time_ns - self.start_sim_time_ns
        for entity in entities:
            self.socket.sendto(entity_state_pdu(frame=self.frame, time_unix_ns=epoch,
                exercise_id=self.exercise_id, **entity), self.destination)

    def close(self):
        self.socket.close()
