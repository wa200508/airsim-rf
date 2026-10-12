"""Bounded real Runtime flight + direct/specular SDR qualification.

Requires the pinned Runtime source and a running server. Writes raw recordings
under output; never commands a physical vehicle. See docs/live-workflow.md.
"""
import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import numpy as np


def dump(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def estimate_tone_offset(block, sample_rate, tone_hz):
    """Fit phase after removing a known tone; discard 1 ms at either edge."""
    margin=round(.001*sample_rate)
    if len(block)<=2*margin+2 or not np.isfinite(block).all():
        raise ValueError('A finite window longer than 2 ms is required')
    sample=np.arange(margin,len(block)-margin)
    base=block[sample]*np.exp(-2j*np.pi*tone_hz*sample/sample_rate)
    if np.any(abs(base)==0):
        raise ValueError('Phase estimation requires nonzero samples')
    return float(np.polyfit(sample/sample_rate,np.unwrap(np.angle(base)),1)[0]/(2*np.pi))


async def run(args):
    import commentjson
    import mitsuba as mi
    mi.set_variant('cuda_ad_mono_polarized')
    if args.pascal_compat:
        from airsim_rf.p100_compat import enable_pascal_compat
        enable_pascal_compat()
    import sionna.rt as rt
    from projectairsim import ProjectAirSimClient, World, Drone
    from airsim_rf.bridge import mount_kinematics
    from airsim_rf.live import record
    from airsim_rf.sampled_waveform import SampledWaveform
    from airsim_rf.sdr import PlutoSDRProfile, SDREmitter, SDRNetworkReceiver
    from airsim_rf.terrain import scene_provenance
    from inspect_live_recording import inspect

    root=Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=False)
    sim=args.output/'sim_config';sim.mkdir()
    source=args.runtime_source/'client/python/example_user_scripts/sim_config/robot_quadrotor_fastphysics.jsonc'
    robot=commentjson.loads(source.read_text())
    robot['sensors']=[s for s in robot['sensors'] if s['type']!='camera']
    dump(sim/'moving.jsonc',robot)
    dump(sim/'fixed.jsonc',{'physics-type':'non-physics','links':[{'name':'Frame','collision':{'enabled':False}}],'sensors':[]})
    dump(sim/'scene.jsonc',{'id':'RFMovingQualification','scene-type':'UnrealNative',
        'actors':[{'type':'robot','name':name,'origin':{'xyz':xyz,'rpy-deg':'0 0 0'},'robot-config':cfg}
                  for name,xyz,cfg in [('Drone1','-20 0 -20','moving.jsonc'),('Drone2','20 0 -20','fixed.jsonc')]],
        'clock':{'type':'steppable','step-ns':3_000_000,'real-time-update-rate':3_000_000,'pause-on-start':True},
        'home-geo-point':{'latitude':47.641468,'longitude':-122.140165,'altitude':122.}})
    client=ProjectAirSimClient(address=args.address);client.connect()
    motion_task=None
    try:
        world=World(client,'scene.jsonc',sim_config_path=str(sim.resolve()))
        world.pause()
        tx=Drone(client,world,'Drone1');rx=Drone(client,world,'Drone2')
        tx.enable_api_control();tx.arm()
        command_origin=int(world.get_sim_time())
        motion_task=await tx.move_by_velocity_async(v_north=args.velocity, v_east=0,v_down=0,duration=5.)
        # Advance two simulated seconds to settle the flight controller before RF capture.
        world.continue_until_sim_time(int(world.get_sim_time())+2_001_000_000,wait_until_complete=True)
        await asyncio.sleep(0)
        origin=int(world.get_sim_time());fs=2_000_000;frequency=150_000
        scene=rt.load_scene(str(root/'benchmarks/scenes/ground.xml'))
        scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V')
        scene.rx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V')
        profile=PlutoSDRProfile(noise_enabled=False);scene.frequency=profile.carrier_hz
        scene.add(rt.Transmitter('tx0',position=[-20,0,20]));scene.add(rt.Receiver('rx0',position=[20,0,20]))
        # One second of history/lookahead, avoiding an artificial waveform onset.
        values=np.exp(2j*np.pi*frequency*np.arange(4_000_000)/fs)
        emitter=SDREmitter(SampledWaveform(values,fs,origin-1_000_000_000,boundary='zero'),
            transmit_power_w=.01,baseband_frequency_bounds_hz=(frequency,frequency))
        receiver=SDRNetworkReceiver(scene,{'tx0':emitter},profile,renderer='basis-cuda',
            continuous=True,max_depth=int(args.reflection),samples_per_link=2,
            path_solver='single-bounce' if args.reflection else 'first-order-scattering')
        channels=[]
        solver=receiver.solver
        def logged_solver(*positional,**keywords):
            paths=solver(*positional,**keywords)
            a,tau=paths.cir(num_time_steps=1,normalize_delays=False,out_type='numpy')
            a=a.reshape(-1);tau=tau.reshape(-1);doppler=paths.doppler.numpy().reshape(-1)
            valid=tau>=0
            channels.append({'coefficient_real':a[valid].real.tolist(),
                'coefficient_imag':a[valid].imag.tolist(),'delay_s':tau[valid].tolist(),
                'doppler_hz':doppler[valid].tolist()})
            return paths
        receiver.solver=logged_solver
        trajectory=[]
        class LoggedRobot:
            def __init__(self,robot,name): self.robot,self.name=robot,name
            def get_ground_truth_kinematics(self):
                message=self.robot.get_ground_truth_kinematics()
                trajectory.append({'radio':self.name,'sim_time_ns':int(world.get_sim_time()),'kinematics':message})
                return message
        provenance={'experiment':'fast-physics moving TX, stationary RX, '+('direct + specular ground' if args.reflection else 'direct path only'),
            'commanded_north_velocity_m_s':args.velocity,'settling_signal_seconds':2.001,
            'noise_enabled':False,'carrier_hz':profile.carrier_hz,'tone_hz':frequency,
            'source_robot_sha256':sha256(source.read_bytes()).hexdigest(),
            'backend':mi.variant(),'renderer':'basis-cuda','sionna_rt':rt.__version__,
            'max_depth':int(args.reflection),'antenna':'isotropic V','transmit_power_w':.01,
            'requested_window_ms':args.window_ms,'filter_sos':receiver.sos.tolist(),
            'impedance_ohm':profile.impedance_ohm,
            'runtime_source_commit':subprocess.check_output(['git','-C',str(args.runtime_source),'rev-parse','HEAD'],text=True).strip(),
            'rf_scene':scene_provenance(root/'benchmarks/scenes/ground.xml'),
            'sim_config_sha256':{p.name:sha256(p.read_bytes()).hexdigest() for p in sim.glob('*.jsonc')},
            'waveform_complex128_sha256':sha256(values.tobytes()).hexdigest(),
            'waveform_origin_ns':origin-1_000_000_000,'waveform_samples':len(values)}
        manifest=record(world,{'tx0':LoggedRobot(tx,'tx0'),'rx0':LoggedRobot(rx,'rx0')},receiver,
            args.output/'capture',updates=480//args.window_ms,advance_ns=args.window_ms*1_000_000,max_samples=100000,provenance=provenance)
        dump(args.output/'trajectory.json',trajectory)
        dump(args.output/'channels.json',channels)
        dump(args.output/'inspection.json',inspect(args.output/'capture'))
        # Let the server finish its five-second command before closing the RPC
        # socket. These post-capture physics ticks are outside recording timing.
        world.continue_until_sim_time(command_origin+5_100_000_000,wait_until_complete=True)
        command_result=await asyncio.wait_for(motion_task,timeout=10)
        codes=np.fromfile(args.output/'capture/rx0.sigmf-data',dtype='<i2').reshape(-1,2)
        iq=codes[:,0]+1j*codes[:,1];offset=0;rows=[]
        for index,row in enumerate(manifest['rows']):
            ptx,vtx,_=mount_kinematics(trajectory[2*index]['kinematics'])
            prx,vrx,_=mount_kinematics(trajectory[2*index+1]['kinematics'])
            direction=(prx-ptx)/np.linalg.norm(prx-ptx)
            expected=float(np.dot(vtx-vrx,direction)*profile.carrier_hz/299792458.)
            count=row['samples_per_receiver'];block=iq[offset:offset+count];offset+=count
            # Discard filter/window transition, demodulate known tone, then fit
            # unwrapped phase over 10 ms. This is not an FFT-bin peak estimate.
            measured=estimate_tone_offset(block,fs,frequency)
            rows.append({'sim_time_ns':row['sim_time_ns'],'tx_position_rf_m':ptx.tolist(),
                'tx_velocity_rf_m_s':vtx.tolist(),'expected_doppler_hz':expected,
                'measured_doppler_hz':measured,'error_hz':measured-expected})
        errors=np.array([r['error_hz'] for r in rows]);displacement=float(np.linalg.norm(np.array(rows[-1]['tx_position_rf_m'])-rows[0]['tx_position_rf_m']))
        clipping=json.loads((args.output/'capture/rx0.sigmf-meta').read_text())['captures']
        checks={'motion_exceeds_half_meter':displacement>.5,
            'doppler_sign_matches_command':all(r['expected_doppler_hz']*args.velocity>0 for r in rows),
            'no_adc_clipping':all(c['airsim_rf:clipped_component_fraction']==0 for c in clipping),
            'flight_command_completed':bool(command_result)}
        if not args.reflection:
            checks['doppler_error_below_half_hz']=bool(np.max(abs(errors))<.5)
        result={'status':'passed' if all(checks.values()) else 'failed','checks':checks,
            'scope':('moving Fast Physics recording; composite frequency is not direct-path Doppler' if args.reflection else
                'moving Fast Physics pose integration and within-window direct-path Doppler'),
            'signal_seconds_per_receiver':manifest['signal_seconds_per_receiver'],
            'wall_seconds_per_signal_second':manifest['wall_seconds_per_signal_second'],
            'tx_displacement_m':displacement,'maximum_absolute_doppler_error_hz':None if args.reflection else float(np.max(abs(errors))),
            'tolerance_hz':.5,'rows':rows}
        dump(args.output/'motion.json',result)
        print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
        if result['status']!='passed':raise RuntimeError('Motion qualification failed; inspect motion.json')
    finally:
        if motion_task is not None: motion_task.cancel()
        client.disconnect()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runtime-source',type=Path,default=Path('.deps/ProjectAirSim-runtime'))
    parser.add_argument('--address',default='127.0.0.1')
    parser.add_argument('--velocity',type=float,choices=(-3.,3.),default=3.)
    parser.add_argument('--pascal-compat',action='store_true')
    parser.add_argument('--window-ms',type=int,choices=(6,12,24,48),default=12)
    parser.add_argument('--reflection',action='store_true',help='Include the specular ground path, without diffuse scattering')
    asyncio.run(run(parser.parse_args()))
