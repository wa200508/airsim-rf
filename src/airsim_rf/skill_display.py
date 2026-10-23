"""Observer-only RF display bindings and legacy-recording migration.

Current skills own their descriptions. Frozen legacy descriptions are only for
old recordings that predate the display contract; live skills are never guessed.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re
from pathlib import Path


def pointer(value,path,variables=None):
    if path=='':return value
    if not isinstance(path,str) or not path.startswith('/'):return None
    for key in path[1:].split('/'):
        for name,replacement in (variables or {}).items():key=key.replace('{'+name+'}',str(replacement))
        key=key.replace('~1','/').replace('~0','~')
        if isinstance(value,dict):value=value.get(key)
        elif isinstance(value,list) and key.isdigit() and int(key)<len(value):value=value[int(key)]
        else:return None
    return value


def binding(frame,spec):
    if not isinstance(spec,dict):return None
    if 'value' in spec:return deepcopy(spec['value'])
    value=pointer(frame,spec.get('path'))
    if 'each' in spec:
        return [pointer(row,spec['each'],{'index':index}) for index,row in enumerate(value)] if isinstance(value,list) else []
    return deepcopy(value)


def history_specs(description):
    """Accept bounded projections without allowing metadata to be overwritten."""
    if not isinstance(description,dict) or description.get('schema_version')!=1:return []
    entries=description.get('histories',[])
    if not isinstance(entries,list):return []
    reserved={'display','timestamp_ns','sim_time_ns','carrier_hz','sample_rate_hz'}
    accepted=[]
    for spec in entries[:16]:
        if not isinstance(spec,dict):continue
        key=spec.get('key');limit=spec.get('limit',60)
        if not isinstance(key,str) or not re.fullmatch(r'[a-z][a-z0-9_]*',key) or key in reserved:continue
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=1000:continue
        if not isinstance(spec.get('row'),dict):continue
        accepted.append({**spec,'limit':limit})
    return accepted


def history_summaries(frame):
    description=frame.get('display')
    if not isinstance(description,dict) or description.get('schema_version')!=1:return None,{}
    signature=sha256(json.dumps(description,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    summaries={}
    for spec in history_specs(description):
        summaries[spec['key']]={key:binding(frame,value) for key,value in spec['row'].items()}
    return signature,summaries


def legacy_display(frame,scenario):
    """Upgrade an old saved result, preserving genuinely missing receiver data."""
    if 'display' in frame:return frame
    kind=scenario.get('skill_kind')
    filename={'direction-finding':'legacy-display-df.json','music':'legacy-display-df.json','radar':'legacy-display-radar.json'}.get(kind)
    if filename is None:return frame
    result=deepcopy(frame)
    result['display']=json.loads((Path(__file__).with_name('assets')/filename).read_text())
    if not result.get('receiver_spectra') and result.get('psd'):
        result['receiver_spectra']=[{'site_id':'Site 0','psd':result['psd']}]
    for row in result.get('waterfall',[]):
        if not row.get('site_psd_db') and row.get('psd_db'):row['site_psd_db']=[row['psd_db']]
    return result
