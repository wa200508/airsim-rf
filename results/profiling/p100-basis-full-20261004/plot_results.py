from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
b=Path('/work/results')
tx=[1,4,100]
data={backend:[json.loads((b/'profiles'/f'basis_{backend}_{n}tx_1rx.json').read_text()) for n in tx] for backend in ('cpu','cuda')}
fig,ax=plt.subplots(figsize=(8,5))
x=np.arange(3)
for shift,backend,color in [(-.18,'cpu','gray'),(.18,'cuda','tab:blue')]:
    values=[d['summary']['p50_ms'] for d in data[backend]]
    bars=ax.bar(x+shift,values,.36,label=backend.upper(),color=color)
    ax.bar_label(bars,labels=[f'{v:.2f}' for v in values],padding=3,fontsize=10)
ax.axhline(1000/120,color='red',linestyle='--',label='120 Hz deadline (8.33 ms)')
ax.set(yscale='log',ylim=(3,4000),xticks=x,xticklabels=['1 TX','4 TX','100 TX'],ylabel='Median synchronized renderer latency (ms)',xlabel='Independent TX / 1 RX')
ax.legend(loc='upper left')
ax.set_title('P100 Doppler-basis FFT rendering\nAccuracy suite failed; timings are diagnostic',fontsize=13)
fig.text(.5,.01,'30 windows per case · 1,028 paths/link · 16,667 outputs · FP64/complex128',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.04,1,1))
fig.savefig(b/'renderer_timings.png',dpi=180)
