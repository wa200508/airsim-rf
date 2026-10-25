"""Simulation stepping uses only algorithm-independent receiver backpressure."""
import asyncio


async def commit_window(writer, stop_requested):
    task=asyncio.create_task(asyncio.to_thread(writer.commit_window))
    while not task.done():
        if stop_requested():
            writer.abort()
            try:await task
            except (OSError,EOFError,RuntimeError):pass
            return False,None
        await asyncio.sleep(.02)
    epoch=await task
    return not stop_requested(),epoch



async def advance_after_commit(world,writer,epoch,step_ns,stop_requested,*,on_committed=None):
    proceed,acknowledged=await commit_window(writer,stop_requested)
    if acknowledged is None:return False
    if acknowledged!=epoch:raise RuntimeError('Receiver acknowledged a different acquisition timestamp')
    if on_committed is not None:await on_committed()
    if not proceed:return False
    world.continue_until_sim_time(epoch+step_ns,wait_until_complete=True)
    return True


def configure_flight_client(client):
    """Only native long-lived flight commands may await simulation-time completion.

    NNG uses -1 for an infinite receive timeout. The independent world/readback
    client remains bounded, and closing this socket cancels outstanding waits.
    Do not use this client for health checks or other ordinary RPCs.
    """
    client.socket_services.recv_timeout=-1


def check_flight_tasks(motions):
    """Surface native controller failures even while waiting for Launch or Resume."""
    for platform,task in motions:
        if task.done():
            try:
                result=task.result()
                if result is False:raise RuntimeError('native controller returned false')
            except Exception as error:
                actor=getattr(platform,'name',getattr(platform,'id','unknown'))
                raise RuntimeError(f'Native flight command failed for {actor}: '
                    f'{type(error).__name__}: {str(error) or "no error text"}') from error
