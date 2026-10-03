"""Reliable receiver RPC and a fail-closed, concurrent RF update barrier."""
from concurrent.futures import ThreadPoolExecutor, wait
import http.client
import json
import time
from urllib.parse import urlsplit
import uuid

from .protocol import CaptureRequest, CaptureResult, MAX_RESPONSE_BYTES


class WorkerError(RuntimeError):
    pass


class WorkerClient:
    def __init__(self, url, receiver_id, *, timeout_s=30):
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.path not in ("", "/"):
            raise ValueError("Worker URL must be an http(s) origin without a path")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Worker URL must not contain credentials, query or fragment")
        self.url, self.receiver_id, self.timeout_s = url, receiver_id, timeout_s
        self.parsed = parsed

    def request(self, path, value=None, *, timeout_s=None):
        connection_type = http.client.HTTPSConnection if self.parsed.scheme == "https" else http.client.HTTPConnection
        connection = connection_type(self.parsed.hostname, self.parsed.port, timeout=timeout_s or self.timeout_s)
        try:
            body = None if value is None else json.dumps(value, allow_nan=False).encode()
            connection.request("GET" if value is None else "POST", path, body,
                               {} if body is None else {"Content-Type": "application/json"})
            response = connection.getresponse()
            result = response.read(MAX_RESPONSE_BYTES + 1)
            if len(result) > MAX_RESPONSE_BYTES:
                raise WorkerError("Worker response exceeds size limit")
            if response.status != 200:
                raise WorkerError(f"{self.receiver_id}: HTTP {response.status}: {result.decode(errors='replace')}")
            return result
        finally:
            connection.close()

    def health(self):
        result = json.loads(self.request("/health"))
        if not result.get("ready") or result.get("receiver_id") != self.receiver_id:
            raise WorkerError("Worker is not ready or receiver identity differs")
        return result

    def session(self, run_id, *, release=False):
        return json.loads(self.request("/v1/session", {"run_id": run_id, "release": release}))

    def capture(self, request, *, deadline):
        # Retry only a transport failure, using exactly the same request identity.
        for attempt in range(2):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{self.receiver_id}: RF barrier deadline expired")
            try:
                payload = self.request("/v1/capture", request.to_dict(), timeout_s=min(self.timeout_s, remaining))
                return CaptureResult.decode(payload, request)
            except (OSError, http.client.HTTPException):
                if attempt:
                    raise


class CaptureBarrier:
    """All receivers must return the requested epoch before physics may proceed."""
    def __init__(self, clients, *, timeout_s=30, run_id=None, scene_id="empty-free-space-v1"):
        self.clients = tuple(clients)
        if not self.clients or len({c.receiver_id for c in self.clients}) != len(self.clients):
            raise ValueError("Configure at least one worker, with unique receiver IDs")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self.timeout_s, self.run_id, self.sequence = timeout_s, run_id or str(uuid.uuid4()), 0
        self.failed = False
        self.claimed = []
        self.executor = ThreadPoolExecutor(max_workers=len(self.clients), thread_name_prefix="rf-rpc")
        try:
            healths = [c.health() for c in self.clients]
            if any(h["scene_id"] != scene_id for h in healths):
                raise WorkerError("Workers must load the coordinator's RF scene version")
            self.profile = healths[0]["profile"]
            acquisition = ("carrier_hz", "bandwidth_hz", "chirp_duration_s", "pri_s", "sample_rate_hz", "num_samples", "adc_start_s")
            if any(any(h["profile"][key] != self.profile[key] for key in acquisition) for h in healths):
                raise WorkerError("Receiver acquisition schedules/profiles differ")
            for client in self.clients:
                client.session(self.run_id)
                self.claimed.append(client)
        except Exception:
            self.close()
            raise

    def capture(self, sim_time_ns, poses, targets):
        if self.failed:
            raise WorkerError("RF barrier previously failed; simulation must remain paused")
        deadline = time.monotonic() + self.timeout_s
        requests = [CaptureRequest.from_dict({"protocol_version": 1, "run_id": self.run_id,
            "receiver_id": c.receiver_id, "sequence": self.sequence, "sim_time_ns": sim_time_ns,
            "position_m": poses[c.receiver_id][0], "velocity_m_s": poses[c.receiver_id][1],
            "orientation_rad": poses[c.receiver_id][2], "targets": [
                {"name": t.name, "position_m": t.position_m, "velocity_m_s": t.velocity_m_s, "rcs_m2": t.rcs_m2}
                for t in targets]}) for c in self.clients]
        futures = [self.executor.submit(c.capture, request, deadline=deadline)
                   for c, request in zip(self.clients, requests)]
        try:
            _, pending = wait(futures, timeout=max(0, deadline-time.monotonic()))
            if pending:
                raise TimeoutError("One or more receivers missed the RF barrier deadline")
            results = [future.result() for future in futures]
            self.sequence += 1
            return dict(zip((c.receiver_id for c in self.clients), results))
        except Exception:
            self.failed = True
            for future in futures:
                future.cancel()
            raise

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)
        for client in self.claimed:
            try:
                client.session(self.run_id, release=True)
            except (WorkerError, OSError):
                pass
        self.claimed.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
