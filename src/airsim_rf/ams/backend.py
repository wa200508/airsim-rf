"""Squall-compatible RF control backend; upstream C++ MEL remains the GRA API."""
from concurrent.futures import ThreadPoolExecutor
import time

import grpc

from . import squall_rf_pb2 as pb
from . import squall_rf_pb2_grpc as rpc


class RFControl(rpc.SquallRfControlServicer):
    def __init__(self, worker):
        self.worker = worker

    def GetStatus(self, request, context):
        w = self.worker
        with w.state_lock:
            mode = w.mode
        return pb.GetStatusResponse(name=w.receiver_id, domain="rf", running=True, ready=True,
            uptime_seconds=int(time.monotonic()-w.started), rf_status=pb.RfStatus(
                center_frequency_hz=round(w.profile.carrier_hz), sample_rate=round(w.profile.sample_rate_hz),
                block_size=w.profile.num_samples, source_type="rf_environment", current_mode=mode))

    def AddDataDestination(self, request, context):
        try:
            self.worker.add_destination(request.client_id, request.udp_destination)
            return pb.AddDataDestinationResponse(success=True)
        except (ValueError, OSError) as error:
            return pb.AddDataDestinationResponse(success=False, error_message=str(error))

    def RemoveDataDestination(self, request, context):
        try:
            self.worker.remove_destination(request.client_id)
            return pb.RemoveDataDestinationResponse(success=True)
        except ValueError as error:
            return pb.RemoveDataDestinationResponse(success=False, error_message=str(error))

    def TuneRf(self, request, context):
        p = self.worker.profile
        accepted = (request.center_frequency_hz in (0, round(p.carrier_hz))
                    and request.sample_rate in (0, round(p.sample_rate_hz))
                    and request.bandwidth_hz in (0, round(p.bandwidth_hz))
                    and not request.HasField("gain") and not request.HasField("agc"))
        return pb.TuneRfResponse(success=accepted, actual_center_frequency_hz=round(p.carrier_hz),
            error_message="" if accepted else "This FMCW profile has fixed frequency, sweep and ADC rate; gain/AGC tuning is unsupported")

    def CommandRf(self, request, context):
        if request.WhichOneof("command") != "set_mode" or request.set_mode not in (1, 2, 3, 4):
            return pb.CommandRfResponse(success=False, error_message="Unsupported RF mode")
        with self.worker.state_lock:
            self.worker.mode = request.set_mode
        return pb.CommandRfResponse(success=True)


def grpc_server(worker, address):
    server = grpc.server(ThreadPoolExecutor(max_workers=4), maximum_concurrent_rpcs=16)
    rpc.add_SquallRfControlServicer_to_server(RFControl(worker), server)
    port = server.add_insecure_port(address)
    if port == 0:
        raise RuntimeError(f"Could not bind RF control server at {address}")
    server.start()
    return server, port
