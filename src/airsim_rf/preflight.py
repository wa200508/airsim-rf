"""Offline capture planning and an explicit, isolated CUDA health check."""
from importlib import metadata
import json
from numbers import Integral
from pathlib import Path
import shutil
import subprocess
import sys


def read_sim_config(path):
    text=Path(path).read_text()
    try:
        value=json.loads(text)
    except json.JSONDecodeError:
        try:
            import commentjson
        except ImportError as error:
            raise ValueError('Commented simulator JSON requires commentjson (installed with the ProjectAirSim client)') from error
        value=commentjson.loads(text)
    if not isinstance(value,dict):
        raise ValueError(f'Simulator configuration must be an object: {path}')
    return value


def positive_count(value, name):
    if isinstance(value,bool) or not isinstance(value,Integral) or value<1:
        raise ValueError(f'{name} must be a positive integer')
    return int(value)


def check(config_path, *, updates=10, advance_ns=10_000_000, max_samples=2_000_000,
          output=None, gpu=False, pascal_compat=False):
    from .live import validate_inputs
    updates=positive_count(updates,'updates')
    advance_ns=positive_count(advance_ns,'advance_ns')
    max_samples=positive_count(max_samples,'max_samples')
    path=Path(config_path).resolve()
    provenance=validate_inputs(path)
    config=json.loads(path.read_text())
    scene=read_sim_config(path.parent/config['sim_config']/config['scene'])
    clock=scene.get('clock',{})
    if not isinstance(clock,dict) or clock.get('type')!='steppable':
        raise ValueError('Capture planning requires a steppable simulator clock with step-ns')
    tick=positive_count(clock.get('step-ns'),'simulator clock step-ns')
    interval=((advance_ns+tick-1)//tick)*tick
    from .sdr import PlutoSDRProfile
    rate=PlutoSDRProfile(**config['receiver_profile']).sample_rate_hz
    samples=interval*rate/1e9
    if abs(samples-round(samples))>1e-6:
        raise ValueError('Physics interval is not sample-aligned; choose a compatible step-ns/sample rate')
    samples=round(samples)
    if not 1<=samples<=max_samples:
        raise ValueError(f'Physics interval including tick overshoot requires {samples} samples; '
                         f'max_samples is {max_samples}. Shorten advance_ns or increase the cap.')
    total=updates*samples
    # 16 samples cover the default sinc lookahead. Zero boundary is intentional
    # at transmission onset; avoid an accidental waveform end during capture.
    short=[name for name,source in provenance['waveforms'].items() if source['samples']<total+16]
    if short:
        raise ValueError(f'Waveform too short for planned capture plus 16-sample lookahead: {short}; '
                         f'need at least {total+16} samples each. Extend the source or reduce updates.')
    receivers=len(config['radios'])-len(provenance['waveforms'])
    byte_count=4*total*receivers
    storage=None
    if output is not None:
        destination=Path(output).resolve()
        if destination.exists():
            raise ValueError(f'Output already exists; choose a new recording directory: {destination}')
        parent=destination.parent
        while not parent.exists():
            parent=parent.parent
        if not parent.is_dir():
            raise ValueError(f'Output parent must be a directory: {parent}')
        available=shutil.disk_usage(parent).free
        if available<byte_count:
            raise ValueError(f'Insufficient output space: need at least {byte_count} I/Q bytes, have {available}')
        storage={'output':str(destination),'free_bytes':available,'raw_iq_bytes':byte_count,
                 'metadata_and_filesystem_overhead_included':False}
    versions={}
    for package in ('airsim-rf','numpy','scipy','sionna-rt','mitsuba','drjit','projectairsim','cupy-cuda12x','usd-core','sigmf'):
        try:
            versions[package]=metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package]=None
    backend={'status':'not_requested','server_contacted':False}
    if gpu:
        command=[sys.executable,'-m','airsim_rf.cuda_launch','-m','airsim_rf.preflight',str(path)]
        if pascal_compat:
            command.append('--pascal-compat')
        try:
            process=subprocess.run(command,text=True,capture_output=True,timeout=180)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError('CUDA preflight timed out after 180 seconds; inspect GPU load and driver/backend setup') from error
        if process.returncode:
            raise RuntimeError('CUDA preflight failed; check driver/container GPU access and the qualified '
                               f'CUDA/OptiX/CuPy versions. No CPU fallback. Details: {process.stderr.strip() or process.stdout.strip()}')
        backend=json.loads(process.stdout)
    return {'status':'passed','scope':'offline configuration and capture plan'+('; CUDA health checked' if gpu else ''),
            'server_contacted':False,'versions':versions,'inputs':provenance,
            'plan':{'updates':updates,'requested_advance_ns':advance_ns,'physics_tick_ns':tick,
                    'expected_interval_ns':interval,'samples_per_window':samples,
                    'complex_samples_per_receiver':total,'signal_seconds_per_receiver':total/rate,
                    'receivers':receivers,'raw_iq_bytes':byte_count,
                    'timing_basis':'configured steppable clock; actual capture timestamps remain authoritative'},
            'storage':storage,'backend':backend}


def gpu_check(config_path, *, pascal_compat=False):
    """Exercise RF mesh loading, CUDA/OptiX propagation and CuPy rendering."""
    import numpy as np
    import mitsuba as mi
    mi.set_variant('cuda_ad_mono_polarized')
    if pascal_compat:
        from .p100_compat import enable_pascal_compat
        enable_pascal_compat()
    import sionna.rt as rt
    import cupy as cp
    import drjit as dr
    path=Path(config_path).resolve()
    config=json.loads(path.read_text())
    # Loading the supplied mesh catches missing XML/PLY and backend material errors.
    loaded=rt.load_scene(str(path.parent/config['rf_scene']),merge_shapes=False)
    scene=rt.load_scene()
    scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V')
    scene.rx_array=scene.tx_array
    scene.add(rt.Transmitter('preflight_tx',position=[0,0,1]))
    scene.add(rt.Receiver('preflight_rx',position=[1,0,1]))
    from .single_bounce import SingleBouncePathSolver
    paths=SingleBouncePathSolver()(scene,max_depth=0)
    gains,delays=paths.cir(normalize_delays=False,out_type='numpy')
    if not np.isfinite(gains).all() or np.sum(delays>=0)!=1:
        raise RuntimeError('CUDA propagation health solve did not retain its known direct path')
    from .batched_rendering import PathRenderJob
    from .sampled_waveform import SampledWaveform
    from .research.doppler_basis import DopplerBasisRenderer
    from .research.doppler_basis_cuda import CudaDopplerBasisRenderer
    wave=SampledWaveform(np.ones(1024,dtype=complex),2e6,-200000,boundary='zero')
    job=PathRenderJob(np.array([1.+.2j]),np.array([3e-6]),np.array([17.]),wave)
    settings={'sample_rate_hz':2e6,'max_delay_s':100e-6,'max_doppler_hz':2500}
    rendered=CudaDopplerBasisRenderer(**settings).render([job],num_samples=256)
    expected=DopplerBasisRenderer(**settings).render([job],num_samples=256)
    np.testing.assert_allclose(rendered,expected,rtol=2e-9,atol=2e-9)
    device=cp.cuda.runtime.getDeviceProperties(cp.cuda.runtime.getDevice())
    name=device['name'].decode() if isinstance(device['name'],bytes) else device['name']
    dr.sync_thread()
    return {'status':'passed','scope':'configured RF mesh loading, synthetic direct-path CUDA/OptiX and CPU-referenced CuPy renderer',
            'server_contacted':False,'gpu':name,'loaded_rf_objects':sorted(loaded.objects),
            'maximum_renderer_error':float(np.max(abs(rendered-expected))),'pascal_compat':pascal_compat}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Isolated GPU worker; use airsim-rf preflight for the public interface')
    parser.add_argument('config',type=Path)
    parser.add_argument('--pascal-compat',action='store_true')
    args=parser.parse_args()
    print(json.dumps(gpu_check(args.config,pascal_compat=args.pascal_compat)))
