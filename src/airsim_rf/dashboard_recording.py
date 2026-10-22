"""Durable dashboard frames and stdlib-only replay; independent of browser polling."""
from bisect import bisect_left, bisect_right
from collections import OrderedDict
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
    def __init__(self, root, identifier, scenario, duration_s, step_ns, *, no_render=False):
        if not ID.fullmatch(identifier):raise ValueError('Invalid recording ID')
        self.path = Path(root) / identifier
        self.path.mkdir(parents=True, exist_ok=False)
        for name in ('frames', 'camera'):(self.path / name).mkdir()
        self.lock = threading.RLock()
        self.manifest = {'schema_version':1, 'id':identifier,
            'created_utc':datetime.now(timezone.utc).isoformat(), 'status':'preparing',
            'duration_s':duration_s, 'step_ns':step_ns, 'no_render':no_render,
            'frame_count':0, 'computed_s':0.,
            'contents':'Camera, telemetry and RF diagnostics; raw ADC samples are not stored'}
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

    def frame(self, producer, skill):
        epoch = producer['sim_time_ns']
        if skill.get('sim_time_ns') != epoch:raise ValueError('Recording epochs differ')
        with self.lock:
            path = self.path / 'frames' / (str(epoch) + '.json')
            if path.exists():return
            # Reconstruct rolling histories from these frames during replay,
            # rather than serializing the same growing history thousands of times.
            data = {'producer':{k:v for k,v in producer.items() if k != 'history'},
                'skill':{k:v for k,v in skill.items() if k not in ('history','waterfall')}}
            atomic_json(path, data)
            self.manifest.update(frame_count=self.manifest['frame_count']+1,
                origin_ns=producer['origin_ns'],
                computed_s=min(self.manifest['duration_s'], producer['sim_elapsed_s'] + self.manifest['step_ns']/1e9))
            atomic_json(self.path / 'manifest.json', self.manifest)

    def status(self, status, **extra):
        with self.lock:
            self.manifest.update(status=status, **extra)
            atomic_json(self.path / 'manifest.json', self.manifest)


class RecordingStore:
    """Index small frame summaries; keep only a bounded cache of full spectra."""
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.indices = OrderedDict()
        self.frames = OrderedDict()

    def path(self, identifier):
        if not ID.fullmatch(identifier):raise ValueError('Invalid recording ID')
        return self.root / identifier

    def list(self):
        results = []
        for path in self.root.glob('*/manifest.json'):
            try:
                value = json.loads(path.read_text())
                if ID.fullmatch(path.parent.name) and value['schema_version']==1:
                    results.append(value)
            except (OSError, ValueError, KeyError):continue
        return sorted(results, key=lambda item:item['created_utc'], reverse=True)

    def _index(self, identifier):
        path = self.path(identifier)
        manifest = json.loads((path/'manifest.json').read_text())
        if manifest.get('schema_version')!=1:raise ValueError('Unsupported dashboard recording')
        index = self.indices.setdefault(identifier, {'rows':{}, 'cameras':{}, 'revision':None})
        self.indices.move_to_end(identifier)
        if len(self.indices)>3:self.indices.popitem(last=False)
        revision = ((path/'frames').stat().st_mtime_ns, (path/'camera').stat().st_mtime_ns)
        if index['revision'] != revision:
            for frame in (path/'frames').glob('*.json'):
                epoch = int(frame.stem)
                if epoch in index['rows']:continue
                value = json.loads(frame.read_text());p=value['producer'];s=value['skill']
                if p['sim_time_ns']!=epoch or s['sim_time_ns']!=epoch:raise ValueError('Corrupt recording epoch')
                index['rows'][epoch]={'producer':{k:p[k] for k in ('sim_time_ns','origin_ns','sim_elapsed_s','position_rf_m','geometry_sha256') if k in p},
                    'history':{'sim_time_ns':epoch,
                        'angles_deg':[b['angle_deg'] if b['detected'] else None for b in s.get('bearings',[])],
                        'detected':[b['detected'] for b in s.get('bearings',[])],
                        'payload_bytes':s.get('payload_bytes',0),'sample_start':s.get('sample_start',0)},
                    'waterfall':{'sim_time_ns':epoch,'psd_db':s.get('psd',{}).get('density_db_v2_hz',[])}}
            for camera in (path/'camera').glob('*.json'):
                if camera.stem not in index['cameras']:
                    value=json.loads(camera.read_text())
                    if CAMERA_KEY.fullmatch(camera.stem) and camera.with_suffix('.jpg').is_file():
                        index['cameras'][camera.stem]=value
            epochs=sorted(index['rows']);cameras=sorted(index['cameras'].values(),key=lambda c:c['sim_time_ns'])
            camera_times=[c['sim_time_ns'] for c in cameras];pairs=[]
            for epoch in epochs:
                p=index['rows'][epoch]['producer']
                if manifest['no_render']:pairs.append((epoch,None));continue
                near=cameras[bisect_left(camera_times,epoch-MAX_OFFSET_NS):bisect_right(camera_times,epoch+MAX_OFFSET_NS)]
                near=[c for c in near if c.get('geometry_sha256')==p.get('geometry_sha256')]
                if near:
                    camera=min(near,key=lambda c:abs(c['sim_time_ns']-epoch))
                    if abs(camera['sim_time_ns']-epoch)<=MAX_OFFSET_NS:pairs.append((epoch,camera))
            index.update(revision=revision,epochs=epochs,pairs=pairs,
                pair_epochs=[epoch for epoch,_ in pairs],
                times=[index['rows'][epoch]['producer']['sim_elapsed_s'] for epoch,_ in pairs])
        index['manifest']=manifest
        return index

    def snapshot(self, identifier, time_s=None):
        with self.lock:
            index=self._index(identifier);manifest=index['manifest'];pairs=index['pairs'];times=index['times']
            timeline={**manifest,'playable_frames':len(pairs),'start_s':times[0] if times else 0.,
                'end_s':times[-1] if times else 0.}
            # A killed writer may have published its final frame just before
            # updating the manifest. Published frame files are authoritative.
            timeline['frame_count']=len(index['epochs'])
            timeline['computed_s']=min(manifest['duration_s'], max((row['producer']['sim_elapsed_s']+
                manifest['step_ns']/1e9 for row in index['rows'].values()),default=0.))
            base={'producer':{},'skill':{},'transport':{},'camera':{'available':False},
                'synchronization':{'status':'waiting'},'no_render':manifest['no_render'],
                'scenario':json.loads((self.path(identifier)/'scenario.json').read_text()),'playback':timeline}
            if not pairs:return base
            origin=manifest.get('origin_ns',index['rows'][pairs[0][0]]['producer'].get('origin_ns',0))
            # Seek using integer epochs: e.g. 0.24 must select a frame whose
            # floating T+ happens to serialize as 0.24000000000000002.
            at=len(pairs)-1 if time_s is None else max(0,min(len(pairs)-1,
                bisect_right(index['pair_epochs'],origin+round(time_s*1e9))-1))
            epoch,camera=pairs[at];key=(identifier,epoch)
            if key not in self.frames:
                self.frames[key]=json.loads((self.path(identifier)/'frames'/f'{epoch}.json').read_text())
                if len(self.frames)>32:self.frames.popitem(last=False)
            self.frames.move_to_end(key);value=self.frames[key]
            end=bisect_right(index['epochs'],epoch);history=index['epochs'][max(0,end-1000):end]
            producer={**value['producer'],'history':[index['rows'][e]['producer'] for e in history]}
            skill={**value['skill'],'history':[index['rows'][e]['history'] for e in history],
                'waterfall':[index['rows'][e]['waterfall'] for e in index['epochs'][max(0,end-60):end]]}
            timeline.update(frame_time_s=times[at],frame_index=at)
            base.update(producer=producer,skill=skill,transport=skill,
                synchronization={'status':'matched','rf_sim_time_ns':epoch,'latest_rf_sim_time_ns':pairs[-1][0],
                    'camera_sim_time_ns':None if camera is None else camera['sim_time_ns'],
                    'offset_ms':None if camera is None else (camera['sim_time_ns']-epoch)/1e6})
            if camera is not None:
                base['camera']={'available':True,'age_s':0.,'url':f'/camera.jpg?recording={identifier}&frame={camera["key"]}',
                    'source':'Recorded ProjectAirSim Chase scene_camera'}
            return base
