"""Backpressure for the dashboard's single simulation stepping owner."""
import asyncio
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

_open = build_opener(ProxyHandler({})).open


async def wait_for_skill_epoch(host, port, epoch, stop_requested, *, timeout=120):
    """Wait for all channels and diagnostics, not merely a successful TCP send.

    Internal HTTP deliberately bypasses environment proxies. Waiting does not
    advance simulation time or discard any samples. Stop remains responsive.
    """
    deadline = time.monotonic() + timeout

    def probe():
        try:
            with _open(f'http://{host}:{port}/epochs/{epoch}', timeout=.5) as response:
                state = json.load(response)
        except HTTPError as error:
            error.close()
            if error.code == 404:
                return False
            raise RuntimeError(f'RF skill rejected epoch {epoch}: HTTP {error.code}') from error
        except (OSError, URLError):
            return False
        if state.get('sim_time_ns') != epoch:
            raise RuntimeError('RF skill acknowledged a different simulation epoch')
        return True

    while not stop_requested():
        if await asyncio.to_thread(probe):
            return True
        if time.monotonic() >= deadline:
            raise TimeoutError(f'RF skill did not finish simulation epoch {epoch} within {timeout:g}s')
        await asyncio.sleep(.05)
    return False


async def advance_after_skill(world, epoch, step_ns, host, port, stop_requested, *, timeout=120, on_complete=None):
    """The camera/flight cannot run ahead of an unfinished RF window."""
    if not await wait_for_skill_epoch(host, port, epoch, stop_requested, timeout=timeout):
        return False
    if on_complete is not None:
        await on_complete()
    if stop_requested():
        return False
    world.continue_until_sim_time(epoch + step_ns, wait_until_complete=True)
    return True


def read_skill_frame(host, port, epoch):
    with _open(f'http://{host}:{port}/frames/{epoch}?compact=1', timeout=5) as response:
        frame=json.load(response)
    if frame.get('sim_time_ns')!=epoch:raise ValueError('Recording skill epoch differs')
    return frame
