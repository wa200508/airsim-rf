"""Flight backpressure uses generic stream commits, with no algorithm HTTP API."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import socket
import threading
import numpy as np
import pytest
from airsim_rf.sample_stream import SampleStreamWriter,iter_stream
from airsim_rf.dashboard_sync import advance_after_commit


def test_arbitrary_delayed_receiver_releases_flight_without_a_skill_service():
    source,receiver=socket.socketpair();source.settimeout(2);receiver.settimeout(2)
    arrived=threading.Event();release=threading.Event();steps=[]
    class World:
        def continue_until_sim_time(self,epoch,wait_until_complete):steps.append((epoch,wait_until_complete))
    def consume():
        with receiver:
            for block in iter_stream(receiver):
                assert not hasattr(block,'sim_time_ns')
                arrived.set();assert release.wait(2)
    with source,ThreadPoolExecutor(1) as pool:
        consumer=pool.submit(consume);writer=SampleStreamWriter(source,carrier_hz=915e6)
        writer.send_samples('rx',np.ones(2,dtype=complex),timestamp_ns=0,sample_rate_hz=2e6)
        async def run():
            task=asyncio.create_task(advance_after_commit(World(),writer,0,1000,lambda:False))
            while not arrived.is_set():await asyncio.sleep(.01)
            await asyncio.sleep(.05);assert steps==[] and not task.done()
            release.set();assert await task
            assert steps==[(1000,True)]
        asyncio.run(run());writer.finish();consumer.result(timeout=2)


def test_receiver_failure_or_timeout_does_not_step():
    source,receiver=socket.socketpair();source.settimeout(.05);receiver.settimeout(.05)
    class World:
        def continue_until_sim_time(self,*args,**kwargs):pytest.fail('Must not advance')
    with source,receiver:
        writer=SampleStreamWriter(source,carrier_hz=915e6)
        writer.send_samples('rx',np.ones(2,dtype=complex),timestamp_ns=0,sample_rate_hz=2e6)
        with pytest.raises(TimeoutError):asyncio.run(advance_after_commit(World(),writer,0,1000,lambda:False))
        assert writer.closed


def test_operator_stop_aborts_wait_without_advancing():
    import time
    source,receiver=socket.socketpair();source.settimeout(120);receiver.settimeout(2)
    stopped=False
    class World:
        def continue_until_sim_time(self,*args,**kwargs):pytest.fail('Stopped world must not advance')
    with source,receiver:
        writer=SampleStreamWriter(source,carrier_hz=915e6)
        writer.send_samples('rx',np.ones(2,complex),timestamp_ns=0,sample_rate_hz=2e6)
        async def run():
            nonlocal stopped
            task=asyncio.create_task(advance_after_commit(World(),writer,0,1000,lambda:stopped))
            await asyncio.sleep(.05);stopped=True
            assert not await task
        start=time.monotonic();asyncio.run(run())
        assert time.monotonic()-start<1 and writer.closed
