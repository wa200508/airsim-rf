"""Plot the physical layout and measured/predicted direct-path live Doppler."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def plot(directories, output):
    fig, axes=plt.subplots(3,1,figsize=(9,9),layout='constrained')
    for directory,color,label in zip(directories,['#146da0','#bc4b23'],['Approaching','Receding']):
        report=json.loads((directory/'motion.json').read_text());rows=report['rows']
        t=(np.array([r['sim_time_ns'] for r in rows])-rows[0]['sim_time_ns'])/1e9
        p=np.array([r['tx_position_rf_m'] for r in rows])
        predicted=np.array([r['expected_doppler_hz'] for r in rows])
        measured=np.array([r['measured_doppler_hz'] for r in rows])
        axes[0].plot(p[:,0],p[:,2],color=color,lw=4,label=label+' TX capture segment')
        axes[0].annotate('',xy=p[-1,[0,2]],xytext=p[0,[0,2]],arrowprops={'arrowstyle':'->','color':color,'lw':2})
        axes[1].plot(t,predicted,color=color,label=label+' geometry prediction')
        axes[1].plot(t[::3],measured[::3],'o',ms=4,mfc='none',color=color,label=label+' I/Q estimate')
        axes[2].plot(t,1000*(measured-predicted),color=color,label=label)
    axes[0].plot(20,20,'kv',ms=8,label='Stationary RX')
    axes[0].plot(-20,20,'kx',ms=7,label='TX spawn (before settling)')
    axes[0].axhline(0,color='.4',lw=1)
    axes[0].set(xlim=(-30,25),ylim=(-2,27),xlabel='RF north position (m)',ylabel='Height above ground (m)',
        title='Separate ±3 m/s north commands; capture after 2.001 s of flight')
    axes[0].legend(fontsize=8,loc='lower right')
    axes[0].text(-28,3,'Flat physics ground; RF direct path only\nIsotropic antennas · 915 MHz carrier · 150 kHz CW',fontsize=9)
    axes[1].set(ylabel='Doppler relative to CW (Hz)',title='Forty 12 ms windows per run: 0.480 s of signal at 2 MS/s')
    axes[1].legend(fontsize=8,ncol=2)
    axes[2].set(xlabel='Signal time since first capture (s)',ylabel='Estimate − prediction (mHz)',
        title='Noise disabled; phase fit inside each window; excludes 1 ms at either edge')
    for ax in axes[1:]: ax.grid(alpha=.25)
    output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(output,dpi=170);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('approach',type=Path);parser.add_argument('recede',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();plot([args.approach,args.recede],args.output)
