"""Real host HTTP transport; GPU/service bootstrap is stubbed explicitly."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


ROOT = Path(__file__).resolve().parents[1]


class DashboardHostHTTPTest(unittest.TestCase):
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
                                            ('/style.css', 'text/css')):
                    with opener.open(base + asset, timeout=2) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers['Content-Type'], content_type)
                        self.assertTrue(response.read())
                with opener.open(base + '/api/status', timeout=2) as response:
                    self.assertEqual(json.load(response), {'transport_test': 'host-loopback'})
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
