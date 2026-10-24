"""Isolated clutter-only I/Q sampling sweep, using the production FMCW source.

No point targets or receiver thermal noise; save both pre-ADC reference and
noise-free quantized ADC output. Every map is computed from 64 rendered chirps,
with moving-platform geometry recomputed at every PRI. Resume completed cases.
"""
import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import platform
import tempfile
import time


def geometries():
    import numpy as np
    cases=[]
    for name,x,z,pos,aim in [
        ('flat-broadside',[-150,150],[0,0],[0,0,60],[0,90,0]),
        ('flat-forward',[-150,150],[0,0],[0,0,60],[100,0,0]),
        ('ridge-shadow',[-150,-40,0,40,150],[0,0,90,0,0],[-90,0,60],[80,0,0]),
    ]:
        vertices=np.array([[xx,yy,zz] for xx,zz in zip(x,z) for yy in [-150,150]],float)
        faces=[]
        for i in range(len(x)-1):
            a=2*i;faces.extend([[a,a+2,a+3],[a,a+3,a+1]])
        doc={'schema_version':1,'scene_id':name,'revision':'1',
             'source':{'adapter':'isolated-clutter-sweep','version':'1','asset':name,'revision':'1','geometry_kind':'shared'},
             'materials':{'earth':{'relative_permittivity':5.,'conductivity_s_m':.01,
                           'assumption':'Illustrative earth material; echo strength uses explicit sigma0, not dielectric inversion.'}},
             'objects':[{'id':'Terrain','material':'earth','vertices_local':(vertices*[1,-1,-1]).tolist(),
                         'faces':faces,'local_to_ned_m':np.eye(4).tolist()}]}
        delta=np.asarray(aim)-pos
        orientation=[float(np.arctan2(delta[1],delta[0])),float(-np.arctan2(delta[2],np.linalg.norm(delta[:2]))),0.]
        cases.append({'name':name,'geometry':doc,'position_m':pos,'velocity_m_s':[20,0,0],
                      'boresight_aim_m':aim,'orientation_rad':orientation})
    return cases


def figures(output,summary):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    records=summary['cases']
    if not records:return
    high=max(r['peak_dbv2'] for r in records);high=float(np.ceil(high/5)*5)
    names=[g['name'] for g in summary['geometries']]
    # Small shared-scene visual: the ridge is a mesh occluder, not a mask on a map.
    fig=plt.figure(figsize=(18,5),layout='constrained')
    for index,spec in enumerate(summary['geometries']):
        ax=fig.add_subplot(1,3,index+1,projection='3d')
        obj=spec['geometry']['objects'][0];xyz=np.asarray(obj['vertices_local'])*[1,-1,-1]
        ax.plot_trisurf(xyz[:,0],xyz[:,1],xyz[:,2],triangles=np.asarray(obj['faces']),color='tan',alpha=.8,edgecolor='saddlebrown')
        pos=np.asarray(spec['position_m']);aim=np.asarray(spec['boresight_aim_m']);delta=aim-pos
        ax.scatter(*pos,c='red',s=40,label='Radar, 60 m')
        ax.quiver(*pos,*delta,color='blue',arrow_length_ratio=.12,label='Antenna boresight')
        ax.quiver(*pos,40,0,0,color='red',arrow_length_ratio=.2,label='Flight +x, 20 m/s')
        ax.set(xlabel='x (m)',ylabel='y (m)',zlabel='Height (m)',title=spec['name'],zlim=(0,110))
        ax.set_box_aspect((3,3,1.4));ax.view_init(elev=23,azim=-65);ax.legend(fontsize=8,loc='upper left')
    fig.savefig(output/'geometries.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for name in names:
        selected=sorted([r for r in records if r['geometry']==name],key=lambda r:r['proposed_samples'])
        if not selected:continue
        budgets=[r['proposed_samples'] for r in selected]
        axes[0].plot(budgets,[20*np.log10(r['gate_rms_v']) for r in selected],'o-',label=name)
        axes[1].plot(budgets,[r['capture_64_chirps_s'] for r in selected],'o-',label=name)
    for ax in axes:ax.set_xscale('log',base=2);ax.set_xlabel('Proposed terrain samples');ax.grid(alpha=.3);ax.legend(fontsize=8)
    axes[0].set_ylabel('Noise-free gate-averaged IF power (dB re 1 V²)')
    axes[0].set_title('One random-phase realization per budget; no ensemble confidence claim')
    axes[1].set(yscale='log',ylabel='CPU seconds / 64-chirp frame',title='One measured capture each; not median/SD or GPU profiling')
    fig.savefig(output/'power-and-runtime.png',dpi=150);plt.close(fig)
    # One global absolute scale: never normalize each map separately. ADC plots
    # retain quantization; pre-ADC maps distinguish physical echoes from it.
    for kind,description,suffix in [('adc','Clutter-only quantized ADC; thermal noise off',''),
                                    ('analog','Noise-free pre-ADC clutter reference','-pre-adc')]:
        for name in names:
            selected=sorted([r for r in records if r['geometry']==name],key=lambda r:r['proposed_samples'])
            if not selected:continue
            fig,axes=plt.subplots(2,5,figsize=(21,9),sharex=True,sharey=True,layout='constrained')
            for ax in axes.flat:ax.set_visible(False)
            for ax,r in zip(axes.flat,selected):
                ax.set_visible(True)
                with np.load(output/r['data_file']) as d:
                    im=ax.pcolormesh(d['doppler_khz'],d['range_m'],d[kind+'_dbv2'],shading='nearest',
                                    cmap='viridis',vmin=high-60,vmax=high,rasterized=True)
                ax.set_title(f"2^{r['exponent']} = {r['proposed_samples']:,} proposed\n{r['retained_first_chirp']:,} retained",fontsize=10)
                ax.set_xlim(-12.5,12.5);ax.set_ylim(0,250);ax.set_xlabel('Doppler (kHz)');ax.set_ylabel('Apparent range (m)');ax.tick_params(labelbottom=True,labelleft=True)
            fig.colorbar(im,ax=list(axes.flat),label='FFT-bin power (dB re 1 V²); common scale',shrink=.8)
            fig.suptitle(name+': '+description+'\n64 chirps / 2.56 ms; range increases upward',fontsize=13)
            fig.savefig(output/(name+suffix+'.png'),dpi=140);fig.savefig(output/(name+suffix+'.svg'));plt.close(fig)
        # Compact beginning/end comparison for reading alongside the report.
        fig,axes=plt.subplots(len(names),2,figsize=(12,12),sharex=True,sharey=True,layout='constrained')
        for row,name in enumerate(names):
            selected=sorted([r for r in records if r['geometry']==name],key=lambda r:r['proposed_samples'])
            if not selected:
                for ax in axes[row]:ax.set_visible(False)
                continue
            for ax,r in zip(axes[row],[selected[0],selected[-1]]):
                with np.load(output/r['data_file']) as d:
                    im=ax.pcolormesh(d['doppler_khz'],d['range_m'],d[kind+'_dbv2'],shading='nearest',vmin=high-60,vmax=high,cmap='viridis',rasterized=True)
                ax.set_title(f"{name}: {r['proposed_samples']:,} proposed / {r['retained_first_chirp']:,} retained")
                ax.set_xlim(-12.5,12.5);ax.set_ylim(0,250);ax.set_xlabel('Doppler (kHz)');ax.set_ylabel('Apparent range (m)');ax.tick_params(labelbottom=True,labelleft=True)
        fig.colorbar(im,ax=list(axes.flat),label='FFT-bin power (dB re 1 V²)',shrink=.75)
        fig.suptitle('Isolated terrain clutter: 1,024 versus highest completed budget\n'+description+'; identical absolute color scale',fontsize=13)
        fig.savefig(output/('comparison'+suffix+'.png'),dpi=150);plt.close(fig)
    summary['plot_limits_dbv2']=[high-60,high]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--exponents',type=int,nargs='+',default=list(range(10,20)))
    p.add_argument('--geometries',nargs='+',default=['flat-broadside','flat-forward','ridge-shadow'])
    p.add_argument('--figures-only',action='store_true')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    summary_path=args.output/'summary.json'
    if args.figures_only:
        summary=json.loads(summary_path.read_text());figures(args.output,summary)
        summary_path.write_text(json.dumps(summary,indent=2)+'\n');return
    if any(e<10 or e>19 for e in args.exponents):p.error('Exponents must be 10 through 19 (powers of two within 10^3..10^6)')
    import numpy as np
    import mitsuba as mi
    mi.set_variant('llvm_ad_mono_polarized')
    import drjit as dr
    dr.set_thread_count(2)
    import sionna.rt as rt
    from airsim_rf.geometry import export_sionna_geometry
    from airsim_rf.fmcw import FMCWRadar,IWR1843Profile
    from radar_skill.processing import range_doppler
    profile=replace(IWR1843Profile(),noise_enabled=False)
    acquisition={k:getattr(profile,k) for k in ('pri_s','adc_start_s','num_samples','bandwidth_hz','chirp_duration_s')}
    source_names=['airsim_rf.fmcw','airsim_rf.radar_scattering','radar_skill.processing']
    hashes={n:sha256(Path(__import__(n,fromlist=['x']).__file__).read_bytes()).hexdigest() for n in source_names}
    specs=geometries()
    summary={'scope':'isolated first-order terrain clutter-only, CPU; production source and external radar FFT',
             'profile':asdict(profile),'acquisition':acquisition,'seed':314159,'sigma0_db':-20.,'incidence_exponent':1.,
             'chirps':64,'CPI_s':64*profile.pri_s,'max_range_m':250.,'source_sha256':hashes,
             'hardware':{'cpu':next(l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),
                         'cpu_quota':Path('/sys/fs/cgroup/cpu.max').read_text().strip(),'drjit_threads':dr.thread_count(),'platform':platform.platform()},
             'software':{'numpy':np.__version__,'mitsuba':mi.__version__,'sionna_rt':rt.__version__},
             'geometries':specs,'cases':[]}
    if summary_path.exists():
        old=json.loads(summary_path.read_text())
        for key in ['profile','acquisition','seed','sigma0_db','incidence_exponent','chirps','CPI_s','max_range_m','source_sha256','geometries']:
            if old[key]!=summary[key]:raise ValueError('Refuse to mix differing sweep inputs: '+key)
        summary['cases']=old['cases']
    done={(r['geometry'],r['exponent']) for r in summary['cases']}
    with tempfile.TemporaryDirectory(prefix='clutter-sweep-') as td:
        for spec in specs:
            if spec['name'] not in args.geometries:continue
            bundle=Path(td)/spec['name'];export_sionna_geometry(spec['geometry'],bundle)
            scene=rt.load_scene(str(bundle/'scene.xml'),merge_shapes=False)
            clutter={'enabled':True,'seed':summary['seed'],'materials':{'earth':{'sigma0_db':-20.,'incidence_exponent':1.}},'shape_materials':{'obj_Terrain':'earth'}}
            for exponent in args.exponents:
                if (spec['name'],exponent) in done:continue
                count=2**exponent
                radar=FMCWRadar(profile,rf_scene=scene,max_range_m=250.,clutter=clutter,samples_per_link=count)
                tick=time.perf_counter();radar.clutter.prepare();prepare_s=time.perf_counter()-tick
                stride=round(profile.pri_s*profile.sample_rate_hz);start=round(profile.adc_start_s*profile.sample_rate_hz)
                analog=np.zeros(64*stride,np.complex64);adc=analog.copy();retained=[];clipped=0
                tick=time.perf_counter()
                for i in range(64):
                    cap=radar.capture([],position_m=np.asarray(spec['position_m'])+np.asarray(spec['velocity_m_s'])*i*profile.pri_s,
                                      velocity_m_s=spec['velocity_m_s'],orientation_rad=spec['orientation_rad'],sim_time_ns=round(i*profile.pri_s*1e9))
                    sl=slice(i*stride+start,i*stride+start+profile.num_samples)
                    analog[sl]=cap.if_volts;adc[sl]=cap.adc_iq_volts;clipped+=cap.clipped_components
                    retained.append(radar.last_render_diagnostics['clutter_echoes'])
                capture_s=time.perf_counter()-tick
                tick=time.perf_counter();rd=range_doppler(analog,profile.sample_rate_hz,profile.carrier_hz,acquisition)
                rd_adc=range_doppler(adc,profile.sample_rate_hz,profile.carrier_hz,acquisition);fft_s=time.perf_counter()-tick
                power=np.asarray(rd['power_db'])+rd['median_bin_power_dbv2'];power_adc=np.asarray(rd_adc['power_db'])+rd_adc['median_bin_power_dbv2']
                filename=f"{spec['name']}-2p{exponent}.npz"
                np.savez_compressed(args.output/filename,analog_iq_volts=analog,adc_iq_volts=adc,
                                    analog_dbv2=power,adc_dbv2=power_adc,range_m=rd['range_m'],doppler_khz=rd['doppler_khz'])
                rms=float(np.sqrt(np.mean(abs(analog.reshape(64,stride)[:,start:start+profile.num_samples])**2)))
                record={'geometry':spec['name'],'exponent':exponent,'proposed_samples':count,
                        'retained_first_chirp':retained[0],'retained_min':min(retained),'retained_max':max(retained),
                        'surface_area_m2':radar.clutter.total_area_m2,'raw_RCS_sum_m2':float(radar.clutter.rcs.sum()),
                        'first_prepare_s':prepare_s,'capture_64_chirps_s':capture_s,'two_FFTs_s':fft_s,
                        'peak_dbv2':float(power.max()),'gate_rms_v':rms,'clipped_components':clipped,
                        'last_chirp_clutter_diagnostics':radar.last_clutter_diagnostics,'data_file':filename}
                summary['cases'].append(record);summary_path.write_text(json.dumps(summary,indent=2)+'\n')
                print(json.dumps(record),flush=True)
    figures(args.output,summary);summary_path.write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':main()
