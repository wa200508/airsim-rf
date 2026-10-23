"""Real host HTTP transport; GPU/service bootstrap is stubbed explicitly."""
import json
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import URLError, HTTPError
from urllib.request import ProxyHandler, build_opener


ROOT = Path(__file__).resolve().parents[1]


class DashboardHostHTTPTest(unittest.TestCase):
    def test_saved_run_reopens_and_seeks_without_docker_or_service_stubs(self):
        spec=importlib.util.spec_from_file_location('replay_http',ROOT/'src/airsim_rf/dashboard_recording.py')
        recording=importlib.util.module_from_spec(spec);spec.loader.exec_module(recording)
        identifier='0123456789abcdef'
        with tempfile.TemporaryDirectory() as temporary:
            run=Path(temporary);writer=recording.RecordingWriter(run/'replays',identifier,{},.24,120000000)
            for index in range(2):
                epoch=index*120000000
                writer.frame({'sim_time_ns':epoch,'origin_ns':0,'sim_elapsed_s':index*.12,
                    'position_rf_m':[index,0,200],'geometry_sha256':'scene'},
                    {'sim_time_ns':epoch,'complete_windows':index+1,'payload_bytes':index+100,'bearings':[]})
                writer.camera({'key':identifier+'-'+str(epoch),'sim_time_ns':epoch,'geometry_sha256':'scene'},b'image '+str(index).encode())
            writer.status('complete')
            tools=run/'bin';tools.mkdir();marker=run/'docker-was-called'
            docker=tools/'docker';docker.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\nexit 99\n');docker.chmod(0o755)
            environment={**os.environ,'PATH':str(tools)+os.pathsep+os.environ['PATH']}
            opener=build_opener(ProxyHandler({}))
            # Stop/reopen twice, using the real main and handlers, no bootstrap
            # patches. The saved frames must survive and no Docker command runs.
            for _ in range(2):
                with socket.socket() as reservation:
                    reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
                process=subprocess.Popen([sys.executable,str(ROOT/'scripts/launch_dashboard.py'),'--replay',
                    '--run-dir',str(run),'--port',str(port)],env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                try:
                    base=f'http://127.0.0.1:{port}';deadline=time.monotonic()+10
                    while True:
                        try:
                            with opener.open(base+'/api/status',timeout=1) as response:state=json.load(response)
                            break
                        except URLError:
                            if process.poll() is not None or time.monotonic()>=deadline:self.fail('Replay did not start')
                            time.sleep(.05)
                    self.assertTrue(state['replay_only']);self.assertEqual(state['processes'],{})
                    self.assertEqual(state['recordings'][0]['id'],identifier)
                    for index in (1,0):
                        with opener.open(base+f'/api/status?recording={identifier}&time_s={index*.12}',timeout=2) as response:state=json.load(response)
                        self.assertEqual(state['producer']['position_rf_m'],[index,0,200])
                        self.assertEqual(state['skill']['complete_windows'],index+1)
                        with opener.open(base+state['camera']['url'],timeout=2) as response:self.assertEqual(response.read(),b'image '+str(index).encode())
                    request=__import__('urllib.request',fromlist=['Request']).Request(base+'/api/start',method='POST',headers={'X-Dashboard-Token':state['token']})
                    with self.assertRaises(HTTPError) as rejected:opener.open(request,timeout=2)
                    self.assertEqual(rejected.exception.code,409)
                    for query in ('recording=../outside','recording='+identifier+'&time_s=nan'):
                        with self.assertRaises(HTTPError) as rejected:opener.open(base+'/api/status?'+query,timeout=2)
                        self.assertEqual(rejected.exception.code,404)
                finally:
                    process.terminate();stdout,stderr=process.communicate(timeout=5)
                self.assertEqual(process.returncode,0,stderr)
            self.assertFalse(marker.exists());self.assertFalse((run/'command.json').exists())

    def test_host_browser_can_fetch_dashboard_assets_and_status(self):
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        # Run the actual main/HTTP handlers in a host Python process. Only the
        # Docker/GPU bootstrap and status payload are replaced for this test.
        child = '''
import importlib.util
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location('dashboard_http_test', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.Dashboard.bootstrap = lambda self: None
module.Dashboard.stop = lambda self: None
module.Dashboard.snapshot = lambda self: {'transport_test': 'host-loopback'}
sys.argv = ['dashboard', '--port', sys.argv[2], '--run-dir', sys.argv[3]]
module.main()
'''
        with tempfile.TemporaryDirectory() as run_dir:
            image_path=Path(run_dir)/'camera/0123456789abcdef-100.jpg'
            image_path.parent.mkdir();image_path.write_bytes(b'immutable epoch 100 image')
            (Path(run_dir)/'camera.jpg').write_bytes(b'latest unpaired image')
            process = subprocess.Popen(
                [sys.executable, '-c', child, str(ROOT / 'src/airsim_rf/dashboard.py'),
                 str(port), run_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True)
            try:
                # These are ordinary host requests, with no Docker exec, Docker
                # network address or port publishing. Bypass inherited proxies.
                opener = build_opener(ProxyHandler({}))
                base = f'http://127.0.0.1:{port}'
                deadline = time.monotonic() + 10
                while True:
                    try:
                        with opener.open(base + '/', timeout=1) as response:
                            html = response.read()
                        break
                    except URLError:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            self.fail('Host dashboard HTTP server did not start')
                        time.sleep(0.05)
                self.assertIn(b'RF FIELD LAB', html)
                for asset, content_type in (('/app.js', 'text/javascript'),
                                            ('/skill-display.js', 'text/javascript'),
                                            ('/style.css', 'text/css')):
                    with opener.open(base + asset, timeout=2) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers['Content-Type'], content_type)
                        self.assertTrue(response.read())
                with opener.open(base + '/api/status', timeout=2) as response:
                    state = json.load(response)
                    self.assertEqual(state['transport_test'], 'host-loopback')
                    self.assertEqual(state['selected_scenario'], 'drone-orbit')
                    catalog = {item['id']: item for item in state['scenario_catalog']}
                    self.assertTrue({'drone-orbit', 'mmwave-radar'} <= catalog.keys())
                    for item in catalog.values():
                        self.assertTrue(item['title'])
                        self.assertTrue((Path(item['directory']) / 'scenario.json').is_file())
                with opener.open(base + '/camera.jpg?frame=0123456789abcdef-100',timeout=2) as response:
                    self.assertEqual(response.read(),b'immutable epoch 100 image')
            finally:
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                    self.fail('Host dashboard did not shut down on SIGTERM')
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn(f'http://localhost:{port}', stdout)


if __name__ == '__main__':
    unittest.main()
