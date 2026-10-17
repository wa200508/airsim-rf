"""Plot the measured Unreal/RF primitive setup without implying rendered imagery."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np


def plot(directory):
    directory=Path(directory);data=json.loads((directory/'unreal.json').read_text())
    points=np.concatenate([np.array(m['point_cloud']).reshape(-1,3) for m in data['blocked_lidar']])
    points=points*np.array([1,-1,-1])+[0,0,100]
    fig,ax=plt.subplots(figsize=(8,4.6),layout='constrained')
    ax.add_patch(Rectangle((4,-1),2,2,facecolor='#e5e5e5',edgecolor='black',label='Initial cube, z=99–101 m'))
    clear=data['clear_pose']['translation'];center=[clear['x'],-clear['y']]
    ax.add_patch(Rectangle((center[0]-1,center[1]-1),2,2,fill=False,edgecolor='#0072b2',linestyle='--',label='Relocated cube'))
    for y in (-5,5):ax.plot([0,10],[0,10*np.tan(np.radians(y))],color='#009e73',alpha=.6,lw=1)
    ax.plot([0,10],[0,0],color='#d55e00',ls=':',label='RF direct link (blocked initially)')
    ax.scatter(points[:,0],points[:,1],s=10,color='#009e73',label='Received LiDAR surface points',zorder=4)
    ax.scatter([0,10],[0,0],s=70,marker='^',color='black',zorder=5)
    ax.annotate('Probe + RF TX\n(0, 0, 100) m',(0,0),xytext=(-5,20),textcoords='offset points',ha='center')
    ax.annotate('RF RX\n(10, 0, 100) m',(10,0),xytext=(0,20),textcoords='offset points',ha='center')
    ax.annotate('',xy=(5,-2),xytext=(5,-1.1),arrowprops={'arrowstyle':'->','color':'#0072b2'})
    ax.set(xlabel='RF x / north (m)',ylabel='RF y / west (m)',xlim=(-1.8,11.8),ylim=(-4.8,2.1),
        title='Shared cube geometry: measured plan view at z = 100 m')
    ax.set_aspect('equal');ax.grid(alpha=.2);ax.legend(loc='lower left',fontsize=8)
    fig.savefig(directory/'scenario.svg');fig.savefig(directory/'scenario.png',dpi=160);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    plot(parser.parse_args().directory)
