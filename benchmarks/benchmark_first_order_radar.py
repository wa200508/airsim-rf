"""CPU first-order radar screening; RF windows only, no simulator or skill timing."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import platform
import statistics
import tempfile
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--iterations',type=int,default=10);p.add_argument('--warmup',type=int,default=1)
    p.add_argument('--output',type=Path,default=Path('first-order-radar-results'))
    args=p.parse_args()
    if args.iterations<2 or args.warmup<0:p.error('Use at least two iterations and nonnegative warmup')
    import numpy as np
    import mitsuba as mi
    mi.set_variant('llvm_ad_mono_polarized')
    import drjit as dr
    dr.set_thread_count(2)
    import sionna.rt as rt
    from airsim_rf.dashboard_scenario import prepare
    from airsim_rf.dashboard_radar import RadarWindowReceiver
    from airsim_rf import radar_scattering
    root=Path(__file__).resolve().parents[1];args.output.mkdir(parents=True,exist_ok=True)
    def stats(values):return {'median':statistics.median(values),'sd':statistics.stdev(values),'p95':float(np.percentile(values,95))}
    def kin(pos,vel):return {'pose':{'position':dict(zip(('x','y','z'),np.asarray(pos)*[1,-1,-1])),'orientation':{'w':1.,'x':0.,'y':0.,'z':0.}},
                             'twist':{'linear':dict(zip(('x','y','z'),np.asarray(vel)*[1,-1,-1])),'angular':{'x':0.,'y':0.,'z':0.}}}
    hardware={'cpu':next(line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),
              'cpu_quota':Path('/sys/fs/cgroup/cpu.max').read_text().strip(),'drjit_threads':dr.thread_count(),'platform':platform.platform(),
              'sionna_rt':rt.__version__,'mitsuba':mi.__version__,'drjit':dr.__version__}
    hashes={name:sha256((root/'src/airsim_rf'/name).read_bytes()).hexdigest() for name in ('fmcw.py','radar_scattering.py','dashboard_radar.py')}
    with tempfile.TemporaryDirectory(prefix='radar-benchmark-') as directory:
        run=Path(directory);prepare(run,scenario_dir='mmwave-radar',duration_s=.004)
        config=json.loads((run/'runtime.json').read_text());arrays=json.loads((run/'arrays.json').read_text())
        cases=[('clear',False,[200,0,210],[-20,0,0]),('masked',False,[-240,-150,210],[20,0,0]),
               ('clear',True,[200,0,210],[-20,0,0]),('masked',True,[-240,-150,210],[20,0,0]),
               ('1024-valid-scatterers',False,[0,0,210],[20,0,0])]
        for name,enabled,pos,vel in cases:
            radio=deepcopy(config['radios']);radio['radar']['clutter']['enabled']=enabled
            stress=name=='1024-valid-scatterers'
            scene=rt.load_scene() if stress else rt.load_scene(str(run/'bundle/scene.xml'),merge_shapes=False)
            receiver=RadarWindowReceiver(scene,radio,deepcopy(arrays))
            receiver.control.configure(config['skill']['mode_config']);receiver.control.set_state({'transmit':True,'receive':True})
            receiver.update({'RadarDrone':kin(pos,vel)})
            if stress:
                from airsim_rf.radar import PointTarget
                receiver.targets=[PointTarget('scatterer_'+str(i),(100+i//32*.25,(i%32-15.5)*.25,210.),1.) for i in range(1024)]
                receiver.orientation=np.zeros(3)
            cold=time.perf_counter();receiver.capture(0,num_samples=40000);cold=(time.perf_counter()-cold)*1000
            for i in range(args.warmup):receiver.capture((i+1)*4_000_000,num_samples=40000)
            # Small inclusive stage timers add diagnostic host overhead.
            timers={};original_visibility=radar_scattering.segment_visibility;original_render=receiver.radar._render_echoes
            def visibility(*a,**kw):
                start=time.perf_counter();out=original_visibility(*a,**kw);timers['visibility_ms']+=(time.perf_counter()-start)*1000;return out
            def render(*a,**kw):
                start=time.perf_counter();out=original_render(*a,**kw);timers['tone_ms']+=(time.perf_counter()-start)*1000;return out
            samples=[];radar_scattering.segment_visibility=visibility;receiver.radar._render_echoes=render
            try:
                for i in range(args.iterations):
                    timers={'visibility_ms':0.,'tone_ms':0.};start=time.perf_counter()
                    cap=receiver.capture((i+args.warmup+1)*4_000_000,num_samples=40000)['radar_rx0']
                    total=(time.perf_counter()-start)*1000
                    samples.append({'service_ms':total,**timers,'other_ms':total-sum(timers.values()),'retained_paths':cap.retained_paths,
                                    'clutter':receiver.last_clutter_diagnostics})
            finally:radar_scattering.segment_visibility=original_visibility;receiver.radar._render_echoes=original_render
            result={'scope':'first_order_radar_rf_window','measurement_mode':'instrumented_cpu_screening','case_kind':'1024 retained echoes, free-space visibility stress' if stress else 'configured scene',
                    'hardware':hardware,'source_file_sha256':hashes,'scenario_input_sha256':config['input_sha256'],
                    'capture_duration_ms':4.,'samples_per_window':40000,'chirps_per_window':100,'adc_samples_per_chirp':256,
                    'arguments':vars(args)|{'output':str(args.output),'clutter_enabled':enabled,'viewpoint':name},
                    'timing_includes':['constant-velocity intra-window poses','direct visibility on shared mesh','coherent tiled IF synthesis','receiver noise and ADC','acquisition gate packing'],
                    'timing_excludes':['AirSim RPC/physics','camera','network transport','recording','external skill/DSP','startup and warmup'],
                    'limitations':['CPU only','repeated fixed window origins with intra-window platform motion','short screening, no sustained-flight or GPU claim','per-stage timers add diagnostic overhead'],
                    'first_window_ms':cold,'summary':{key:stats([r[key] for r in samples]) for key in ('service_ms','visibility_ms','tone_ms','other_ms')},
                    'wall_seconds_per_signal_second':sum(r['service_ms'] for r in samples)/(4*len(samples)),'samples':samples}
            path=args.output/(name+'-'+('clutter' if enabled else 'targets'))
            path=Path(str(path)+'.json');path.write_text(json.dumps(result,indent=2)+'\n')
            print(json.dumps({'case':path.stem,'summary':result['summary'],'wall_signal_ratio':result['wall_seconds_per_signal_second'],'echoes':samples[-1]['retained_paths']}),flush=True)


if __name__=='__main__':main()
