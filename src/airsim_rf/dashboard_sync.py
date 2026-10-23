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
