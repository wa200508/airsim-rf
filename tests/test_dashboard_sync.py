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


def test_long_flight_reply_survives_old_wall_deadline_and_socket_close_cancels():
    # Exercise the actual NNG context used by native asynchronous flight RPCs.
    # The old one-hour deadline is compressed to 20 ms for this regression.
    from types import SimpleNamespace
    pynng=pytest.importorskip('pynng')
    from airsim_rf.dashboard_sync import configure_flight_client
    async def run():
        with pynng.Rep0(listen='inproc://long-flight-test',recv_timeout=500) as server, \
             pynng.Req0(dial='inproc://long-flight-test',recv_timeout=20,resend_time=-1) as command, \
             pynng.Req0(recv_timeout=20) as ordinary:
            configure_flight_client(SimpleNamespace(socket_services=command))
            assert ordinary.recv_timeout==20
            with command.new_context() as context:
                await context.asend(b'flight');pending=asyncio.create_task(context.arecv())
                assert await server.arecv()==b'flight'
                await asyncio.sleep(.08);assert not pending.done()
                await server.asend(b'complete');assert await pending==b'complete'
            context=command.new_context()
            await context.asend(b'next-flight');pending=asyncio.create_task(context.arecv())
            assert await server.arecv()==b'next-flight'
            command.close()
            with pytest.raises(pynng.exceptions.NNGException):await asyncio.wait_for(pending,1)
            # NNG closes child contexts with the socket; release the Python wrapper.
            try:context.close()
            except pynng.exceptions.Closed:pass
    asyncio.run(run())


def test_flight_failures_report_actor_and_preserve_exception():
    from types import SimpleNamespace
    from airsim_rf.dashboard_sync import check_flight_tasks
    async def run():
        pending=asyncio.get_running_loop().create_future()
        check_flight_tasks([(SimpleNamespace(name='Drone1'),pending)])
        pending.set_exception(TimeoutError('native reply failed'))
        with pytest.raises(RuntimeError,match='Drone1: TimeoutError: native reply failed') as failure:
            check_flight_tasks([(SimpleNamespace(name='Drone1'),pending)])
        assert isinstance(failure.value.__cause__,TimeoutError)
        pending=asyncio.get_running_loop().create_future();pending.set_result(False)
        with pytest.raises(RuntimeError,match='returned false'):check_flight_tasks([(SimpleNamespace(name='Drone2'),pending)])
    asyncio.run(run())
