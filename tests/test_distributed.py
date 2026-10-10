import json
import socket
import threading
import uuid

import grpc
import numpy as np
import pytest

from airsim_rf.ams import squall_rf_pb2 as pb
from airsim_rf.ams import squall_rf_pb2_grpc as rpc
from airsim_rf.ams.backend import grpc_server
from airsim_rf.distributed.client import CaptureBarrier, WorkerClient, WorkerError
from airsim_rf.distributed.coordinator import AirSimSource, DemoSource, Snapshot, interpolate, run_simulation
from airsim_rf.distributed.protocol import CaptureRequest, CaptureResult
from airsim_rf.distributed.worker import ReceiverWorker, http_server


@pytest.fixture
def receiver():
    worker = ReceiverWorker("rx0", backend="cpu", noise_enabled=False)
    server = http_server(worker, ("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    control, port = grpc_server(worker, "127.0.0.1:0")
    with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
        yield worker, WorkerClient(f"http://127.0.0.1:{server.server_port}", "rx0"), rpc.SquallRfControlStub(channel)
    control.stop(0).wait()
    server.shutdown()
    thread.join()
    server.server_close()
    worker.close()


def request(run, sequence=0, epoch=0, receiver_id="rx0"):
    return CaptureRequest.from_dict({"protocol_version": 1, "run_id": run, "receiver_id": receiver_id,
        "sequence": sequence, "sim_time_ns": epoch, "position_m": [0, 0, 0], "velocity_m_s": [0, 0, 0],
        "orientation_rad": [0, 0, 0], "targets": [{"name": "target", "position_m": [12, 0, 0], "rcs_m2": 1}]})


def test_native_rf_control_udp_and_retry(receiver):
    worker, client, control = receiver
    status = control.GetStatus(pb.GetStatusRequest(), timeout=1)
    assert status.ready and status.rf_status.center_frequency_hz == 24_125_000_000
    assert status.rf_status.sample_rate == 100000 and status.rf_status.block_size == 128
    assert status.rf_status.source_type == "rf_environment"
    assert not control.TuneRf(pb.TuneRfRequest(center_frequency_hz=915000000), timeout=1).success
    assert not control.TuneRf(pb.TuneRfRequest(agc=True), timeout=1).success
    assert control.TuneRf(pb.TuneRfRequest(center_frequency_hz=24_125_000_000), timeout=1).success
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.bind(("127.0.0.1", 0))
        udp.settimeout(0.1)
        assert control.AddDataDestination(pb.AddDataDestinationRequest(
            client_id="native-mel-0", udp_destination=f"127.0.0.1:{udp.getsockname()[1]}"), timeout=1).success
        run = str(uuid.uuid4())
        client.session(run)
        first = request(run)
        payload = client.request("/v1/capture", first.to_dict())
        assert CaptureResult.decode(payload, first).metadata["udp_sent"] == 0
        with pytest.raises(socket.timeout):
            udp.recv(2048)  # IDLE mode does not emit UDP.
        assert control.CommandRf(pb.CommandRfRequest(set_mode=pb.RF_MODE_OPERATIONAL), timeout=1).success
        second = request(run, 1, 5_000_000)
        result = client.request("/v1/capture", second.to_dict())
        values = CaptureResult.decode(result, second)
        wire = np.frombuffer(udp.recv(2048), dtype="<i2").reshape(128, 2)
        volts = (wire[:, 0].astype(float)+1j*wire[:, 1])*values.metadata["volts_per_sc16_count"]
        np.testing.assert_allclose(volts, values.arrays["adc_iq_volts"], atol=values.metadata["volts_per_sc16_count"])
        assert client.request("/v1/capture", second.to_dict()) == result
        with pytest.raises(socket.timeout):
            udp.recv(2048)  # Retried HTTP capture cannot duplicate native delivery.
        changed = second.to_dict()
        changed["position_m"] = [1, 0, 0]
        with pytest.raises(WorkerError, match="HTTP 409"):
            client.request("/v1/capture", changed)
        with pytest.raises(WorkerError, match="HTTP 409"):
            client.session(str(uuid.uuid4()))
        with pytest.raises(WorkerError, match="HTTP 409"):
            client.request("/v1/capture", request(run, 3, 10_000_000).to_dict())
        with pytest.raises(WorkerError, match="HTTP 409"):
            client.request("/v1/capture", request(run, 2, 5_000_000).to_dict())
        with pytest.raises(WorkerError, match="HTTP 409"):
            client.request("/v1/capture", request(run, 2, 10_000_000, "rx1").to_dict())
        assert control.RemoveDataDestination(pb.RemoveDataDestinationRequest(client_id="native-mel-0"), timeout=1).success
        assert not control.RemoveDataDestination(pb.RemoveDataDestinationRequest(client_id="native-mel-0"), timeout=1).success
        client.session(run, release=True)
        assert worker.health()["run_id"] is None


def test_network_barrier_and_recorded_epochs(receiver, tmp_path):
    _, client, _ = receiver
    with CaptureBarrier([client]) as barrier:
        source = DemoSource([{"receiver_id": "rx0"}], [{"name": "t", "position_ned_m": [12, 0, 0], "rcs_m2": 1}])
        summary = run_simulation(source, barrier, duration_ns=20_000_000, output=tmp_path)
    directory = tmp_path/summary["run_id"]
    epochs = [json.loads(line) for line in (directory/"epochs.jsonl").read_text().splitlines()]
    assert [e["sim_time_ns"] for e in epochs] == [0, 5_000_000, 10_000_000, 15_000_000, 20_000_000]
    assert summary["physics_steps"] == 3
    assert len(list((directory/"rx0").glob("*.npz"))) == 5
    assert epochs[1]["truth_interval_ns"] == [0, 8_333_333]


def test_rotation_interpolation_crosses_pi_smoothly():
    previous = Snapshot(0, {"r": ([0, 0, 0], [1, 0, 0], [np.deg2rad(179), 0, 0])}, ())
    current = Snapshot(10, {"r": ([10, 0, 0], [3, 0, 0], [np.deg2rad(-179), 0, 0])}, ())
    poses, _ = interpolate(previous, current, 5)
    np.testing.assert_allclose(poses["r"][0], [5, 0, 0])
    np.testing.assert_allclose(poses["r"][1], [2, 0, 0])
    assert abs(abs(poses["r"][2][0])-np.pi) < 1e-10


def test_failed_receiver_prevents_further_physics_steps():
    class Client:
        def __init__(self, name, failed=False):
            self.receiver_id, self.failed = name, failed
        def health(self):
            return {"ready": True, "scene_id": "empty-free-space-v1", "profile": dict(
                carrier_hz=24.125e9, bandwidth_hz=200e6, chirp_duration_s=.0015,
                pri_s=.005, sample_rate_hz=100000, num_samples=128, adc_start_s=.0001)}
        def session(self, *args, **kwargs):
            pass
        def capture(self, request, *, deadline):
            if self.failed and request.sequence == 1:
                raise TimeoutError("receiver unavailable")
            class Result:
                metadata = {"compute_ms": 1}
            return Result()
    with CaptureBarrier([Client("a"), Client("b", True)]) as barrier:
        source = DemoSource([{"receiver_id": "a"}, {"receiver_id": "b"}], [])
        with pytest.raises(TimeoutError):
            run_simulation(source, barrier, duration_ns=100_000_000)
        assert source.time_ns == 8_333_333
        assert barrier.sequence == 1 and barrier.failed
        with pytest.raises(WorkerError, match="previously failed"):
            barrier.capture(10_000_000, {}, [])


def test_protocol_rejects_bad_epochs_and_identity():
    run = str(uuid.uuid4())
    for field, value in [("sim_time_ns", -1), ("sequence", True), ("receiver_id", "../../bad"),
                         ("position_m", [float("nan"), 0, 0]), ("run_id", "not-a-uuid")]:
        bad = request(run).to_dict()
        bad[field] = value
        with pytest.raises(ValueError):
            CaptureRequest.from_dict(bad)


@pytest.mark.parametrize('wrapped',[False,True])
def test_airsim_truth_uses_paused_native_time_and_rejects_torn_snapshot(wrapped):
    class World:
        epoch, paused = 1_000_000_000, True
        def pause(self):
            self.paused = True
        def is_paused(self):
            return self.paused
        def get_sim_time(self):
            return self.epoch
        def continue_until_sim_time(self, target, wait_until_complete):
            assert wait_until_complete
            self.epoch = target
    world = World()
    class Robot:
        torn = False
        def get_ground_truth_kinematics(self):
            if self.torn:
                world.epoch += 1
            value = {"kinematics": {"pose": {"position": dict(x=1, y=2, z=-3),
                "orientation": dict(x=0, y=0, z=0, w=1)},
                "twist": {"linear": dict(x=4, y=5, z=6), "angular": dict(x=0, y=0, z=0)}}}
            return value if wrapped else value["kinematics"]
    robot = Robot()
    source = AirSimSource(world, {"Drone1": robot}, [{"receiver_id": "rx0", "robot": "Drone1",
        "dis_entity_id": [1, 1, 1]}], [{"name": "drone-target", "robot": "Drone1", "rcs_m2": 1}])
    truth = source.snapshot()
    assert truth.time_ns == 1_000_000_000
    np.testing.assert_allclose(truth.poses["rx0"][0], [1, -2, 3])
    np.testing.assert_allclose(truth.poses["rx0"][1], [4, -5, -6])
    np.testing.assert_allclose(truth.entities[0]["position_ned_m"], [1, 2, -3])
    source.advance(1_010_000_000)
    assert source.snapshot().time_ns == 1_010_000_000
    robot.torn = True
    with pytest.raises(RuntimeError, match="advanced during"):
        source.snapshot()


def test_worker_response_cannot_change_requested_epoch(receiver):
    _, client, _ = receiver
    run = str(uuid.uuid4())
    client.session(run)
    first = request(run, epoch=123456789)
    payload = client.request("/v1/capture", first.to_dict())
    with pytest.raises(ValueError, match="sim_time_ns"):
        CaptureResult.decode(payload, request(run, epoch=123456790))
    client.session(run, release=True)
