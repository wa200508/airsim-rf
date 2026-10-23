"""Neutral acquisition-clock contract, compatibility and window failure semantics."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import socket
import numpy as np
import pytest
from airsim_rf.sample_stream import SampleStreamWriter,iter_stream,_send,_receive
from airsim_rf.iq_stream import IQStreamWriter


def pair():
    a,b=socket.socketpair();a.settimeout(2);b.settimeout(2);return a,b


def test_old_source_adapter_and_new_hardware_facing_writer_produce_same_blocks():
    inputs=np.array([1+2j,3-4j],np.complex64);observed=[]
    for legacy in (True,False):
        a,b=pair()
        with a,b,ThreadPoolExecutor(1) as pool:
            consumer=pool.submit(lambda:list(iter_stream(b)))
            if legacy:
                writer=IQStreamWriter(a,carrier_hz=433e6)
                writer.send_capture('sensor',SimpleNamespace(adc_iq_volts=inputs,sim_time_ns=999,
                    actual_sample_rate_hz=1e6,clipped_component_fraction=0.))
            else:
                writer=SampleStreamWriter(a,carrier_hz=433e6)
                writer.send_samples('sensor',inputs,timestamp_ns=999,sample_rate_hz=1e6)
                assert writer.commit_window()==999
            writer.finish();block=consumer.result(timeout=2)[0]
            assert not hasattr(block,'sim_time_ns') and not hasattr(block,'paths')
            observed.append(block)
    np.testing.assert_array_equal(observed[0].samples,observed[1].samples)
    assert observed[0].timestamp_ns==observed[1].timestamp_ns==999


def test_processing_exception_never_acknowledges_window():
    a,b=pair()
    with a,b,ThreadPoolExecutor(1) as pool:
        def fail():
            with b:
                for block in iter_stream(b):raise RuntimeError('application failed')
        consumer=pool.submit(fail);writer=SampleStreamWriter(a,carrier_hz=915e6)
        writer.send_samples('rx',np.ones(2,complex),timestamp_ns=0,sample_rate_hz=2e6)
        with pytest.raises((EOFError,ConnectionError,OSError)):writer.commit_window()
        with pytest.raises(RuntimeError,match='application failed'):consumer.result(timeout=2)
        assert writer.closed


def test_simulation_truth_is_not_an_allowed_version_two_metadata_field():
    a,b=pair()
    with a,b:
        header={'type':'iq','sequence':0,'receiver':'rx','sample_start':0,'samples':1,'timestamp_ns':0,
            'sample_rate_hz':2e6,'carrier_hz':915e6,'clipped_component_fraction':0,'dtype':'cf32_le','units':'volts',
            'transmitter_position':[1,2,3]}
        _send(a,header,np.array([1j],dtype='<c8').tobytes())
        with pytest.raises(ValueError,match='metadata'):next(iter_stream(b))


def test_false_window_acknowledgement_invalidates_connection():
    a,b=pair()
    with a,b,ThreadPoolExecutor(1) as pool:
        def wrong():
            _receive(b);header,_=_receive(b);_send(b,{**header,'type':'window_ack','timestamp_ns':1})
        consumer=pool.submit(wrong);writer=SampleStreamWriter(a,carrier_hz=915e6)
        writer.send_samples('rx',np.ones(2,complex),timestamp_ns=0,sample_rate_hz=2e6)
        with pytest.raises(ValueError,match='acknowledge'):writer.commit_window()
        consumer.result(timeout=2);assert writer.closed
