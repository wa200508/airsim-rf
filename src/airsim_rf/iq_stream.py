"""Legacy simulation-capture adapter for the receiver-facing sample stream.

Version-1 callers retain their public names and wire representation. New source
adapters and skills use sample_stream.SampleBlock/SampleStreamWriter directly.
"""
from dataclasses import dataclass
import numpy as np
from . import sample_stream as _stream
from .sample_stream import MAX_SAMPLES, MAX_HEADER, PREFIX, _exact


@dataclass(frozen=True)
class StreamIQBlock:
    receiver: str
    samples: np.ndarray
    sample_start: int
    sim_time_ns: int
    sample_rate_hz: float
    carrier_hz: float
    clipped_component_fraction: float


class IQStreamWriter(_stream.SampleStreamWriter):
    def __init__(self,sock,*,carrier_hz):
        super().__init__(sock,carrier_hz=carrier_hz,protocol_version=1)

    def send_capture(self,receiver,capture):
        return self.send_samples(receiver,capture.adc_iq_volts,timestamp_ns=capture.sim_time_ns,
            sample_rate_hz=capture.actual_sample_rate_hz,clipped_component_fraction=capture.clipped_component_fraction)


def iter_stream(sock,*,validate_end=None):
    for b in _stream.iter_stream(sock,validate_end=validate_end):
        yield StreamIQBlock(b.receiver,b.samples,b.sample_start,b.timestamp_ns,b.sample_rate_hz,b.carrier_hz,b.clipped_component_fraction)


def _send(sock,header,payload=b''):
    return _stream._send(sock,{'version':1,**header},payload)


def _receive(sock):
    header,payload=_stream._receive(sock)
    if header['type']=='iq' and header['version']==1:header['sim_time_ns']=header.pop('timestamp_ns')
    return header,payload
