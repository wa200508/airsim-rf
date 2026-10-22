"""Real HTTP backpressure with delayed, failed and cancelled RF processing."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import pytest

from airsim_rf.dashboard_sync import advance_after_skill, wait_for_skill_epoch


@pytest.fixture
def skill_http():
    state={'ready':False,'failed':False,'epoch':120000000,'requests':[]}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state['requests'].append(self.path)
            if state['failed']:self.send_error(503);return
            if not state['ready']:self.send_error(404);return
            data=json.dumps({'sim_time_ns':state['epoch'],'complete_windows':1}).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield state,server.server_port
    finally:server.shutdown();server.server_close();thread.join()


def test_flight_does_not_advance_until_all_rf_processing_finishes(skill_http):
    state,port=skill_http;steps=[]
    class World:
        def continue_until_sim_time(self,epoch,wait_until_complete):steps.append((epoch,wait_until_complete))
    async def scenario():
        task=asyncio.create_task(advance_after_skill(World(),120000000,120000000,'127.0.0.1',port,lambda:False,timeout=2))
        while not state['requests']:await asyncio.sleep(.01)
        await asyncio.sleep(.1)
        assert steps==[] and not task.done()
        # Simulates the consumer completing covariance/PSD/MUSIC, after the
        # samples have already arrived. Only this event releases the world.
        state['ready']=True
        assert await task
        assert steps==[(240000000,True)]
        assert set(state['requests'])=={'/epochs/120000000'}
    asyncio.run(scenario())


def test_stop_and_timeout_cannot_advance_flight(skill_http):
    _,port=skill_http;steps=[];stopped=False
    class World:
        def continue_until_sim_time(self,*args,**kwargs):steps.append(args)
    async def scenario():
        nonlocal stopped
        task=asyncio.create_task(advance_after_skill(World(),120000000,120000000,'127.0.0.1',port,lambda:stopped,timeout=2))
        await asyncio.sleep(.1);stopped=True
        assert not await task
        with pytest.raises(TimeoutError,match='did not finish'):
            await advance_after_skill(World(),120000000,120000000,'127.0.0.1',port,lambda:False,timeout=.05)
        assert steps==[]
    asyncio.run(scenario())


@pytest.mark.parametrize('failure',['wrong_epoch','failed'])
def test_consumer_failure_or_wrong_epoch_is_fatal(skill_http,failure):
    state,port=skill_http;state['ready']=True
    if failure=='failed':state['failed']=True
    else:state['epoch']+=1
    with pytest.raises(RuntimeError,match='rejected|different'):
        asyncio.run(wait_for_skill_epoch('127.0.0.1',port,120000000,lambda:False,timeout=1))
