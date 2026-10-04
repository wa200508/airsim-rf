"""Legacy Sionna simultaneous-TX propagation only; no waveforms or receiver DSP."""
import argparse,json,time,os,resource,traceback
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--tx',type=int,required=True);p.add_argument('--rays-per-tx',type=int,default=1028);p.add_argument('--iterations',type=int,default=3);p.add_argument('--warmup',type=int,default=1);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
result={'arguments':vars(args).copy(),'status':'starting','measurement':'simultaneous native legacy propagation; no signal rendering, no IQ, no ADC; not transmitter batches','epochs':[]}
result['arguments']['output']=str(args.output)
def save():
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
def stage(name):
    result['stage']=name;save();print(name,flush=True)
save();start=time.perf_counter()
try:
    stage('imports')
    import numpy as np
    import tensorflow as tf
    import drjit as dr
    import mitsuba as mi
    import sionna
    import sionna.rt as rt
    dr.set_thread_count(2);mi.set_variant('cuda_ad_rgb')
    result['versions']={'sionna':sionna.__version__,'mitsuba':mi.__version__,'drjit':dr.__version__,'tensorflow':tf.__version__,'backend':mi.variant()}
    result['host']={'cpu_count':os.cpu_count(),'cpu_quota':Path('/sys/fs/cgroup/cpu.max').read_text().strip(),'memory_limit':Path('/sys/fs/cgroup/memory.max').read_text().strip()}
    result['ray_count']=args.tx*args.rays_per_tx
    result['import_s']=time.perf_counter()-start
    stage('scene_setup')
    setup=time.perf_counter()
    import re
    original=Path('/opt/airsim-rf/benchmarks/scenes/terrain.xml')
    xml=re.sub(r'<bsdf.*?</bsdf>','<bsdf type="diffuse" id="legacy_ground"/>',original.read_text(),flags=re.S)
    xml=xml.replace('ground-material','legacy_ground').replace('value="terrain.ply"','value="/opt/airsim-rf/benchmarks/scenes/terrain.ply"')
    Path('/tmp/scaling-terrain.xml').write_text(xml)
    scene=rt.load_scene('/tmp/scaling-terrain.xml');scene.frequency=915e6
    mat=scene.radio_materials['legacy_ground'];mat.frequency_update_callback=None;mat.relative_permittivity=5.;mat.conductivity=.01;mat.scattering_coefficient=.3;mat.is_placeholder=False
    scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,vertical_spacing=.5,horizontal_spacing=.5,pattern='hw_dipole',polarization='V')
    scene.rx_array=rt.PlanarArray(num_rows=1,num_cols=1,vertical_spacing=.5,horizontal_spacing=.5,pattern='hw_dipole',polarization='V')
    scene.synthetic_array=True
    with tf.device('/CPU:0'):
        scene.add(rt.Receiver('rx',position=[-30,-10,14]))
        for i,y in enumerate(np.linspace(-25,25,args.tx)):
            scene.add(rt.Transmitter(f'tx_{i}',position=[0,float(y),10]))
            if (i+1)%10000==0:
                result['created_transmitters']=i+1;result['setup_elapsed_s']=time.perf_counter()-setup;save();print(f'created {i+1}/{args.tx}',flush=True)
    result['created_transmitters']=len(scene.transmitters);result['setup_s']=time.perf_counter()-setup;save()
    stage('first_solve')
    def epoch(profile=False):
        tf.random.set_seed(42)
        if profile:dr.kernel_history();dr.set_flag(dr.JitFlag.KernelHistory,True)
        begin=time.perf_counter()
        traced=scene.trace_paths(max_depth=1,method='fibonacci',num_samples=result['ray_count'],los=True,reflection=True,diffraction=False,scattering=True,ris=False,scat_keep_prob=1.,check_scene=True)
        dr.sync_thread()
        for path in traced[:4]:
            if path is not None and hasattr(path,'tau'):tf.reduce_sum(path.tau).numpy()
        trace_done=time.perf_counter()
        paths=scene.compute_fields(*traced,check_scene=False,scat_random_phases=False)
        # A device reduction and scalar export fence completion without exporting all paths.
        coefficient_fence=float(tf.reduce_sum(tf.math.real(paths.a)).numpy())
        retained=int(tf.reduce_sum(tf.cast(paths.tau>=0,tf.int64)).numpy())
        dr.sync_thread();done=time.perf_counter()
        row={'trace_ms':1000*(trace_done-begin),'fields_and_fence_ms':1000*(done-trace_done),'propagation_ms':1000*(done-begin),'retained_paths':retained,'coefficient_shape':list(paths.a.shape),'coefficient_fence':coefficient_fence,'tensorflow_memory':tf.config.experimental.get_memory_info('GPU:0'),'host_peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}
        if profile:
            history=dr.kernel_history();dr.set_flag(dr.JitFlag.KernelHistory,False)
            rows=[]
            for e in history:
                row_e={}
                for k in ('backend','type','execution_time','operation_count','cache_hit','cache_disk','codegen_time','backend_time','uses_optix'):
                    if k in e:
                        v=e[k];row_e[k]=v if v is None or isinstance(v,(str,int,float,bool)) else getattr(v,'name',str(v))
                rows.append(row_e)
            row['device_events']=rows
        return row
    result['first']=epoch();save()
    stage('warmup');result['warmups']=[]
    for i in range(args.warmup):result['warmups'].append(epoch());save()
    stage('timed')
    for i in range(args.iterations):
        row=epoch();result['epochs'].append(row);save();print(f'epoch {i+1}/{args.iterations}: {row["propagation_ms"]:.1f} ms',flush=True)
    stage('profile');result['profile']=epoch(profile=True)
    values=[r['propagation_ms'] for r in result['epochs']]
    result['statistics']={'p50_ms':float(np.median(values)),'p95_ms':float(np.percentile(values,95)),'max_ms':max(values),'mean_ms':float(np.mean(values)),'serial_updates_hz':1000/float(np.mean(values))}
    result['status']='ok';result['stage']='complete'
except Exception as exc:
    result['status']='failed';result['error']=f'{type(exc).__name__}: {exc}';result['traceback']=traceback.format_exc();print(result['traceback'],flush=True)
finally:
    result['wall_s']=time.perf_counter()-start;result['host_peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024;save()
raise SystemExit(0 if result['status']=='ok' else 20)
