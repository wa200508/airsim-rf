"""Physical plan view and signed Doppler for the two-drone qualification."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def plot(directory):
    motion=json.loads((directory/'direct-12/motion.json').read_text())['rows']
    channels=json.loads((directory/'specular-12/channels.json').read_text())
    t=(np.array([r['sim_time_ns'] for r in motion])-motion[0]['sim_time_ns'])/1e9
    fig,axes=plt.subplots(2,1,figsize=(9,6),layout='constrained')
    for radio,color in [('tx','#146da0'),('rx','#bc4b23')]:
        p=np.array([r[radio+'_position_rf_m'] for r in motion])
        axes[0].plot(p[:,0],p[:,1],color=color,lw=3,label=radio.upper()+' capture trajectory')
        axes[0].annotate('',xy=p[-1,:2],xytext=p[0,:2],arrowprops={'arrowstyle':'->','color':color,'lw':2})
    first=motion[0];tx=np.array(first['tx_position_rf_m']);rx=np.array(first['rx_position_rf_m'])
    axes[0].plot([tx[0],rx[0]],[tx[1],rx[1]],':',color='.5',label='Initial direct path')
    axes[0].set(xlabel='RF north position (m)',ylabel='RF west position (m)',ylim=(-5,5),xlim=(-22,22),
        title='Plan view: TX north; RX south and east; both use Fast Physics')
    axes[0].set_aspect('equal');axes[0].legend(loc='upper center',fontsize=8,ncol=3)
    axes[1].plot(t,[r['expected_doppler_hz'] for r in motion],color='#146da0',label='Direct geometry prediction')
    axes[1].plot(t[::3],[r['measured_doppler_hz'] for r in motion][::3],'o',mfc='none',color='#146da0',ms=4,label='Direct-only I/Q estimate')
    reflected=[np.array(c['doppler_hz'])[np.argsort(c['delay_s'])][1] for c in channels]
    axes[1].plot(t,reflected,color='#bc4b23',label='Ground path (geometry checked)')
    axes[1].set(xlabel='Signal time since capture start (s)',ylabel='Path Doppler (Hz)',
        title='12 ms channel updates; 0.480 s recorded per run; 915 MHz carrier')
    axes[1].grid(alpha=.25);axes[1].legend(fontsize=9)
    fig.savefig(directory/'moving-receiver.png',dpi=170);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    plot(parser.parse_args().directory)
