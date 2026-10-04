"""External legacy-Sionna adapter for the P100 experiment; repository untouched."""
import os, sys
from pathlib import Path
if Path(sys.argv[0]).name in ('benchmark_sdr_runtime.py','gpu_preflight.py','pluto_esm_drones.py'):
    import time, re
    import numpy as np
    import tensorflow as tf
    import drjit as dr
    import mitsuba as mi
    backend=sys.argv[sys.argv.index('--backend')+1] if '--backend' in sys.argv else 'cuda'
    if backend=='cpu': tf.config.set_visible_devices([], 'GPU')
    import sionna
    import sionna.rt as rt
    dr.set_thread_count(2)
    if not hasattr(dr,"thread_count"): dr.thread_count=lambda: 2
    backend=sys.argv[sys.argv.index('--backend')+1] if '--backend' in sys.argv else 'cuda'
    native_variant=mi.set_variant
    def variant(name):
        return native_variant('cuda_ad_rgb' if name.startswith('cuda') else 'llvm_ad_rgb')
    mi.set_variant=variant
    variant(backend)
    rt.__version__=sionna.__version__
    if not hasattr(dr,'kernel_history_clear'):
        dr.kernel_history_clear=lambda: dr.kernel_history()
    native_load=rt.load_scene
    def load(filename, **kwargs):
        path=Path(filename)
        xml=path.read_text()
        xml=re.sub(r'<bsdf.*?</bsdf>', '<bsdf type="diffuse" id="legacy_ground"/>', xml, flags=re.S)
        xml=xml.replace('ground-material','legacy_ground')
        xml=re.sub(r'value="([^"<>]+\.ply)"', lambda m: 'value="'+str((path.parent/m.group(1)).resolve())+'"', xml)
        converted=Path('/tmp')/('legacy-'+path.name)
        converted.write_text(xml)
        scene=native_load(str(converted),**kwargs)
        material=scene.radio_materials['legacy_ground']
        material.frequency_update_callback=None
        material.relative_permittivity=5.
        material.conductivity=.01
        material.scattering_coefficient=.3
        material.is_placeholder=False
        scene.synthetic_array=True
        return scene
    rt.load_scene=load
    native_array=rt.PlanarArray
    def array(*args,**kwargs):
        kwargs.setdefault('vertical_spacing',.5)
        kwargs.setdefault('horizontal_spacing',.5)
        return native_array(*args,**kwargs)
    rt.PlanarArray=array
    for clsname in ('Transmitter','Receiver'):
        cls=getattr(rt,clsname)
        def device(*args,_cls=cls,**kwargs):
            velocity=kwargs.pop('velocity',[0.,0.,0.])
            obj=_cls(*args,**kwargs)
            obj.velocity=velocity
            return obj
        setattr(rt,clsname,device)
    class Array:
        def __init__(self,a): self.a=np.asarray(a)
        def numpy(self): return self.a
    class Paths:
        def __init__(self,native,scene):
            self.native=native
            native.normalize_delays=False
            theta_t,phi_t=native.theta_t.numpy()[0],native.phi_t.numpy()[0]
            theta_r,phi_r=native.theta_r.numpy()[0],native.phi_r.numpy()[0]
            def direction(theta,phi):
                return np.stack([np.sin(theta)*np.cos(phi),np.sin(theta)*np.sin(phi),np.cos(theta)],axis=-1)
            txv=np.array([d.velocity for d in scene.transmitters.values()])
            rxv=np.array([d.velocity for d in scene.receivers.values()])
            fd=((direction(theta_t,phi_t)*txv[None,:,None,:]).sum(-1)+(direction(theta_r,phi_r)*rxv[:,None,None,:]).sum(-1))/float(scene.wavelength.numpy())
            self.doppler=Array(fd)
        def cir(self,**kwargs):
            a,tau=self.native.cir()
            return a.numpy()[0],tau.numpy()[0]
    class LegacySolver:
        def __init__(self,**kwargs):
            self.stage_timings={}
        def specular_plane_count(self,scene):
            return sum(shape.face_count() for shape in scene.mi_scene.shapes()) if hasattr(scene,'mi_scene') else sum(shape.face_count() for shape in scene._scene.shapes())
        def __call__(self,scene,**kwargs):
            tf.random.set_seed(kwargs.get('seed',42))
            samples=kwargs.get('samples_per_src',1028)
            start=time.perf_counter()
            native=scene.compute_paths(max_depth=kwargs.get('max_depth',1),num_samples=samples*len(scene.transmitters),los=True,reflection=True,diffraction=False,scattering=kwargs.get('diffuse_reflection',True),ris=False,scat_keep_prob=1.,scat_random_phases=False)
            result=Paths(native,scene)
            self.stage_timings={'legacy_native_solve_export_ms':1000*(time.perf_counter()-start),'host_numpy_sampling_ms':0.,'proposal_table_prepare_ms':0.}
            return result
    import airsim_rf.scattering as scattering
    import airsim_rf.single_bounce as single_bounce
    scattering.FirstOrderScatteringPathSolver=LegacySolver
    single_bounce.SingleBouncePathSolver=LegacySolver
    print('LEGACY P100 ADAPTER: Sionna '+sionna.__version__+'; native Fibonacci rays; original I/Q receiver chain; backend '+mi.variant(),flush=True)
