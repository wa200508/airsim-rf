"""Real host signals/locks/child cancellation; Docker commands are stubbed here."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lifecycle_dashboard', ROOT / 'src/airsim_rf/dashboard.py')
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)


def instance(run):
    return dashboard.Dashboard(SimpleNamespace(repo=ROOT, run_dir=Path(run), port=8765,
        ready_timeout=10, sim_image='render', rf_image='gpu', skill_image='skill'))


CHILD = '''
import importlib.util,json,sys,time
spec=importlib.util.spec_from_file_location('dashboard_child',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
mode=sys.argv[4]
def bootstrap(self):
    self.boot_count=getattr(self,'boot_count',0)+1
    self.owned_names.add('test-probe');self.network_created=True
    (self.run/'phase').write_text(str(self.boot_count))
    if mode=='failure':raise RuntimeError('injected startup failure')
    if mode=='startup' or self.boot_count>1:
        while True:self.ensure_running();time.sleep(.02)
def cleanup(self,args):
    with (self.run/'cleanup.jsonl').open('a') as out:out.write(json.dumps(args)+'\\n')
    return module.subprocess.CompletedProcess(args,0,'','')
module.Dashboard.bootstrap=bootstrap
module.Dashboard.cleanup_command=cleanup
module.Dashboard.snapshot=lambda self:{'token':self.token}
sys.argv=['dashboard','--port',sys.argv[2],'--run-dir',sys.argv[3]]
module.main()
'''


class DashboardLifecycleTest(unittest.TestCase):
    def wait_for(self, predicate, process):
        deadline=time.monotonic()+8
        while not predicate():
            if process.poll() is not None or time.monotonic()>deadline:
                self.fail('Child exited or timed out before expected lifecycle phase')
            time.sleep(.02)

    def check_child_shutdown(self, mode, shutdown_signal=signal.SIGTERM):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            child=subprocess.Popen([sys.executable,'-c',CHILD,str(ROOT/'src/airsim_rf/dashboard.py'),
                str(port),directory,mode],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.wait_for(lambda:(run/'phase').exists(),child)
                if mode=='worker':
                    opener=build_opener(ProxyHandler({}));base=f'http://127.0.0.1:{port}'
                    with opener.open(base+'/api/status',timeout=3) as response:token=json.load(response)['token']
                    request=Request(base+'/api/prepare',method='POST',headers={'X-Dashboard-Token':token})
                    with opener.open(request,timeout=3) as response:self.assertEqual(response.status,202)
                    self.wait_for(lambda:(run/'phase').read_text()=='2',child)
                if mode!='failure':child.send_signal(shutdown_signal)
                _,stderr=child.communicate(timeout=8)
                self.assertEqual(child.returncode,1 if mode=='failure' else 0,stderr)
                cleanup=[json.loads(line) for line in (run/'cleanup.jsonl').read_text().splitlines()]
                self.assertTrue(any(c[:3]==['docker','rm','-f'] and 'test-probe' in c for c in cleanup))
                self.assertTrue(any(c[:3]==['docker','network','rm'] for c in cleanup))
                # Shutdown must release the lock and listening socket, even if
                # the process never reached its HTTP serving loop.
                reopened=instance(directory);reopened.acquire_run();reopened.close()
                with socket.socket() as sock:
                    sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                    sock.bind(('127.0.0.1',port))
            finally:
                if child.poll() is None:child.kill();child.communicate()

    def test_signals_during_startup_run_cleanup(self):
        for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
            with self.subTest(signal=number):self.check_child_shutdown('startup',number)

    def test_startup_exception_runs_cleanup(self):
        self.check_child_shutdown('failure')

    def test_signal_during_prepare_worker_cancels_before_cleanup_finishes(self):
        self.check_child_shutdown('worker')

    def test_second_launcher_cannot_modify_active_run_directory(self):
        with tempfile.TemporaryDirectory() as run:
            first=instance(run);second=instance(run)
            first.acquire_run()
            try:
                with self.assertRaisesRegex(RuntimeError,'Another dashboard launcher'):
                    second.acquire_run()
                second.close()
                self.assertFalse((Path(run)/'command.json').exists())
            finally:first.close()

    def test_shutdown_cancels_slow_command_and_reaps_child(self):
        with tempfile.TemporaryDirectory() as run:
            obj=instance(run);obj.acquire_run();errors=[]
            marker=Path(run)/'child.pid'
            script='import os,time; from pathlib import Path; Path('+repr(str(marker))+').write_text(str(os.getpid())); time.sleep(60)'
            def command():
                try:
                    with obj.operation_lock:obj.command([sys.executable,'-c',script])
                except RuntimeError as error:errors.append(str(error))
            thread=threading.Thread(target=command);thread.start()
            deadline=time.monotonic()+5
            while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
            try:self.assertTrue(marker.exists())
            finally:obj.close();thread.join(timeout=3)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,['Dashboard is shutting down'])
            with self.assertRaises(ProcessLookupError):os.kill(int(marker.read_text()),0)

    def test_stale_recovery_selects_only_this_run_directory(self):
        with tempfile.TemporaryDirectory() as run:
            obj=instance(run);calls=[]
            def command(args):
                calls.append(args)
                return SimpleNamespace(stdout='old-container' if args[1]=='ps' else 'old-network' if args[2]=='ls' else '')
            with patch.object(obj,'command',command):obj.cleanup_stale()
            selector='label=org.airsim-rf.dashboard.run='+obj.run_key
            self.assertEqual(calls,[['docker','ps','-aq','--filter',selector],
                ['docker','rm','-f','old-container'],['docker','network','ls','-q','--filter',selector],
                ['docker','network','rm','old-network']])

    def test_cleanup_continues_when_docker_stop_times_out(self):
        with tempfile.TemporaryDirectory() as run:
            obj=instance(run);obj.network_created=True
            obj.processes={'sim':SimpleNamespace(wait=lambda timeout:None)};calls=[]
            def execute(args,**kwargs):
                calls.append(args)
                if args[1]=='stop':raise subprocess.TimeoutExpired(args,8)
                return subprocess.CompletedProcess(args,0,'','')
            with patch.object(dashboard.subprocess,'run',execute):obj.stop()
            self.assertTrue(any(c[:3]==['docker','rm','-f'] for c in calls))
            self.assertTrue(any(c[:3]==['docker','network','rm'] for c in calls))


if __name__ == '__main__':
    unittest.main()
