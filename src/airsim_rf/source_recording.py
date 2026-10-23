"""Simulation-side camera/truth journal. Does not read application results."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading

ID = re.compile(r'[0-9a-f]{16}')
CAMERA_KEY = re.compile(r'[0-9a-f]{16}-[0-9]+')
MAX_OFFSET_NS = 60_000_000


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, allow_nan=False) + '\n')
    temporary.replace(path)


class RecordingWriter:
    def __init__(self, root, identifier, scenario, duration_s, step_ns, *, no_render=False, resume=False):
        if not ID.fullmatch(identifier):raise ValueError('Invalid recording ID')
        self.path = Path(root) / identifier
        self.path.mkdir(parents=True, exist_ok=resume)
        for name in ('frames', 'camera', 'results'):(self.path / name).mkdir(exist_ok=resume)
        self.lock = threading.RLock()
        if resume and (self.path/'manifest.json').exists():
            self.manifest=json.loads((self.path/'manifest.json').read_text())
            if (self.manifest['id'],self.manifest['duration_s'],self.manifest['step_ns'],self.manifest['no_render'])!=(identifier,duration_s,step_ns,no_render):
                raise ValueError('Recording configuration differs from coordinator preparation')
            return
        self.manifest = {'schema_version':2, 'id':identifier,
            'created_utc':datetime.now(timezone.utc).isoformat(), 'status':'preparing',
            'duration_s':duration_s, 'step_ns':step_ns, 'no_render':no_render,
            'frame_count':0, 'computed_s':0.,
            'contents':'Source camera and telemetry; independent application results may be joined by an observer'}
        atomic_json(self.path / 'scenario.json', scenario)
        atomic_json(self.path / 'manifest.json', self.manifest)

    def camera(self, metadata, jpeg):
        key = metadata['key']
        if not CAMERA_KEY.fullmatch(key):raise ValueError('Invalid camera key')
        with self.lock:
            path = self.path / 'camera' / (key + '.jpg')
            if path.exists():return
            temporary = path.with_suffix('.tmp')
            temporary.write_bytes(jpeg);temporary.replace(path)
            # Metadata is the publication marker; orphan JPEGs are ignored.
            atomic_json(path.with_suffix('.json'), metadata)

    def source_frame(self, producer):
        epoch = producer['sim_time_ns']
        with self.lock:
            path = self.path / 'frames' / (str(epoch) + '.json')
            if path.exists():return
            # Reconstruct rolling histories from these frames during replay,
            # rather than serializing the same growing history thousands of times.
            data = {'producer':{k:v for k,v in producer.items() if k != 'history'}}
            atomic_json(path, data)
            self.manifest.update(frame_count=self.manifest['frame_count']+1,
                origin_ns=producer['origin_ns'],
                computed_s=min(self.manifest['duration_s'], producer['sim_elapsed_s'] + self.manifest['step_ns']/1e9))
            atomic_json(self.path / 'manifest.json', self.manifest)

    def status(self, status, **extra):
        with self.lock:
            self.manifest.update(status=status, **extra)
            atomic_json(self.path / 'manifest.json', self.manifest)
