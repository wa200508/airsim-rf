"""Test a compiled public MEL probe and the starter kit's real Couloir binary."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import uuid

import grpc
import numpy as np

from airsim_rf.distributed.client import WorkerClient
from airsim_rf.distributed.protocol import CaptureRequest, CaptureResult


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def await_log(process, path, check):
    deadline = time.monotonic()+60
    while time.monotonic() < deadline:
        value = path.read_text()
        result = check(value)
        if result:
            return result
        if process.poll() is not None:
            raise RuntimeError(value)
        time.sleep(.05)
    raise TimeoutError(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--couloir", type=Path, required=True)
    args = parser.parse_args()
    processes = []
    with tempfile.TemporaryDirectory(prefix="rf-mel-") as directory:
        directory = Path(directory)
        def start(command, name):
            path = directory/f"{name}.log"
            with path.open("w") as log:
                process = subprocess.Popen([str(x) for x in command], stdout=log, stderr=subprocess.STDOUT)
            processes.append(process)
            return process, path
        try:
            worker, worker_log = start([sys.executable, "-m", "airsim_rf.distributed.worker", "--backend", "cpu",
                "--receiver-id", "rx0", "--host", "127.0.0.1", "--port", "0", "--no-noise",
                "--grpc-address", f"unix:{directory}/control.sock"], "worker")
            ready = await_log(worker, worker_log, lambda s: next(
                (json.loads(line) for line in s.splitlines() if line.startswith('{"http_port":')), None))
            port, metrics = free_port(), free_port()
            config = directory/"couloir.toml"
            config.write_text(f'tcp_addr = "127.0.0.1:{port}"\nmetrics_port = {metrics}\n\n[routes]\n'
                              f'"/squall.rf.control.v1.SquallRfControl/" = "{directory}/control.sock"\n')
            couloir, couloir_log = start([args.couloir.resolve(), "--config", config], "couloir")
            with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
                grpc.channel_ready_future(channel).result(timeout=10)
                from airsim_rf.ams import squall_rf_pb2 as pb, squall_rf_pb2_grpc as rpc
                assert rpc.SquallRfControlStub(channel).GetStatus(pb.GetStatusRequest(), timeout=2).ready
            profile = directory/"profile.json"
            profile.write_text(json.dumps({"log_level": "off", "client_id": "rf-test", "face_id": 0,
                "va_definition_id": 0, "va_instance_id": 0, "rx_element_group_label": "0", "rx_stream_id": 0,
                "control_address": f"127.0.0.1:{port}", "data_host": "127.0.0.1"}))
            native, native_log = start([args.probe.resolve(), profile, directory/"callback.sc16"], "native")
            await_log(native, native_log, lambda s: "MEL_READY" in s)
            client = WorkerClient(f"http://127.0.0.1:{ready['http_port']}", "rx0")
            run_id = str(uuid.uuid4())
            client.session(run_id)
            request = CaptureRequest.from_dict({"protocol_version": 1, "run_id": run_id,
                "receiver_id": "rx0", "sequence": 0, "sim_time_ns": 0, "position_m": [0, 0, 0],
                "velocity_m_s": [0, 0, 0], "orientation_rad": [0, 0, 0],
                "targets": [{"name": "reflector", "position_m": [12, 0, 0], "rcs_m2": 1}]})
            result = CaptureResult.decode(client.request("/v1/capture", request.to_dict()), request)
            if native.wait(timeout=15) != 0:
                raise RuntimeError(native_log.read_text())
            decoded = np.fromfile(directory/"callback.sc16", dtype="<i2").reshape(128, 2)
            volts = (decoded[:, 0].astype(float)+1j*decoded[:, 1])*result.metadata["volts_per_sc16_count"]
            np.testing.assert_allclose(volts, result.arrays["adc_iq_volts"], atol=result.metadata["volts_per_sc16_count"])
            client.session(run_id, release=True)
            print("PASS: native C++ MEL control -> Couloir -> worker UDS; worker UDP -> native MEL callback; 128 I/Q samples match volts")
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    main()
