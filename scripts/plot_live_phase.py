"""Regenerate the live cadence/phase qualification figure from published JSON."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def plot(directory):
    reports={p.parent.name:json.loads(p.read_text()) for p in directory.glob('*/phase.json')}
    fig,axes=plt.subplots(3,1,figsize=(8.5,9),layout='constrained')
    direct=[reports[f'direct-{n}'] for n in (6,12,24,48)]
    specular=[reports[f'specular-{n}'] for n in (12,24,48)]
    for cases,path_index,color,label in [(direct,0,'#146da0','Direct path'),(specular,1,'#bc4b23','Ground-reflected path')]:
        x=[r['window_ms'] for r in cases]
        y=[1000*max(abs(b['path_refresh_jump_rad'][path_index]) for b in r['boundaries']) for r in cases]
        axes[0].plot(x,y,'o-',color=color,label=label)
    axes[0].set(xlabel='Channel update interval (ms)',ylabel='Maximum phase adjustment (mrad)',
        title='Refresh corrections grow as the constant-velocity window grows')
    axes[0].legend()
    r=reports['direct-12'];b=r['boundaries'];t=(np.array([v['sim_time_ns'] for v in b])-b[0]['sim_time_ns'])/1e9+.012
    axes[1].plot(t,[1000*v['geometry_refresh_jump_rad'][0] for v in b],label='Position/velocity prediction',color='#146da0')
    axes[1].plot(t,[1000*v['adc_fitted_jump_rad'] for v in b],'o',mfc='none',ms=4,label='I/Q phase fits',color='#bc4b23')
    axes[1].set(xlabel='Signal time since capture start (s)',ylabel='Direct-path adjustment (mrad)',
        title='12 ms direct-path run: the new pose corrects the preceding prediction')
    axes[1].legend()
    for cases,color,label in [(direct,'#146da0','Direct'),(specular,'#bc4b23','Direct + ground')]:
        x=[r['window_ms'] for r in cases]
        axes[2].plot(x,[100*r['metrics']['whole_recording_iq_nrmse'] for r in cases],'o-',color=color,label=label+', whole record')
        axes[2].plot(x,[100*r['metrics']['boundary_neighborhood_iq_nrmse'] for r in cases],'s--',color=color,label=label+', boundary neighborhoods')
    axes[2].set(xlabel='Channel update interval (ms)',ylabel='I/Q normalized RMS error (%)',
        title='ADC output versus analytic CW sum and one continuous receive filter')
    axes[2].legend(fontsize=8,ncol=2)
    for ax in axes:ax.grid(alpha=.25)
    fig.savefig(directory/'phase-cadence.png',dpi=170);plt.close(fig)
    trajectory=json.loads((directory/'specular-12/trajectory.json').read_text())
    def position(entry):
        p=entry['kinematics']['pose']['position'];return np.array([p['x'],-p['z']])
    tx,rx=map(position,trajectory[:2]);bounce=np.array([(tx[0]*rx[1]+rx[0]*tx[1])/(tx[1]+rx[1]),0.])
    fig,ax=plt.subplots(figsize=(8.5,4.5),layout='constrained')
    ax.plot([tx[0],rx[0]],[tx[1],rx[1]],color='#146da0',label='Direct path')
    ray=np.array([tx,bounce,rx]);ax.plot(ray[:,0],ray[:,1],color='#bc4b23',label='Specular ground path')
    ax.plot(*tx,'o',color='#146da0',ms=8);ax.plot(*rx,'kv',ms=8)
    ax.annotate('Moving TX',xy=tx,xytext=tx+[-3,4])
    ax.annotate('Fixed RX',xy=rx,xytext=rx+[-3,4])
    ax.annotate('',xy=tx+[6,1.5],xytext=tx+[0,1.5],arrowprops={'arrowstyle':'->','color':'#146da0'})
    ax.axhline(0,color='.4');ax.text(-24,1,'Flat ground',color='.3')
    ax.set(xlim=(-27,28),ylim=(-2,30),xlabel='RF north position (m)',ylabel='Height (m)',
        title='First approaching snapshot: two RF paths, one moving transmitter')
    ax.set_aspect('equal');ax.legend(loc='center left',fontsize=9)
    fig.savefig(directory/'phase-scenario.png',dpi=170);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    plot(parser.parse_args().directory)
