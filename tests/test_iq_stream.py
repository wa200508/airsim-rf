"""Framing, multiplexing and failure semantics for a separate I/Q consumer."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import socket
import struct
import numpy as np
import pytest
from airsim_rf.iq_stream import IQStreamWriter,iter_stream,_send,MAX_HEADER


def pair():
    a,b=socket.socketpair();a.settimeout(2);b.settimeout(2);return a,b


def capture(epoch,values):
    return SimpleNamespace(adc_iq_volts=np.array(values,dtype=np.complex64),sim_time_ns=epoch,
        actual_sample_rate_hz=2e6,clipped_component_fraction=0.)


def test_multiplexed_samples_and_explicit_completion():
    a,b=pair()
    with a,b,ThreadPoolExecutor(1) as pool:
        received=pool.submit(lambda:list(iter_stream(b)))
        writer=IQStreamWriter(a,carrier_hz=915e6)
        for epoch in (1_700_000_000_000_000_000,1_700_000_000_000_001_000):
            writer.send_capture('rx0',capture(epoch,[1+2j,3+4j]))
            writer.send_capture('rx1',capture(epoch,[.1-.2j,.3-.4j]))
        assert writer.finish()=={'rx0':4,'rx1':4}
        blocks=received.result(timeout=2)
        assert [x.sample_start for x in blocks]==[0,0,2,2]
        assert blocks[-1].sim_time_ns==1_700_000_000_000_001_000
        np.testing.assert_array_equal(blocks[1].samples,np.array([.1-.2j,.3-.4j],dtype=np.complex64))
        with pytest.raises(RuntimeError):writer.send_capture('rx0',capture(0,[1j]))


def test_eof_is_not_successful_completion():
    a,b=pair()
    with a,b:
        writer=IQStreamWriter(a,carrier_hz=915e6);writer.send_capture('rx',capture(0,[1j]))
        a.shutdown(socket.SHUT_WR)
        reader=iter_stream(b);next(reader)
        with pytest.raises(EOFError,match='explicit completion'):next(reader)


def test_bad_lengths_rejected_before_payload_allocation():
    a,b=pair()
    with a,b:
        a.sendall(struct.pack('!II',MAX_HEADER+1,0))
        with pytest.raises(ValueError,match='lengths'):next(iter_stream(b))


def test_timestamp_gap_aborts_writer():
    a,b=pair()
    with a,b:
        writer=IQStreamWriter(a,carrier_hz=915e6);writer.send_capture('rx',capture(0,[1j]))
        with pytest.raises(ValueError,match='discontinuous'):writer.send_capture('rx',capture(501,[1j]))
        with pytest.raises(RuntimeError):writer.finish()


@pytest.mark.parametrize('change',[{'sequence':3},{'dtype':'pickle'},{'samples':2},{'sim_time_ns':1.5}])
def test_malformed_or_out_of_sequence_data_rejected(change):
    a,b=pair()
    with a,b:
        header={'type':'iq','sequence':0,'receiver':'rx','sample_start':0,'samples':1,
            'sim_time_ns':0,'sample_rate_hz':2e6,'carrier_hz':915e6,'clipped_component_fraction':0,
            'dtype':'cf32_le','units':'volts',**change}
        _send(a,header,np.array([1j],dtype='<c8').tobytes())
        with pytest.raises(ValueError):next(iter_stream(b))


def test_completion_requires_consumer_acknowledgement():
    a,b=pair()
    with a,b:
        a.settimeout(.05);writer=IQStreamWriter(a,carrier_hz=915e6)
        with pytest.raises(TimeoutError):writer.finish()
