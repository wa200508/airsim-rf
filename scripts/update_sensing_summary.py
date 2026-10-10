"""Derive displayed capture/height scalars from the canonical recorded sources."""
import argparse
import json
from pathlib import Path
import re

import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def update(*, check=False):
    data=ROOT/'docs/figures';page=ROOT/'docs/sensing-plots.md'
    radio=json.loads((data/'pluto_esm_report.json').read_text())
    products=json.loads((data/'sensing_products.json').read_text())
    terrain=json.loads((data/'terrain_signature_data.json').read_text())
    lines=[f"Final capture epoch: **{radio['epochs_s'][-1]:g} s**. Link powers precede receiver noise.",
        '', '| Receiver | Beacon A (dBm) | Beacon B (dBm) | Noise (dBm) | All-zero 8-bit captures |',
        '| --- | ---: | ---: | ---: | ---: |']
    for i,receiver in enumerate(radio['records'][-1]['receivers']):
        powers=receiver['link_power_dbm'];states=products['line_prominence_status'][i]['8-bit control']
        lines.append(f"| Receiver {i+1} | {powers['beacon_a']:.2f} | {powers['beacon_b']:.2f} | {receiver['thermal_noise_power_dbm']:.2f} | {states.count('all_samples_zero')}/{len(states)} |")
    error=np.asarray(terrain['iq_peak_height_dem_m'])-terrain['dem_height_reference_m']
    radar=np.load(data/'terrain_scan_iq.npz',allow_pickle=False);worst=int(np.argmax(abs(error)))
    height=f"Route RMSE **{np.sqrt(np.mean(error**2)):.3f} m**; mean signed error **{error.mean():+.3f} m**; maximum absolute error **{abs(error[worst]):.3f} m** at route distance **{radar['distance_m'][worst]:.1f} m**."
    text=page.read_text()
    for marker,body in [('CAPTURE SUMMARY','\n'.join(lines)),('RADAR QUALITY',height)]:
        block=f'<!-- BEGIN {marker} -->\n\n{body}\n\n<!-- END {marker} -->'
        pattern=rf'<!-- BEGIN {marker} -->.*?<!-- END {marker} -->'
        if not re.search(pattern,text,flags=re.S):
            raise ValueError(f'Missing documentation block {marker}')
        text=re.sub(pattern,lambda m:block,text,flags=re.S)
    if text!=page.read_text():
        if check:
            raise ValueError('Stale sensing summary; run scripts/update_sensing_summary.py')
        page.write_text(text)
    print('Sensing capture/height summary agrees with recorded data.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    update(check=parser.parse_args().check)
