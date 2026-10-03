"""Offline two-process Sionna CPU demonstration of the distributed RF barrier."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from airsim_rf.distributed.client import CaptureBarrier, WorkerClient
from airsim_rf.distributed.coordinator import DemoSource, run_simulation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-s", type=float, default=0.1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    processes = []
    with tempfile.TemporaryDirectory(prefix="airsim-rf-") as directory:
        clients, receivers = [], []
        try:
            for index in range(2):
                name = f"rx{index}"
                log = Path(directory)/f"{name}.log"
                with log.open("w") as stream:
                    processes.append(subprocess.Popen([sys.executable, "-m", "airsim_rf.distributed.worker",
                        "--backend", "cpu", "--receiver-id", name, "--host", "127.0.0.1", "--port", "0",
                        "--grpc-address", f"unix:{directory}/{name}.sock", "--seed", str(42+index)],
                        stdout=stream, stderr=subprocess.STDOUT))
                deadline = time.monotonic()+60
                while True:
                    lines = log.read_text().splitlines()
                    ready = next((json.loads(line) for line in lines if line.startswith('{"http_port":')), None)
                    if ready:
                        break
                    if processes[-1].poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f"Worker failed to start:\n{log.read_text()}")
                    time.sleep(0.05)
                url = f"http://127.0.0.1:{ready['http_port']}"
                clients.append(WorkerClient(url, name))
                receivers.append({"receiver_id": name, "url": url})
            with CaptureBarrier(clients) as barrier:
                summary = run_simulation(DemoSource(receivers, [{"name": "reflector", "position_ned_m": [12, 0, 0],
                    "rcs_m2": 1}]), barrier, duration_ns=round(args.duration_s*1e9), output=args.output)
                assert summary["rf_chirps_per_receiver"] == round(args.duration_s*1e9)//5_000_000+1
                print(json.dumps(summary, indent=2))
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
