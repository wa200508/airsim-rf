"""Version-1 framed TCP sample transport; synchronous, bounded and lossless.

One producer and consumer per connection; receiver streams are multiplexed by ID.
A socket timeout or protocol failure aborts rather than dropping/resuming samples.
"""
from dataclasses import dataclass
import json
import math
import re
import socket
import struct
import numpy as np

MAX_SAMPLES=2_000_000
MAX_HEADER=16_384
PREFIX=struct.Struct('!II')


def _exact(sock,count):
    data=bytearray(count);view=memoryview(data);offset=0
    while offset<count:
        n=sock.recv_into(view[offset:])
        if not n:raise EOFError('I/Q connection closed before explicit completion')
        offset+=n
    return data


def _send(sock,header,payload=b''):
    encoded=json.dumps({'version':1,**header},allow_nan=False,separators=(',',':')).encode()
    if len(encoded)>MAX_HEADER or len(payload)>8*MAX_SAMPLES:raise ValueError('I/Q frame exceeds transport limit')
    sock.sendall(PREFIX.pack(len(encoded),len(payload)))
    sock.sendall(encoded)
    if payload:sock.sendall(payload)


def _receive(sock):
    header_bytes,payload_bytes=PREFIX.unpack(_exact(sock,PREFIX.size))
    if not 0<header_bytes<=MAX_HEADER or payload_bytes>8*MAX_SAMPLES:
        raise ValueError('Invalid I/Q frame lengths')
    header=json.loads(_exact(sock,header_bytes))
    if not isinstance(header,dict) or header.get('version')!=1:raise ValueError('Unsupported I/Q protocol version')
    # Validate the bounded header before reading any data payload.
    kind=header.get('type')
    if kind=='iq':
        _validate_header(header)
        if payload_bytes!=header['samples']*8:raise ValueError('I/Q payload size differs from sample count')
    elif kind in ('end','ack'):
        if payload_bytes:raise ValueError('Control frames cannot contain samples')
    else:raise ValueError('Unknown I/Q frame type')
    return header,_exact(sock,payload_bytes)


def _integer(value):return isinstance(value,int) and not isinstance(value,bool)


def _validate_header(h):
    if not isinstance(h.get('receiver'),str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',h['receiver']):
        raise ValueError('Invalid receiver ID')
    for key in ('sequence','sample_start','samples','sim_time_ns'):
        if not _integer(h.get(key)):raise ValueError(f'{key} must be an integer')
    if h['sequence']<0 or h['sample_start']<0 or not 1<=h['samples']<=MAX_SAMPLES:
        raise ValueError('Invalid sequence, offset or sample count')
    for key in ('sample_rate_hz','carrier_hz','clipped_component_fraction'):
        value=h.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError(f'{key} must be finite')
    if h['sample_rate_hz']<=0 or h['carrier_hz']<=0 or not 0<=h['clipped_component_fraction']<=1:
        raise ValueError('Invalid sample rate, carrier or clipping fraction')
    if h.get('dtype')!='cf32_le' or h.get('units')!='volts':raise ValueError('Expected cf32_le complex volts')


def _advance(states,h):
    name=h['receiver'];previous=states.get(name)
    if previous is None:
        if h['sample_start']!=0:raise ValueError('First receiver sample offset must be zero')
    else:
        offset,epoch,rate,carrier=previous
        if h['sample_start']!=offset or h['sim_time_ns']!=epoch:
            raise ValueError('Receiver samples or timestamps are discontinuous')
        if (h['sample_rate_hz'],h['carrier_hz'])!=(rate,carrier):
            raise ValueError('Receiver rate/carrier changed within stream')
    duration=h['samples']*1e9/h['sample_rate_hz']
    if abs(duration-round(duration))>1e-4:raise ValueError('Window duration must align to integer nanoseconds')
    states[name]=(h['sample_start']+h['samples'],h['sim_time_ns']+round(duration),h['sample_rate_hz'],h['carrier_hz'])


@dataclass(frozen=True)
class StreamIQBlock:
    receiver: str
    samples: np.ndarray
    sample_start: int
    sim_time_ns: int
    sample_rate_hz: float
    carrier_hz: float
    clipped_component_fraction: float


class IQStreamWriter:
    """Use send_capture as a live callback; finish waits for consumer acknowledgement.

    The supplied socket needs a finite timeout. The caller owns socket closure.
    Any failure makes this connection unusable; do not retry frames on it.
    """
    def __init__(self,sock,*,carrier_hz):
        if sock.gettimeout() is None or sock.gettimeout()<=0:raise ValueError('A finite positive socket timeout is required')
        self.sock=sock;self.carrier_hz=carrier_hz;self.states={};self.sequence=0;self.closed=False

    def send_capture(self,receiver,capture):
        if self.closed:raise RuntimeError('I/Q stream is closed')
        samples=np.asarray(capture.adc_iq_volts,dtype='<c8')
        if samples.ndim!=1 or not np.isfinite(samples).all():raise ValueError('Finite one-dimensional samples required')
        h={'type':'iq','sequence':self.sequence,'receiver':receiver,
            'sample_start':self.states.get(receiver,(0,))[0], 'samples':len(samples),
            'sim_time_ns':capture.sim_time_ns,'sample_rate_hz':capture.actual_sample_rate_hz,
            'carrier_hz':self.carrier_hz,'clipped_component_fraction':capture.clipped_component_fraction,
            'dtype':'cf32_le','units':'volts'}
        try:
            _validate_header(h);_advance(self.states,h);_send(self.sock,h,samples.tobytes())
            self.sequence+=1
        except BaseException:
            self.closed=True
            raise

    def finish(self):
        if self.closed:raise RuntimeError('I/Q stream is closed')
        self.closed=True
        totals={name:state[0] for name,state in self.states.items()}
        _send(self.sock,{'type':'end','sequence':self.sequence,'sample_totals':totals})
        ack,_=_receive(self.sock)
        if ack!={'version':1,'type':'ack','sequence':self.sequence,'sample_totals':totals}:
            raise ValueError('Consumer did not acknowledge the complete sample stream')
        return totals


def iter_stream(sock):
    """Yield complete voltage blocks; acknowledge only after consumer exhausts them.

    Breaking iteration early or raising in processing leaves completion
    unacknowledged. EOF without an end frame is a failure, not normal completion.
    """
    if sock.gettimeout() is None or sock.gettimeout()<=0:raise ValueError('A finite positive socket timeout is required')
    states={};sequence=0
    while True:
        h,payload=_receive(sock)
        if not _integer(h.get('sequence')) or h['sequence']!=sequence:raise ValueError('I/Q sequence mismatch')
        if h['type']=='end':
            totals={name:state[0] for name,state in states.items()}
            if h.get('sample_totals')!=totals:raise ValueError('I/Q completion totals mismatch')
            _send(sock,{'type':'ack','sequence':sequence,'sample_totals':totals})
            return
        if h['type']!='iq':raise ValueError('Unexpected I/Q control frame')
        _advance(states,h)
        samples=np.frombuffer(payload,dtype='<c8').copy()
        if not np.isfinite(samples).all():raise ValueError('Nonfinite I/Q samples')
        sequence+=1
        yield StreamIQBlock(h['receiver'],samples,h['sample_start'],h['sim_time_ns'],
            h['sample_rate_hz'],h['carrier_hz'],h['clipped_component_fraction'])
