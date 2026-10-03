"""A persistent Sionna process dedicated to one radar receiver and one GPU."""
import argparse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import signal
import socket
import threading
import time

import numpy as np

from .protocol import CaptureRequest, MAX_REQUEST_BYTES, encode_result, receiver_name, run_uuid, sc16_payload


class Conflict(ValueError):
    pass


class Busy(RuntimeError):
    pass


class ReceiverWorker:
    def __init__(self, receiver_id, *, backend="cpu", rf_scene=None, scene_id="empty-free-space-v1",
                 seed=42, noise_enabled=True, max_destinations=8):
        self.receiver_id = receiver_name(receiver_id)
        if backend not in ("cpu", "cuda"):
            raise ValueError("backend must be cpu or cuda; implicit fallback is not supported")
        if rf_scene and scene_id == "empty-free-space-v1":
            raise ValueError("Provide a scene_id version covering the RF scene and its assets")
        self.backend, self.scene_id, self.seed = backend, scene_id, seed
        self.max_destinations = max_destinations
        self.started = time.monotonic()
        self.state_lock, self.capture_lock = threading.Lock(), threading.Lock()
        self.run_id, self.sequence, self.sim_time_ns = None, -1, None
        self.mode, self.destinations, self.cache = 3, {}, OrderedDict()  # Squall RF_MODE_IDLE
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sionna")
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.setblocking(False)
        try:
            self.executor.submit(self._initialize, rf_scene, noise_enabled).result()
        except Exception:
            self.close()
            raise

    def _initialize(self, rf_scene, noise_enabled):
        # Set the requested variant before Sionna imports or creates scene arrays.
        import mitsuba as mi
        mi.set_variant("cuda_ad_mono_polarized" if self.backend == "cuda" else "llvm_ad_mono_polarized")
        from airsim_rf.fmcw import Distance2GoLProfile, FMCWRadar
        self.profile = replace(Distance2GoLProfile(), noise_enabled=noise_enabled)
        self.radar = FMCWRadar(self.profile, rf_scene=rf_scene, seed=self.seed)
        self.variant = mi.variant()

    def health(self):
        with self.state_lock:
            return {"ready": True, "receiver_id": self.receiver_id, "backend": self.backend,
                    "variant": self.variant, "scene_id": self.scene_id, "profile": asdict(self.profile),
                    "run_id": self.run_id, "sequence": self.sequence, "sim_time_ns": self.sim_time_ns,
                    "mode": self.mode, "destinations": len(self.destinations)}

    def session(self, run_id, *, release=False):
        run_uuid(run_id)
        if not isinstance(release, bool):
            raise ValueError("release must be a boolean")
        if not self.capture_lock.acquire(blocking=False):
            raise Busy("Receiver is computing a capture")
        try:
            with self.state_lock:
                if self.run_id not in (None, run_id):
                    raise Conflict("Receiver is owned by another simulation run; release it or restart the worker")
                if release:
                    self.run_id, self.sequence, self.sim_time_ns = None, -1, None
                    self.cache.clear()
                elif self.run_id is None:
                    self.executor.submit(setattr, self.radar, "rng", np.random.default_rng(self.seed)).result()
                    self.run_id = run_id
            return {"run_id": self.run_id, "receiver_id": self.receiver_id}
        finally:
            self.capture_lock.release()

    def add_destination(self, client_id, destination):
        if not client_id or len(client_id) > 256:
            raise ValueError("client_id must contain 1..256 characters")
        host, port_text = destination.rsplit(":", 1)
        port = int(port_text)
        if not host or not 1 <= port <= 65535:
            raise ValueError("Expected a UDP host:port with port 1..65535")
        address = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_DGRAM)[0][4]
        with self.state_lock:
            if client_id not in self.destinations and len(self.destinations) >= self.max_destinations:
                raise ValueError("RF UDP destination slots are full")
            self.destinations[client_id] = address

    def remove_destination(self, client_id):
        with self.state_lock:
            if client_id not in self.destinations:
                raise ValueError("Unknown client_id")
            del self.destinations[client_id]

    def capture(self, request):
        if request.receiver_id != self.receiver_id:
            raise Conflict("Capture addressed to the wrong receiver")
        if not self.capture_lock.acquire(blocking=False):
            raise Busy("Receiver is computing a capture; bounded admission rejects concurrent requests")
        try:
            digest = hashlib.sha256(request.canonical_bytes()).digest()
            with self.state_lock:
                if request.run_id != self.run_id:
                    raise Conflict("Claim this receiver with /v1/session before requesting captures")
                if request.sequence in self.cache:
                    old_digest, result = self.cache[request.sequence]
                    if digest != old_digest:
                        raise Conflict("A retry changed the original capture request")
                    return result  # No second noise draw or duplicate UDP transmission.
                if request.sequence != self.sequence + 1:
                    raise Conflict("Capture sequences must be contiguous and start at zero")
                if self.sim_time_ns is not None and request.sim_time_ns <= self.sim_time_ns:
                    raise Conflict("Simulation timestamps must strictly increase")
            start = time.perf_counter()
            capture = self.executor.submit(self.radar.capture, request.targets,
                position_m=request.position_m, velocity_m_s=request.velocity_m_s,
                orientation_rad=request.orientation_rad, sim_time_ns=request.sim_time_ns).result()
            payload, volts_per_count = sc16_payload(capture)
            delivered, failed = 0, 0
            with self.state_lock:
                if self.mode == 4:  # RF_MODE_OPERATIONAL
                    for address in self.destinations.values():
                        try:
                            self.udp.sendto(payload, address)
                            delivered += 1
                        except OSError:
                            failed += 1
            metadata = request.to_dict()
            metadata.update(profile=asdict(self.profile), backend=self.backend, variant=self.variant,
                            scene_id=self.scene_id, compute_ms=(time.perf_counter()-start)*1000,
                            volts_per_sc16_count=volts_per_count, udp_sent=delivered, udp_failed=failed,
                            clipped_components=capture.clipped_components)
            result = encode_result(capture, metadata)
            with self.state_lock:
                self.sequence, self.sim_time_ns = request.sequence, request.sim_time_ns
                self.cache[request.sequence] = (digest, result)
                while len(self.cache) > 8:
                    self.cache.popitem(last=False)
            return result
        finally:
            self.capture_lock.release()

    def close(self):
        self.udp.close()
        self.executor.shutdown(wait=True)


def http_server(worker, address):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_):
            pass

        def reply(self, status, body, content_type="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self.reply(200, worker.health())
            else:
                self.reply(404, {"error": "Unknown endpoint"})

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_REQUEST_BYTES:
                    self.reply(413, {"error": "Request exceeds size limit or is empty"})
                    return
                value = json.loads(self.rfile.read(size))
                if not isinstance(value, dict):
                    raise ValueError("Request must be a JSON object")
                if self.path == "/v1/session":
                    self.reply(200, worker.session(value["run_id"], release=value.get("release", False)))
                elif self.path == "/v1/capture":
                    result = worker.capture(CaptureRequest.from_dict(value))
                    self.reply(200, result, "application/x-npz")
                else:
                    self.reply(404, {"error": "Unknown endpoint"})
            except Conflict as error:
                self.reply(409, {"error": str(error)})
            except Busy as error:
                self.reply(429, {"error": str(error)})
            except (ValueError, TypeError, KeyError) as error:
                self.reply(400, {"error": str(error)})
            except (BrokenPipeError, ConnectionResetError):
                pass  # A completed capture remains in the retry cache.
            except Exception as error:
                self.reply(500, {"error": str(error)})
    server = ThreadingHTTPServer(address, Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receiver-id", required=True)
    parser.add_argument("--backend", choices=["cpu", "cuda"], default="cuda")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=22100)
    parser.add_argument("--grpc-address", default="unix:/tmp/airsim-rf-control.sock")
    parser.add_argument("--rf-scene")
    parser.add_argument("--scene-id", default="empty-free-space-v1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-noise", action="store_true")
    args = parser.parse_args()
    worker = ReceiverWorker(args.receiver_id, backend=args.backend, rf_scene=args.rf_scene,
                            scene_id=args.scene_id, seed=args.seed, noise_enabled=not args.no_noise)
    from airsim_rf.ams.backend import grpc_server
    control, port = grpc_server(worker, args.grpc_address)
    server = http_server(worker, (args.host, args.port))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    print(json.dumps({"http_port": server.server_port, "grpc_port": port, **worker.health()}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        control.stop(1).wait()
        worker.close()


if __name__ == "__main__":
    main()
