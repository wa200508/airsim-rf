"""Application results journal. Contains no acquisition-source or truth knowledge."""
import json
from pathlib import Path


class ResultWriter:
    def __init__(self,directory):
        self.path=Path(directory);self.path.mkdir(parents=True,exist_ok=True)

    def write(self,result):
        epoch=result['timestamp_ns']
        if isinstance(epoch,bool) or not isinstance(epoch,int):raise ValueError('Integer acquisition timestamp required')
        data={k:v for k,v in result.items() if k not in ('history','waterfall','updated_monotonic')}
        path=self.path/f'{epoch}.json';temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data,allow_nan=False)+'\n');temporary.replace(path)
