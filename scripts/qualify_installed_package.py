"""Exercise the installed wheel outside a checkout; preserve JSON acceptance evidence."""
import argparse
from hashlib import sha256
from importlib import metadata
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    import airsim_rf
    if Path(sys.prefix) not in Path(airsim_rf.__file__).parents:
        raise RuntimeError('Qualification must import an installed wheel outside the checkout')
    executable=Path(sys.executable).parent/'airsim-rf'
    checks={};commands=[]
    scenario=subprocess.run([sys.executable,'-m','airsim_rf.dashboard','--check-scenario'],text=True,capture_output=True)
    if scenario.returncode:raise RuntimeError('Installed default scenario missing: '+scenario.stderr)
    checks['installed_editable_scenario_available']=json.loads(scenario.stdout)['status']=='valid'
    replay=subprocess.run([sys.executable,'-m','airsim_rf.sample_recording','--help'],text=True,capture_output=True)
    if replay.returncode:raise RuntimeError('Installed neutral I/Q replay missing: '+replay.stderr)
    checks['installed_neutral_iq_replay_available']=True
    def run(arguments, *, expected_code=0):
        result=subprocess.run([str(executable),*map(str,arguments)],text=True,capture_output=True)
        commands.append({'arguments':list(map(str,arguments)),'returncode':result.returncode,
                         'stdout':result.stdout,'stderr':result.stderr})
        if result.returncode!=expected_code:
            raise RuntimeError(f'Installed command failed: {arguments}: {result.stderr}')
        return result
    for mode in ('ground','shared'):
        target=args.output/mode
        run(['example','--geometry',mode,'--output',target])
        plan=json.loads(run(['preflight','--config',target/'radios.json','--output',args.output/(mode+'-capture')]).stdout)
        checks[mode+'_expected_plan']=plan['plan']['complex_samples_per_receiver']==240000 and not plan['server_contacted']
        checks[mode+'_complete_local_assets']=all((target/path).exists() for path in ('radios.json','tx0.npy','sim_config/scene_rf.jsonc','sim_config/robot_rf.jsonc','README.txt'))
    # Relocate the generated scenario; no repo/temporary extraction paths may be needed.
    import shutil
    shutil.copytree(args.output/'shared',args.output/'relocated')
    run(['preflight','--config',args.output/'relocated/radios.json'])
    checks['relocated_bundle_consumable']=True
    bad=run(['preflight','--config',args.output/'shared/radios.json','--updates','1000'],expected_code=2)
    checks['short_source_diagnosed']='Waveform too short' in bad.stderr
    # A completed independently generated ADC fixture checks both installed consumers.
    # This is file/API acceptance, not new physical propagation evidence.
    import numpy as np
    import mitsuba as mi
    mi.set_variant('llvm_ad_mono_polarized')
    import drjit as dr
    dr.set_thread_count(2)
    import sionna.rt as rt
    scene=rt.load_scene()
    scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V')
    scene.rx_array=scene.tx_array
    scene.add(rt.Transmitter('tx0',position=[0,0,1]))
    scene.add(rt.Receiver('rx0',position=[1,0,1]))
    from airsim_rf.single_bounce import SingleBouncePathSolver
    _,delays=SingleBouncePathSolver()(scene,max_depth=0).cir(normalize_delays=False,out_type='numpy')
    checks['clean_cpu_propagation']=int(np.sum(delays>=0))==1 and abs(float(delays.reshape(-1)[0])*299792458.-1)<1e-5
    from airsim_rf.sampled_waveform import SampledWaveform
    from airsim_rf.sdr import PlutoSDRProfile,SDREmitter,SDRNetworkReceiver
    waveform=SampledWaveform(np.exp(2j*np.pi*150000*np.arange(16384)/2e6),2e6,-1_000_000,boundary='zero')
    receiver=SDRNetworkReceiver(scene,{'tx0':SDREmitter(waveform,transmit_power_w=1e-6)},
        PlutoSDRProfile(noise_enabled=False),renderer='numpy',path_solver='single-bounce',max_depth=0)
    capture=receiver.capture(0,num_samples=4096)['rx0']
    checks['clean_cpu_receiver_processing']=len(capture.adc_iq_volts)==4096 and bool(np.isfinite(capture.adc_iq_volts).all())
    root=args.output/'adc-fixture';root.mkdir()
    fs=2_000_000;count=24000
    codes=np.column_stack((np.rint(500*np.cos(2*np.pi*150000*np.arange(count)/fs)),
                           np.rint(500*np.sin(2*np.pi*150000*np.arange(count)/fs)))).astype('<i2')
    with (root/'rx0.sigmf-data').open('wb') as stream:
        for _ in range(2):codes.tofile(stream)
    rows=[{'sim_time_ns':i*12_000_000,'samples_per_receiver':count} for i in range(2)]
    manifest={'status':'complete','sample_rate_hz':fs,'wall_seconds_per_signal_second':None,'rows':rows}
    meta={'global':{'core:datatype':'ci16_le','core:sample_rate':fs,'core:version':'1.2.6'},'captures':[
        {'core:sample_start':i*count,'core:frequency':915e6,'airsim_rf:sim_time_ns':row['sim_time_ns'],
         'airsim_rf:volts_per_count':.001,'airsim_rf:clipped_component_fraction':0.} for i,row in enumerate(rows)]}
    (root/'manifest.json').write_text(json.dumps(manifest))
    (root/'rx0.sigmf-meta').write_text(json.dumps(meta))
    inspection=json.loads(run(['inspect',root]).stdout)
    processed=json.loads(run(['process',root]).stdout)
    checks['recording_consumers_accept_known_adc_samples']=(inspection['receivers']['rx0']['complex_samples']==48000
        and processed['complex_samples']==48000 and abs(processed['rms_complex_volts']-.5)<.001)
    report={'status':'passed' if all(checks.values()) else 'failed','checks':checks,
            'python':sys.version,'installed_module':str(airsim_rf.__file__),
            'versions':{name:metadata.version(name) for name in ('airsim-rf','numpy','scipy','sionna-rt','mitsuba','drjit','projectairsim','usd-core','sigmf')},
            'commands':commands,'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope':'Clean installed wheel, complete examples and CPU interfaces; ADC fixture is synthetic, not a live capture'}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='commands'},indent=2))
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':
    main()
