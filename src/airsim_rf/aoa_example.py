"""Ready-to-run SDR Challenge-inspired MUSIC → emitter-track example.

The RF pipeline uses a supplied kinematic trajectory, not live simulator physics.
Each array element is an individually traced/rendered/filtered/quantized receiver.
"""
from importlib import metadata
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from .geometry import file_digest, read_bundle


def dump(path, value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def prepare(output, *, windows=100):
    from scipy.signal import firwin,upfirdn
    from .example import prepare as prepare_shared
    if isinstance(windows,bool) or not isinstance(windows,int) or not 32<=windows<=1000:
        raise ValueError('AoA example requires 32–1000 windows (at least 0.384 s for track settling)')
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    inputs=output/'inputs';prepare_shared(inputs,geometry='shared')
    fs=2_000_000;carrier=915_000_000.;duration=windows*.012+.2
    # Independent random data, pulse-shaped on the TX side. No transmitted bits
    # or symbols enter the noncooperative MUSIC/tracking consumer.
    rng=np.random.default_rng(20261020)
    symbols=(2*rng.integers(0,2,round(duration*25000)+32)-1
             +1j*(2*rng.integers(0,2,round(duration*25000)+32)-1))/np.sqrt(2)
    taps=firwin(801,20000,fs=fs,window=('kaiser',8.))
    waveform=upfirdn(taps,symbols,up=80)[:round(duration*fs)]
    waveform/=np.sqrt(np.mean(abs(waveform)**2))
    np.save(inputs/'tx0.npy',waveform)
    spacing=299792458./carrier/2
    offsets=(np.arange(4)-1.5)*spacing
    sites=[{'id':f'site{i}','channels':[f'site{i}_e{j}' for j in range(4)],
            'center_rf_m':[0.,y,120.],'yaw_rad':0.,'element_offsets_m':offsets.tolist(),
            'calibration_complex':[[1.,0.]]*4} for i,y in enumerate((-10.,10.))]
    arrays={'schema_version':1,'carrier_hz':carrier,'sample_rate_hz':fs,'sites':sites,
            'clock_assumption':'Common nominal sample clock and LO phase within each site; ideal calibrated channels',
            'source_assumption':'One narrowband emitter in the front hemisphere, approximately same elevation'}
    dump(output/'arrays.json',arrays)
    config=json.loads((inputs/'radios.json').read_text())
    config['receiver_profile'].update(noise_enabled=True)
    config['antennas']={side:{'pattern':'iso','polarization':'V'} for side in ('tx','rx')}
    config['propagation']['mode']='direct'
    tx=config['radios']['tx0'];tx.update(robot='Emitter',transmit_power_w=.001,baseband_frequency_bounds_hz=[-100000,100000])
    radios={'tx0':tx}
    for site in sites:
        for channel,offset in zip(site['channels'],offsets):
            radios[channel]={'robot':site['id'],'mount_body_m':[0.,float(-offset),0.]}
    config['radios']=radios
    dump(inputs/'radios.json',config)
    sim=inputs/'sim_config/scene_rf.jsonc'
    scene=json.loads(sim.read_text())
    scene['actors']=[{'type':'robot','name':name,'origin':{'xyz':xyz,'rpy-deg':'0 0 0'},'robot-config':'robot_rf.jsonc'}
        for name,xyz in [('Emitter','20 7.2 -120'),('site0','0 10 -120'),('site1','0 -10 -120')]]
    dump(sim,scene)
    scenario={'schema_version':1,'scope':'supplied RF trajectory; no simulator connection or physics claim',
              'windows':windows,'advance_ns':12_000_000,'samples_per_window':24000,
              'emitter_position_rf_m':[20.,-7.2,120.],'emitter_velocity_rf_m_s':[0.,12.,0.],
              'waveform_origin_ns':-100_000_000,'symbol_rate_hz':25000,
              'waveform':'independent QPSK symbols, 80x upsampling and 801-tap Kaiser lowpass pulse shaping, unit mean power',
              'waveform_sha256':file_digest(inputs/'tx0.npy')}
    dump(output/'scenario.json',scenario)
    (inputs/'README.txt').write_text('AoA/2D tracking example inputs.\n'
        'radios.json is a complete stationary live configuration at the initial pose.\n'
        'The track demo additionally drives the supplied RF trajectory in scenario.json.\n'
        'It does not run live simulator physics. Arrays use common nominal clocks/LOs.\n'
        'All 8 element channels are individually propagated and recorded.\n'
        'Consumer inputs: capture/ and arrays.json; truth.json is evaluation only.\n')
    return scenario,arrays


def render(output, *, backend='cpu', windows=100, reflection=False, pascal_compat=False):
    if backend not in ('cpu','cuda'):
        raise ValueError('backend must be cpu or cuda')
    if pascal_compat and backend!='cuda':
        raise ValueError('Pascal compatibility is a CUDA option')
    import mitsuba as mi
    mi.set_variant('cuda_ad_mono_polarized' if backend=='cuda' else 'llvm_ad_mono_polarized')
    if pascal_compat:
        from .p100_compat import enable_pascal_compat
        enable_pascal_compat()
    import drjit as dr
    dr.set_thread_count(2)
    import sionna.rt as rt
    from .sampled_waveform import SampledWaveform
    from .sdr import PlutoSDRProfile,SDREmitter,SDRNetworkReceiver
    output=Path(output)
    scenario,arrays=prepare(output,windows=windows)
    config=json.loads((output/'inputs/radios.json').read_text())
    document,bundle,_=read_bundle(output/'inputs/bundle')
    scene=rt.load_scene(str(output/'inputs/bundle/scene.xml'),merge_shapes=False)
    scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V')
    scene.rx_array=scene.tx_array
    scene.add(rt.Transmitter('tx0',position=scenario['emitter_position_rf_m']))
    for site in arrays['sites']:
        for name,offset in zip(site['channels'],site['element_offsets_m']):
            center=np.asarray(site['center_rf_m'])
            scene.add(rt.Receiver(name,position=(center+[0,offset,0]).tolist()))
    waveform=SampledWaveform(np.load(output/'inputs/tx0.npy'),arrays['sample_rate_hz'],
        scenario['waveform_origin_ns'],boundary='zero')
    profile=PlutoSDRProfile(**config['receiver_profile'])
    receiver=SDRNetworkReceiver(scene,{'tx0':SDREmitter(waveform,transmit_power_w=.001,
        baseband_frequency_bounds_hz=(-100000,100000))},profile,
        renderer='basis-cuda' if backend=='cuda' else 'basis-cpu',continuous=True,
        path_solver='single-bounce',max_depth=int(reflection),samples_per_link=2,seed=20261020)
    directory=output/'capture';directory.mkdir()
    names=list(scene.receivers)
    metas={name:{'global':{'core:datatype':'ci16_le','core:version':'1.2.6',
        'core:sample_rate':arrays['sample_rate_hz'],
        'core:extensions':[{'name':'airsim_rf','version':'0.1.0','optional':True}],
        'core:description':'Simulated coherent array element, input-referred 12-bit SDR; ideal common clocks/LO'},
        'captures':[],'annotations':[]} for name in names}
    rows=[];frames=[];channels=[]
    manifest={'status':'running','scope':'supplied_trajectory_rf_recording',
        'sample_rate_hz':arrays['sample_rate_hz'],'rows':rows,
        'provenance':{'source_kind':'supplied trajectory; emitter poses held out in truth.json',
            'waveform_sha256':scenario['waveform_sha256'],'symbol_rate_hz':scenario['symbol_rate_hz'],
            'geometry_sha256':bundle['scene_sha256'],
            'geometry_static':True,'radio_clock_model':arrays['clock_assumption'],'backend':backend,
            'renderer':receiver.renderer,'sionna_rt':rt.__version__,'mitsuba':mi.__version__,
            'propagation':'direct + first-order specular' if reflection else 'direct visibility',
            'noise_enabled':True,'source_module_sha256':file_digest(__file__)}}
    def checkpoint():
        for name,meta in metas.items():dump(directory/(name+'.sigmf-meta'),meta)
        dump(directory/'manifest.json',manifest)
    checkpoint()
    started=perf_counter()
    try:
        for index in range(windows):
            epoch=index*scenario['advance_ns'];t=epoch*1e-9
            position=np.asarray(scenario['emitter_position_rf_m'])+t*np.asarray(scenario['emitter_velocity_rf_m_s'])
            scene.transmitters['tx0'].position=position.tolist()
            scene.transmitters['tx0'].velocity=scenario['emitter_velocity_rf_m_s']
            captures=receiver.capture(epoch,num_samples=scenario['samples_per_window'])
            for name,capture in captures.items():
                with (directory/(name+'.sigmf-data')).open('ab') as stream:capture.adc_codes.astype('<i2').tofile(stream)
                metas[name]['captures'].append({'core:sample_start':index*scenario['samples_per_window'],
                    'core:frequency':arrays['carrier_hz'],'airsim_rf:sim_time_ns':epoch,
                    'airsim_rf:volts_per_count':capture.volts_per_count,
                    'airsim_rf:clipped_component_fraction':capture.clipped_component_fraction})
            rows.append({'sim_time_ns':epoch,'samples_per_receiver':scenario['samples_per_window'],
                         'geometry':{'sim_time_ns':epoch,'geometry_sha256':bundle['scene_sha256']}})
            middle=epoch+scenario['advance_ns']//2
            truth=np.asarray(scenario['emitter_position_rf_m'])+middle*1e-9*np.asarray(scenario['emitter_velocity_rf_m_s'])
            frames.append({'sim_time_ns':middle,'position_rf_m':truth.tolist(),
                'velocity_rf_m_s':scenario['emitter_velocity_rf_m_s'],
                'bearings_rad':[float(np.arctan2(truth[1]-site['center_rf_m'][1],truth[0]-site['center_rf_m'][0])) for site in arrays['sites']]})
            channels.append({'sim_time_ns':epoch,'retained_paths':{name:c.retained_paths for name,c in captures.items()}})
        manifest['status']='complete'
    except BaseException as error:
        manifest.update(status='failed',error=str(error));raise
    finally:
        signal_s=len(rows)*scenario['advance_ns']*1e-9
        manifest['signal_seconds_per_receiver']=signal_s
        manifest['wall_seconds_per_signal_second']=(perf_counter()-started)/signal_s if signal_s else None
        checkpoint()
        dump(output/'truth.json',{'scope':'held-out evaluation; never passed to consumer','frames':frames})
        dump(output/'channels.json',channels)
    return manifest


def plot(output, result, truth_path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    truth=json.loads(Path(truth_path).read_text())['frames']
    xy=np.asarray([f['position_rf_m'][:2] for f in truth])
    estimates=np.asarray([r['track_position_rf_xy_m'] if r['track_position_rf_xy_m'] is not None else [np.nan,np.nan] for r in result['rows']])
    time=np.asarray([r['sim_time_ns'] for r in result['rows']],dtype=np.int64)
    time=(time-time[0])*1e-9
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    axes[0].plot(xy[:,0],xy[:,1],label='Held-out emitter truth',linewidth=2)
    axes[0].plot(estimates[:,0],estimates[:,1],'--',label='MUSIC + FilterPy estimate')
    axes[0].scatter([0,0],[-10,10],marker='^',color='black',label='4-element array sites')
    axes[0].set(xlabel='RF north x (m)',ylabel='RF west y (m)',title='Emitter track from recorded ADC I/Q',aspect='equal')
    axes[0].legend(fontsize=8)
    for site in range(2):
        true=np.rad2deg([frame['bearings_rad'][site] for frame in truth])
        observed=[np.rad2deg(row['bearings'][site]['global_angle_rad']) if row['bearings'][site]['global_angle_rad'] is not None else np.nan for row in result['rows']]
        axes[1].plot(time,true,label=f'Site {site} truth')
        axes[1].plot(time,observed,'--',label=f'Site {site} MUSIC')
    axes[1].set(xlabel='Time from first estimate (s)',ylabel='Bearing from RF north towards west (deg)',title='Unknown QPSK emitter: measured bearings')
    axes[1].legend(fontsize=8)
    for axis in axes:axis.grid(alpha=.25)
    fig.savefig(Path(output)/'tracking.png',dpi=160)
    fig.savefig(Path(output)/'tracking.svg')
    plt.close(fig)


def run(output, *, backend='cpu',windows=100,reflection=False,pascal_compat=False):
    from .aoa_tracking import consume,score
    try:
        metadata.version('doa-py');metadata.version('filterpy')
    except metadata.PackageNotFoundError as error:
        raise RuntimeError('track-demo requires pip install airsim-rf[geometry,tracking]') from error
    output=Path(output)
    render(output,backend=backend,windows=windows,reflection=reflection,pascal_compat=pascal_compat)
    result=consume(output/'capture',output/'arrays.json')
    dump(output/'estimates.json',result)
    metrics=score(result,output/'truth.json')
    negative=consume(output/'capture',output/'arrays.json',reverse_first_array=True)
    negative_score=score(negative,output/'truth.json')
    dump(output/'reversed-array-control.json',{'status':'passed' if negative_score['status']=='failed' else 'failed',
        'scope':'Reversing the first array wiring must fail the unchanged positive-case gates','evaluation':negative_score})
    metrics['checks']['reversed_array_control_rejected']=negative_score['status']=='failed'
    metrics['status']='passed' if all(metrics['checks'].values()) else 'failed'
    dump(output/'metrics.json',metrics)
    from .music_plots import plot_recording
    plot_recording(output/'capture',output/'arrays.json',output)
    plot(output,result,output/'truth.json')
    return metrics
