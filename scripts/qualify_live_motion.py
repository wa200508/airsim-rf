"""Bounded real Runtime flight + direct/specular/diffuse SDR qualification.

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


def receiver_lateral_motion(velocities, *, turning=False):
    """Turns can cross zero lateral speed; straight flight must sustain it.

    RMS over the sampled windows retains the 0.1 m/s activity threshold without
    rejecting a turning trajectory merely because its lateral direction changes.
    Independent pose/heading checks remain in analyze_turning_mounts.py.
    """
    lateral=np.asarray(velocities,dtype=float)[:,1]
    rms=float(np.sqrt(np.mean(lateral**2)))
    return bool(rms>.1 if turning else np.all(abs(lateral)>.1)),rms


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
    from airsim_rf.geometry import export_sionna_geometry, geometry_digest
    from airsim_rf.geometry_sync import AirSimGeometryBinding, spawn_placements, nearest_intersections
    from airsim_rf.usd_geometry import import_usd

    root=Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=False)
    geometry_binding=None
    if args.shared_geometry:
        asset=root/'examples/geometry'/args.shared_geometry
        geometry_profile=json.loads(asset.with_suffix('.rf.json').read_text())
        geometry_profile['stage_meters_to_ned_m'][2][3]=-100
        dump(args.output/'geometry-profile.json',geometry_profile)
        geometry,geometry_provenance,bindings=import_usd(asset.with_suffix('.usda'),args.output/'geometry-profile.json')
        export_sionna_geometry(geometry,args.output/'bundle',provenance=geometry_provenance,bindings=bindings)
        geometry_binding=AirSimGeometryBinding(geometry,bindings)
    sim=args.output/'sim_config';sim.mkdir()
    source=args.runtime_source/'client/python/example_user_scripts/sim_config/robot_quadrotor_fastphysics.jsonc'
    robot=commentjson.loads(source.read_text())
    robot['sensors']=[s for s in robot['sensors'] if s['type']!='camera']
    dump(sim/'moving.jsonc',robot)
    dump(sim/'fixed.jsonc',{'physics-type':'non-physics','links':[{'name':'Frame','collision':{'enabled':False}}],'sensors':[]})
    dump(sim/'scene.jsonc',{'id':'RFMovingQualification','scene-type':'UnrealNative',
        'actors':[{'type':'robot','name':name,'origin':{'xyz':xyz,'rpy-deg':'0 0 0'},'robot-config':cfg}
                  for name,xyz,cfg in [('Drone1',f'-20 0 {-120 if args.shared_geometry else -20}','moving.jsonc'),
                    ('Drone2',f'20 0 {-120 if args.shared_geometry else -20}','moving.jsonc' if args.moving_receiver else 'fixed.jsonc')]],
        'clock':{'type':'steppable','step-ns':3_000_000,'real-time-update-rate':3_000_000,'pause-on-start':True},
        'home-geo-point':{'latitude':47.641468,'longitude':-122.140165,'altitude':122.}})
    client=ProjectAirSimClient(address=args.address);client.connect()
    motion_task=None;receiver_task=None
    try:
        world=World(client,'scene.jsonc',sim_config_path=str(sim.resolve()))
        world.pause()
        if geometry_binding is not None:
            spawn_placements(world,geometry_binding.plan)
            geometry_binding.require_static_match(world,int(world.get_sim_time()))
        tx=Drone(client,world,'Drone1');rx=Drone(client,world,'Drone2')
        tx.enable_api_control();tx.arm()
        command_origin=int(world.get_sim_time())
        command_duration=max(5.,2.001+args.duration_ms/1000+1.)
        if args.turning_mounts:
            motion_task=await tx.move_by_velocity_body_frame_async(v_forward=args.velocity,v_right=0,v_down=0,duration=command_duration,yaw_is_rate=True,yaw=.7)
        else:
            motion_task=await tx.move_by_velocity_async(v_north=args.velocity, v_east=0,v_down=0,duration=command_duration)
        if args.moving_receiver:
            rx.enable_api_control();rx.arm()
            if args.turning_mounts:
                receiver_task=await rx.move_by_velocity_body_frame_async(v_forward=-args.velocity,v_right=1.,v_down=0,duration=command_duration,yaw_is_rate=True,yaw=-.5)
            else:
                receiver_task=await rx.move_by_velocity_async(v_north=-args.velocity,v_east=1.,v_down=0,duration=command_duration)
        # Advance two simulated seconds to settle the flight controller before RF capture.
        world.continue_until_sim_time(int(world.get_sim_time())+2_001_000_000,wait_until_complete=True)
        await asyncio.sleep(0)
        origin=int(world.get_sim_time());fs=2_000_000;frequency=150_000
        rf_scene=root/'benchmarks/scenes/ground.xml'
        if args.occlusion_test and not args.shared_geometry:
            # A thin RF-only screen intersects the moving link, not either flight path.
            # Runtime has no matching screen collision geometry.
            rf_scene=args.output/'screen.xml'
            (args.output/'screen.ply').write_text('ply\nformat ascii 1.0\nelement vertex 4\nproperty float x\nproperty float y\nproperty float z\nelement face 2\nproperty list uchar int vertex_indices\nend_header\n0 -0.75 0\n0 -0.65 0\n0 -0.65 30\n0 -0.75 30\n3 0 1 2\n3 0 2 3\n')
            rf_scene.write_text('<scene version="2.1.0"><bsdf type="radio-material" id="screen-material"><float name="relative_permittivity" value="5"/></bsdf><shape type="ply" id="screen"><string name="filename" value="screen.ply"/><ref id="screen-material" name="bsdf"/></shape></scene>')
        if args.shared_geometry:
            rf_scene=args.output/'bundle/scene.xml'
        scene=rt.load_scene(str(rf_scene),merge_shapes=False) if args.shared_geometry else rt.load_scene(str(rf_scene))
        scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern=args.antenna_pattern,polarization='V')
        scene.rx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern=args.antenna_pattern,polarization='V')
        profile=PlutoSDRProfile(noise_enabled=False);scene.frequency=profile.carrier_hz
        scene.add(rt.Transmitter('tx0',position=[-20,0,20]));scene.add(rt.Receiver('rx0',position=[20,0,20]))
        # One second of history/lookahead, avoiding an artificial waveform onset.
        waveform_samples=round(max(2.,args.duration_ms/1000+1.1)*fs)
        values=np.exp(2j*np.pi*frequency*np.arange(waveform_samples)/fs)
        emitter=SDREmitter(SampledWaveform(values,fs,origin-1_000_000_000,boundary='zero'),
            transmit_power_w=args.transmit_power_w,baseband_frequency_bounds_hz=(frequency,frequency))
        receiver=SDRNetworkReceiver(scene,{'tx0':emitter},profile,renderer='basis-cuda',
            continuous=True,max_depth=int(args.reflection or bool(args.diffuse)),
            samples_per_link=args.samples_per_link if args.diffuse else 2,
            surface_sampling=args.diffuse=='surface',
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
        mounts={'tx0':[.6,.2,.1],'rx0':[-.4,.3,-.1]} if args.turning_mounts else {'tx0':[0,0,0],'rx0':[0,0,0]}
        provenance={'mounts_body_m':mounts,'turning_mounts':args.turning_mounts,
            'qualification_script_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
            'velocity_command_frame':'body' if args.turning_mounts else 'NED',
            'commanded_yaw_rates_rad_s':{'tx0':.7,'rx0':-.5} if args.turning_mounts else {},'experiment':'fast-physics moving TX, '+('moving RX, ' if args.moving_receiver else 'stationary RX, ')+('direct + specular + '+args.diffuse+' diffuse' if args.diffuse else 'direct + specular ground' if args.reflection else 'direct path only'),
            'commanded_rx_velocity_m_s':[-args.velocity,1.,0.] if args.moving_receiver else [0.,0.,0.],
            'commanded_north_velocity_m_s':args.velocity if not args.turning_mounts else None,
            'commanded_forward_velocity_m_s':args.velocity if args.turning_mounts else None,'settling_signal_seconds':2.001,
            'noise_enabled':False,'carrier_hz':profile.carrier_hz,'tone_hz':frequency,
            'source_robot_sha256':sha256(source.read_bytes()).hexdigest(),
            'backend':mi.variant(),'renderer':'basis-cuda','sionna_rt':rt.__version__,
            'max_depth':int(args.reflection or bool(args.diffuse)),
            'diffuse_mode':args.diffuse,'samples_per_link':args.samples_per_link if args.diffuse else 2,'antenna':args.antenna_pattern+' V','transmit_power_w':args.transmit_power_w,
            'requested_window_ms':args.window_ms,'requested_capture_ms':args.duration_ms,
            'command_duration_s':command_duration,'filter_sos':receiver.sos.tolist(),
            'impedance_ohm':profile.impedance_ohm,
            'runtime_source_commit':subprocess.check_output(['git','-C',str(args.runtime_source),'rev-parse','HEAD'],text=True).strip(),
            'rf_scene':scene_provenance(rf_scene),'rf_only_screen':args.occlusion_test and not bool(args.shared_geometry),
            'geometry_sha256':geometry_digest(geometry) if geometry_binding is not None else None,
            'shared_obstruction':args.shared_geometry=='shared-mesh-turn-screen',
            'sim_config_sha256':{p.name:sha256(p.read_bytes()).hexdigest() for p in sim.glob('*.jsonc')},
            'waveform_complex128_sha256':sha256(values.tobytes()).hexdigest(),
            'waveform_origin_ns':origin-1_000_000_000,'waveform_samples':len(values)}
        manifest=record(world,{'tx0':LoggedRobot(tx,'tx0'),'rx0':LoggedRobot(rx,'rx0')},receiver,
            args.output/'capture',updates=args.duration_ms//args.window_ms,advance_ns=args.window_ms*1_000_000,max_samples=100000,provenance=provenance,mounts_body_m=mounts,geometry_binding=geometry_binding)
        dump(args.output/'trajectory.json',trajectory)
        dump(args.output/'channels.json',channels)
        dump(args.output/'inspection.json',inspect(args.output/'capture'))
        # Let the server finish its bounded command before closing the RPC
        # socket. These post-capture physics ticks are outside recording timing.
        world.continue_until_sim_time(command_origin+round((command_duration+.1)*1e9),wait_until_complete=True)
        command_result=await asyncio.wait_for(motion_task,timeout=10)
        receiver_command_result=await asyncio.wait_for(receiver_task,timeout=10) if receiver_task is not None else True
        codes=np.fromfile(args.output/'capture/rx0.sigmf-data',dtype='<i2').reshape(-1,2)
        iq=codes[:,0]+1j*codes[:,1];offset=0;rows=[]
        for index,row in enumerate(manifest['rows']):
            ptx,vtx,_=mount_kinematics(trajectory[2*index]['kinematics'],mounts['tx0'])
            prx,vrx,_=mount_kinematics(trajectory[2*index+1]['kinematics'],mounts['rx0'])
            direction=(prx-ptx)/np.linalg.norm(prx-ptx)
            expected=float(np.dot(vtx-vrx,direction)*profile.carrier_hz/299792458.)
            count=row['samples_per_receiver'];block=iq[offset:offset+count];offset+=count
            # Discard filter/window transition, demodulate known tone, then fit
            # unwrapped phase inside the window. This is not an FFT-bin peak estimate.
            measured=estimate_tone_offset(block,fs,frequency) if not args.occlusion_test else None
            rows.append({'sim_time_ns':row['sim_time_ns'],'tx_position_rf_m':ptx.tolist(),
                'rx_position_rf_m':prx.tolist(),'rx_velocity_rf_m_s':vrx.tolist(),
                'tx_velocity_rf_m_s':vtx.tolist(),'expected_doppler_hz':expected,
                'measured_doppler_hz':measured,'error_hz':measured-expected if measured is not None else None})
        errors=np.array([r['error_hz'] for r in rows]);displacement=float(np.linalg.norm(np.array(rows[-1]['tx_position_rf_m'])-rows[0]['tx_position_rf_m']))
        receiver_displacement=float(np.linalg.norm(np.array(rows[-1]['rx_position_rf_m'])-rows[0]['rx_position_rf_m']))
        lateral_ok,lateral_rms=receiver_lateral_motion(
            [r['rx_velocity_rf_m_s'] for r in rows],turning=args.turning_mounts)
        clipping=json.loads((args.output/'capture/rx0.sigmf-meta').read_text())['captures']
        checks={'motion_exceeds_half_meter':displacement>.5,
            'doppler_sign_matches_command':all(r['expected_doppler_hz']*args.velocity>0 for r in rows),
            'no_adc_clipping':all(c['airsim_rf:clipped_component_fraction']==0 for c in clipping),
            'flight_command_completed':bool(command_result) and bool(receiver_command_result)}
        if args.turning_mounts:
            del checks['doppler_sign_matches_command']
        if args.moving_receiver:
            checks['receiver_motion_exceeds_half_meter']=receiver_displacement>.5
            checks['receiver_has_lateral_motion']=lateral_ok
        if not (args.reflection or args.diffuse or args.occlusion_test):
            checks['doppler_error_below_half_hz']=bool(np.max(abs(errors))<.5)
        if args.occlusion_test:
            visible=[];observed=[]
            for row,channel in zip(rows,channels):
                pt=np.array(row['tx_position_rf_m']);pr=np.array(row['rx_position_rf_m'])
                fraction=-pt[0]/(pr[0]-pt[0]);hit=pt+fraction*(pr-pt)
                visible.append(not (0<fraction<1 and -.75<=hit[1]<=-.65 and (100 if args.shared_geometry else 0)<=hit[2]<=(130 if args.shared_geometry else 30)))
                observed.append(len(channel['delay_s']))
            checks['visibility_matches_geometric_screen']=observed==[int(v) for v in visible]
            checks['path_disappears_and_returns']=sum(a!=b for a,b in zip(visible,visible[1:]))==2
        if geometry_binding is not None:
            independent=[];direct_matches=[];ground_matches=[]
            for row,channel in zip(rows,channels):
                txpos=np.asarray(row['tx_position_rf_m']);rxpos=np.asarray(row['rx_position_rf_m'])
                vector=rxpos-txpos;distance=np.linalg.norm(vector)
                hit=nearest_intersections(geometry,[txpos*[1,-1,-1]],[vector*[1,-1,-1]],maximum_distance_m=distance)[0]
                expected_visible=hit is None
                lengths=np.asarray(channel['delay_s'])*299792458.
                direct_present=bool(np.any(abs(lengths-distance)<.001))
                independent.append(expected_visible)
                direct_matches.append(direct_present==expected_visible)
                image=txpos.copy();image[2]=200-txpos[2]
                ground_distance=np.linalg.norm(rxpos-image)
                ground_matches.append(bool(np.any(abs(lengths-ground_distance)<.001)))
            checks['direct_visibility_matches_independent_shared_triangles']=all(direct_matches)
            checks['geometry_identity_at_each_recorded_epoch']=all(
                r['geometry']['geometry_sha256']==provenance['geometry_sha256'] and r['geometry']['sim_time_ns']==r['sim_time_ns'] for r in manifest['rows'])
            if args.reflection:
                checks['analytic_ground_reflection_present_each_window']=all(ground_matches)
            if args.occlusion_test:
                checks['shared_geometry_obstruction_disappears_and_returns']=sum(a!=b for a,b in zip(independent,independent[1:]))==2
            if args.shared_geometry=='shared-mesh-turn-screen':
                checks['turning_direct_path_disappears_and_returns']=sum(a!=b for a,b in zip(independent,independent[1:]))==2
            dump(args.output/'geometry-checks.json',{'checks':checks,'direct_visible':independent,
                'ground_reflection_present':ground_matches,'geometry_sha256':provenance['geometry_sha256']})
        result={'status':'passed' if all(checks.values()) else 'failed','checks':checks,
            'scope':('shared USD/GLB environment with real flight, static guards and independent triangle visibility' if args.shared_geometry else 'RF-only screen visibility during real flight; no Runtime screen collisions' if args.occlusion_test else 'moving Fast Physics recording; composite frequency is not direct-path Doppler' if (args.reflection or args.diffuse) else
                'moving Fast Physics pose integration and within-window direct-path Doppler'),
            'signal_seconds_per_receiver':manifest['signal_seconds_per_receiver'],
            'wall_seconds_per_signal_second':manifest['wall_seconds_per_signal_second'],
            'tx_displacement_m':displacement,'maximum_absolute_doppler_error_hz':None if (args.reflection or args.diffuse or args.occlusion_test) else float(np.max(abs(errors))),
            'rx_displacement_m':receiver_displacement,
            'rx_lateral_speed_rms_m_s':lateral_rms,
            'rx_lateral_motion_rule':'rms_above_0.1m_s' if args.turning_mounts else 'every_window_above_0.1m_s',
            'tolerance_hz':.5,'rows':rows}
        dump(args.output/'motion.json',result)
        print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
        if result['status']!='passed':raise RuntimeError('Motion qualification failed; inspect motion.json')
    finally:
        if motion_task is not None: motion_task.cancel()
        if receiver_task is not None: receiver_task.cancel()
        client.disconnect()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runtime-source',type=Path,default=Path('.deps/ProjectAirSim-runtime'))
    parser.add_argument('--address',default='127.0.0.1')
    parser.add_argument('--velocity',type=float,choices=(-3.,3.),default=3.)
    parser.add_argument('--pascal-compat',action='store_true')
    parser.add_argument('--shared-geometry',choices=('shared-mesh-world','shared-mesh-screen','shared-mesh-turn-screen'),help='Shared USD asset, generated Blocks collision meshes and RF bundle')
    parser.add_argument('--duration-ms',type=int,default=480,help='Positive capture duration, divisible by --window-ms')
    parser.add_argument('--window-ms',type=int,choices=(6,12,24,48),default=12)
    modes=parser.add_mutually_exclusive_group()
    parser.add_argument('--turning-mounts',action='store_true',help='Body-frame velocity with yaw rates and nonzero radio offsets; requires --moving-receiver')
    modes.add_argument('--occlusion-test',action='store_true',help='Direct path crosses RF-only screen; requires --moving-receiver')
    modes.add_argument('--diffuse',choices=('angular','surface'),help='Include first-order diffuse paths; analyze with analyze_diffuse_iq.py')
    parser.add_argument('--transmit-power-w',type=float,default=.01)
    parser.add_argument('--antenna-pattern',choices=('iso','tr38901'),default='iso')
    parser.add_argument('--samples-per-link',type=int,default=1024)
    modes.add_argument('--reflection',action='store_true',help='Include the specular ground path, without diffuse scattering')
    parser.add_argument('--moving-receiver',action='store_true',help='Fly RX with opposite north velocity and +1 m/s east command')
    args=parser.parse_args()
    if (args.occlusion_test or args.turning_mounts) and not args.moving_receiver:parser.error('--occlusion-test/--turning-mounts requires --moving-receiver')
    if args.duration_ms<args.window_ms or args.duration_ms%args.window_ms:parser.error('--duration-ms must be positive and divisible by --window-ms')
    if args.occlusion_test and args.turning_mounts:parser.error('--occlusion-test uses the straight-flight reference; omit --turning-mounts')
    if args.occlusion_test and args.shared_geometry and args.shared_geometry!='shared-mesh-screen':
        parser.error('Shared occlusion qualification requires --shared-geometry shared-mesh-screen')
    if args.shared_geometry=='shared-mesh-turn-screen' and not (args.turning_mounts and args.reflection):
        parser.error('shared-mesh-turn-screen requires --turning-mounts --reflection')
    if not np.isfinite(args.transmit_power_w) or args.transmit_power_w<=0:parser.error('--transmit-power-w must be finite and positive')
    asyncio.run(run(args))
