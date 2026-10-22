"""Validate SDR recording counts/timestamps and summarize the observed spectrum."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
from scipy.signal import welch


def inspect(directory):
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_text());rows=manifest['rows'];fs=manifest['sample_rate_hz']
    if manifest['status']!='complete' or not rows:
        raise ValueError('A complete nonempty recording is required for qualification')
    starts=np.array([r['sim_time_ns'] for r in rows],dtype=np.int64)
    counts=np.array([r['samples_per_receiver'] for r in rows],dtype=np.int64)
    if not np.array_equal(np.diff(starts),np.rint(counts[:-1]*1e9/fs).astype(np.int64)):
        raise ValueError('Simulation timestamps are not sample-contiguous')
    offsets=np.r_[0,np.cumsum(counts)[:-1]];receivers={}
    for path in directory.glob('*.sigmf-meta'):
        metadata=json.loads(path.read_text());captures=metadata['captures']
        if metadata['global']['core:datatype']!='ci16_le' or metadata['global']['core:sample_rate']!=fs:
            raise ValueError('Unexpected recording format or rate')
        if [c['core:sample_start'] for c in captures]!=offsets.tolist() or [c['airsim_rf:sim_time_ns'] for c in captures]!=starts.tolist():
            raise ValueError('Capture metadata offsets/timestamps disagree with manifest')
        data_path=path.with_suffix('.sigmf-data')
        if data_path.stat().st_size!=4*sum(counts):
            raise ValueError('ADC count or signed 12-bit range is invalid')
        digest=sha256();minimum=2047;maximum=-2048;nonzero=0
        with data_path.open('rb') as stream:
            for count in counts:
                values=np.fromfile(stream,dtype='<i2',count=2*int(count))
                if len(values)!=2*count or values.min() < -2048 or values.max()>2047:
                    raise ValueError('ADC count or signed 12-bit range is invalid')
                digest.update(values.tobytes())
                minimum=min(minimum,int(values.min()));maximum=max(maximum,int(values.max()))
                iq=values.reshape(-1,2)
                nonzero+=int(np.count_nonzero(np.any(iq!=0,axis=1)))
        complex_codes=iq[:,0].astype(float)+1j*iq[:,1]
        frequency,psd=welch(complex_codes[-int(counts[-1]):],fs=fs,nperseg=min(4096,int(counts[-1])),
            return_onesided=False,detrend=False)
        receivers[path.stem]={'complex_samples':int(sum(counts)),'data_bytes':int(4*sum(counts)),
            'data_sha256':digest.hexdigest(),
            'adc_component_min':minimum,'adc_component_max':maximum,
            'nonzero_complex_sample_fraction':float(nonzero/sum(counts)),
            'final_window_peak_baseband_hz':float(frequency[np.argmax(psd)]),
            'frequency_bin_spacing_hz':float(fs/min(4096,int(counts[-1])))}
    if not receivers:
        raise ValueError('No receiver recording found')
    return {'status':'passed','scope':'recording structure, sample continuity, code range and spectral summary',
        'server_motion_or_physical_accuracy_qualified':False,'updates':len(rows),'sample_rate_hz':fs,
        'signal_seconds_per_receiver':float(sum(counts)/fs),'samples_per_update':counts.tolist(),
        'wall_seconds_per_signal_second':manifest['wall_seconds_per_signal_second'],'receivers':receivers}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();report=inspect(args.directory);text=json.dumps(report,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text)
    print(text)


if __name__=='__main__':
    main()
