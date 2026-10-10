"""Check gallery provenance and explicitly classified undefined measurements."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np


def check(data_dir, output_dir):
    for name in ('sensing_products.json','sensing_scenarios.json'):
        manifest=json.loads((output_dir/name).read_text())
        for source,digest in manifest['source_sha256'].items():
            if sha256((data_dir/source).read_bytes()).hexdigest()!=digest:
                raise ValueError(f'{name}: stale source {source}')
        for figure in manifest['figures']:
            for extension in ('svg','png'):
                if not (output_dir/f'{figure}.{extension}').is_file():
                    raise ValueError(f'Missing figure {figure}.{extension}')
    manifest=json.loads((output_dir/'sensing_products.json').read_text())
    with np.load(output_dir/'sensing_products.npz',allow_pickle=False) as products:
        for key in products.files:
            values=products[key]
            prefix='weak_line_prominence_'
            if not key.startswith(prefix):
                if not np.isfinite(values).all():
                    raise ValueError(f'Unexpected nonfinite array {key}')
                continue
            receiver,label=key[len(prefix):].split('_',1)
            states=manifest['line_prominence_status'][int(receiver)][label.replace('_',' ')]
            if len(states)!=len(values):
                raise ValueError(f'Status length differs for {key}')
            for value,state in zip(values,states):
                if np.isnan(value) and state in ('all_samples_zero','undefined_peak_or_floor'):
                    continue
                if np.isfinite(value) and state=='valid':
                    continue
                raise ValueError(f'Unexplained value/status in {key}')
        raw=np.load(data_dir/'pluto_esm_iq.npz',allow_pickle=False)
        for ri in range(2):
            fraction=np.count_nonzero(raw['adc8_control_iq_volts'][:,ri],axis=-1)/raw['adc8_control_iq_volts'].shape[-1]
            np.testing.assert_array_equal(products[f'adc8_nonzero_fraction_{ri}'],fraction)
            states=manifest['line_prominence_status'][ri]['8-bit control']
            if any((f==0)!=(state=='all_samples_zero') for f,state in zip(fraction,states)):
                raise ValueError('Zero-code status disagrees with raw captures')
    print('Gallery source hashes, figure files and undefined-metric states agree.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=Path('docs/figures'))
    parser.add_argument('--output-dir',type=Path,default=Path('docs/figures'))
    args=parser.parse_args()
    check(args.data_dir,args.output_dir)


if __name__=='__main__':
    main()
