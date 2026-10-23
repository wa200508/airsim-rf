"""Observer-only replay compositor: joins source telemetry and application results.

Neither sample generation nor receiver processing imports this module.
"""
from bisect import bisect_left, bisect_right
from collections import OrderedDict
import importlib.util
import json
from pathlib import Path
import threading

_spec=importlib.util.spec_from_file_location('source_recording',Path(__file__).with_name('source_recording.py'))
_source=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_source)
ID=_source.ID;CAMERA_KEY=_source.CAMERA_KEY;MAX_OFFSET_NS=_source.MAX_OFFSET_NS;atomic_json=_source.atomic_json


def display_result(result):
    """Translate acquisition-clock metadata only at the simulation observer UI."""
    data=dict(result)
    if 'timestamp_ns' in data:data['sim_time_ns']=data.pop('timestamp_ns')
    for key in ('history','waterfall'):
        if key in data:data[key]=[display_result(row) for row in data[key]]
    return data


class RecordingWriter(_source.RecordingWriter):
    """Observer/test convenience for joining already-computed inputs."""
    def frame(self,producer,skill):
        epoch=producer['sim_time_ns']
        if skill.get('timestamp_ns',skill.get('sim_time_ns'))!=epoch:raise ValueError('Recording epochs differ')
        self.source_frame(producer)
        data={k:v for k,v in skill.items() if k not in ('history','waterfall')}
        if 'sim_time_ns' in data:data['timestamp_ns']=data.pop('sim_time_ns')
        atomic_json(self.path/'results'/f'{epoch}.json',data)


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
                if ID.fullmatch(path.parent.name) and value['schema_version'] in (1,2):
                    results.append(value)
            except (OSError, ValueError, KeyError):continue
        return sorted(results, key=lambda item:item['created_utc'], reverse=True)

    def _index(self, identifier):
        path = self.path(identifier)
        manifest = json.loads((path/'manifest.json').read_text())
        if manifest.get('schema_version') not in (1,2):raise ValueError('Unsupported dashboard recording')
        index = self.indices.setdefault(identifier, {'rows':{}, 'cameras':{}, 'revision':None})
        self.indices.move_to_end(identifier)
        if len(self.indices)>3:self.indices.popitem(last=False)
        revision = ((path/'frames').stat().st_mtime_ns, (path/'camera').stat().st_mtime_ns,
            (path/'results').stat().st_mtime_ns if (path/'results').exists() else None)
        if index['revision'] != revision:
            for frame in (path/'frames').glob('*.json'):
                epoch = int(frame.stem)
                if epoch in index['rows']:continue
                value = json.loads(frame.read_text());p=value['producer']
                if 'skill' in value:s=value['skill']  # Immutable version-1 archive.
                else:
                    result=path/'results'/f'{epoch}.json'
                    if not result.exists():continue  # Source/result arrivals are independent.
                    s=display_result(json.loads(result.read_text()))
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
            timeline['frame_count']=max(manifest.get('frame_count',0),len(index['epochs']))
            timeline['computed_s']=min(manifest['duration_s'], max(manifest.get('computed_s',0.),
                max((row['producer']['sim_elapsed_s']+manifest['step_ns']/1e9
                    for row in index['rows'].values()),default=0.)))
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
                if 'skill' not in self.frames[key]:
                    self.frames[key]['skill']=display_result(json.loads((self.path(identifier)/'results'/f'{epoch}.json').read_text()))
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
