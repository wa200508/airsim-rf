"""Versioned, timestamped captures on the reliable RF coordination channel."""
from dataclasses import dataclass
from io import BytesIO
import json
import re
import uuid

import numpy as np

from airsim_rf.radar import PointTarget

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


def integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def vector(value, name):
    result = np.asarray(value, dtype=float)
    if result.shape != (3,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite 3-vector")
    return tuple(float(x) for x in result)


def receiver_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value):
        raise ValueError("receiver_id must contain 1..64 ASCII letters, digits, dots, dashes or underscores")
    return value


def run_uuid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("run_id must be a canonical UUID")
    return value


@dataclass(frozen=True)
class CaptureRequest:
    run_id: str
    receiver_id: str
    sequence: int
    sim_time_ns: int
    position_m: tuple
    velocity_m_s: tuple
    orientation_rad: tuple
    targets: tuple

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Capture request must be a JSON object")
        if integer(value.get("protocol_version"), "protocol_version") != PROTOCOL_VERSION:
            raise ValueError("Unsupported protocol_version")
        targets = value["targets"]
        if not isinstance(targets, list) or len(targets) > 2048:
            raise ValueError("targets must be a list of at most 2048 point targets")
        names = [t["name"] for t in targets]
        if any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(names):
            raise ValueError("Target names must be nonempty and unique")
        return cls(run_uuid(value["run_id"]), receiver_name(value["receiver_id"]),
                   integer(value["sequence"], "sequence"), integer(value["sim_time_ns"], "sim_time_ns"),
                   vector(value["position_m"], "position_m"), vector(value["velocity_m_s"], "velocity_m_s"),
                   vector(value["orientation_rad"], "orientation_rad"),
                   tuple(PointTarget(t["name"], vector(t["position_m"], "target position"),
                                     float(t["rcs_m2"]), vector(t.get("velocity_m_s", [0, 0, 0]), "target velocity"))
                         for t in targets))

    def to_dict(self):
        return {"protocol_version": PROTOCOL_VERSION, "run_id": self.run_id,
                "receiver_id": self.receiver_id, "sequence": self.sequence, "sim_time_ns": self.sim_time_ns,
                "position_m": self.position_m, "velocity_m_s": self.velocity_m_s,
                "orientation_rad": self.orientation_rad,
                "targets": [{"name": t.name, "position_m": t.position_m, "rcs_m2": t.rcs_m2,
                             "velocity_m_s": t.velocity_m_s} for t in self.targets]}

    def canonical_bytes(self):
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def encode_result(capture, metadata):
    buffer = BytesIO()
    np.savez_compressed(buffer, metadata_json=json.dumps(metadata, allow_nan=False),
                        if_volts=capture.if_volts, adc_iq_volts=capture.adc_iq_volts,
                        adc_codes=capture.adc_codes, target_names=np.asarray(capture.target_names, dtype=str),
                        target_ranges_m=capture.target_ranges_m, target_doppler_hz=capture.target_doppler_hz,
                        target_beat_hz=capture.target_beat_hz, target_delays_s=capture.target_delays_s)
    return buffer.getvalue()


@dataclass(frozen=True)
class CaptureResult:
    metadata: dict
    arrays: dict
    payload: bytes

    @classmethod
    def decode(cls, payload, expected):
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ValueError("RF response exceeds size limit")
        with np.load(BytesIO(payload), allow_pickle=False) as recording:
            metadata = json.loads(str(recording["metadata_json"]))
            arrays = {key: recording[key].copy() for key in recording.files if key != "metadata_json"}
        for key in ("protocol_version", "run_id", "receiver_id", "sequence", "sim_time_ns"):
            if metadata.get(key) != expected.to_dict()[key]:
                raise ValueError(f"RF response {key} does not match requested capture")
        count = metadata["profile"]["num_samples"]
        if arrays["adc_iq_volts"].shape != (count,) or arrays["adc_codes"].shape != (count, 2):
            raise ValueError("RF response sample shape does not match profile")
        return cls(metadata, arrays, payload)


def sc16_payload(capture):
    """MEL wire format: signed little-endian I0,Q0,...; fixed physical scale."""
    volts_per_count = capture.profile.adc_full_scale_v / (2 * 32767)
    samples = np.column_stack((capture.adc_iq_volts.real, capture.adc_iq_volts.imag))
    return np.rint(np.clip(samples / volts_per_count, -32768, 32767)).astype("<i2").tobytes(), volts_per_count
