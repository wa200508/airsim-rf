import struct

import numpy as np

from airsim_rf.ams.dis import LocalEarthFrame, entity_state_pdu


def test_dis_wire_and_ecef_truth_at_equator():
    frame = LocalEarthFrame(0, 0, 100)
    packet = entity_state_pdu(frame=frame, entity_id=(1, 1, 1), position_ned_m=[10, 20, -30],
        velocity_ned_m_s=[1, 2, -3], body_to_ned=np.eye(3), time_unix_ns=900_000_000_000,
        marking="Drone1")
    assert len(packet) == 144
    version, exercise, kind, family, timestamp, length, status, padding = struct.unpack(">BBBBIHBB", packet[:12])
    assert (version, exercise, kind, family, length, status, padding) == (7, 1, 1, 1, 144, 0, 0)
    assert timestamp & 1 == 1 and abs((timestamp >> 1)/2147483647*3600-900) < 1e-5
    assert struct.unpack_from(">HHH", packet, 12) == (1, 1, 1)
    np.testing.assert_allclose(struct.unpack_from(">fff", packet, 36), [3, 2, 1])
    np.testing.assert_allclose(struct.unpack_from(">ddd", packet, 48), [6378137+100+30, 20, 10])
    assert packet[88] == 2  # DRM_FPW.
    assert packet[128] == 1 and packet[129:135] == b"Drone1"
