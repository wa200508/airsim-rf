"""Single stepping owner: actual AirSim orbit -> Sionna -> ADC -> receiver transport."""
import argparse
import asyncio
import json
import secrets
from pathlib import Path
import socket
import time

import numpy as np
from .dashboard_scenario import ADVANCE_NS,FS,CARRIER,SPEED,RADIUS,ALTITUDE,atomic_json,waveform_window


async def run(args):
    import mitsuba as mi
    mi.set_variant('cuda_ad_mono_polarized')
    if args.pascal_compat:
        from .p100_compat import enable_pascal_compat
        enable_pascal_compat()
    import drjit as dr
    dr.set_thread_count(2)
    import sionna.rt as rt
    from projectairsim import ProjectAirSimClient,World,Drone
    from projectairsim.utils import unpack_image
    import cv2
    from .bridge import mount_kinematics,normalize_kinematics
    from .dashboard_view import queue_chase_camera_pose,radio_marker_glb
    from .dashboard_geometry import isolate_blocks_scene,require_rf_mesh_match,link_geometry
    from .dashboard_sync import commit_window,advance_after_commit
    from .source_recording import RecordingWriter
    from .geometry import read_bundle
    from .geometry_sync import AirSimGeometryBinding,spawn_placements
    from .sample_stream import SampleStreamWriter
    from .sampled_waveform import SampledWaveform
    from .sdr import SDREmitter,SDRNetworkReceiver,PlutoSDRProfile

    output=Path(args.run_dir);arrays=json.loads((output/'arrays.json').read_text())
    document,bundle,bindings=read_bundle(output/'bundle')
    if args.wait_for_mission:
        deadline=time.monotonic()+args.ready_timeout
        for port in (8989,8990):
            while True:
                try:
                    probe=socket.create_connection((args.address,port),timeout=.5);probe.close();break
                except OSError:
                    if time.monotonic()>deadline:raise RuntimeError('ProjectAirSim did not become reachable before RF startup')
                    await asyncio.sleep(.25)
    client=ProjectAirSimClient(address=args.address);client.connect()
    state={'status':'starting','sim_elapsed_s':0,'windows':0,'camera_frames':0,'backend':'CUDA / Sionna RT','propagation':'direct + first-order specular',
           'flight_controller':'native MoveOnPath, 3-degree circle waypoints, ForwardOnly absolute heading',
           'flight_command_wall_timeout_s':3600}
    atomic_json(output/'producer.json',state)
    writer=None;sock=None;motion=None;flight_client=None
    camera_counter=[0];last_camera=[0.];history=[]
    camera_session=args.recording_id or secrets.token_hex(8);camera_files=[];camera_history=[]
    state['presentation_session']=camera_session
    recording=RecordingWriter(output/'replays',camera_session,json.loads((output/'scenario.json').read_text()),
        args.duration,ADVANCE_NS,no_render=args.no_render,resume=args.recording_id is not None)
    (output/'camera').mkdir(exist_ok=True)
    site_positions=[site['center_rf_m'] for site in arrays['sites']]
    def image_received(_,message):
        try:
            image=unpack_image(message).copy()
            success,jpeg=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,82])
            if success:
                epoch=int(message['time_stamp']);key=camera_session+'-'+str(epoch)
                path=output/'camera'/(key+'.jpg');temp=path.with_suffix('.tmp')
                if path.exists():return  # Published URLs are immutable.
                temp.write_bytes(jpeg.tobytes());temp.replace(path)
                temp=output/'camera.tmp';temp.write_bytes(jpeg.tobytes());temp.replace(output/'camera.jpg')
                camera_counter[0]+=1;last_camera[0]=time.monotonic()
                metadata={'key':key,'sim_time_ns':epoch,'frames':camera_counter[0],
                    'position_ned_m':[message['pos_'+axis] for axis in ('x','y','z')],
                    'geometry_sha256':bundle['scene_sha256']}
                recording.camera(metadata,jpeg.tobytes())
                camera_history[:]=[frame for frame in camera_history if frame['key']!=key]
                camera_history.append(metadata);del camera_history[:-128]
                atomic_json(output/'camera.json',{**metadata,'history':list(camera_history)})
                if path in camera_files:camera_files.remove(path)
                camera_files.append(path)
                if len(camera_files)>128:camera_files.pop(0).unlink(missing_ok=True)
        except Exception as error:
            state['camera_error']=str(error)
            state['recording_error']=str(error)
    try:
        if args.wait_for_mission:
            from .preflight import gpu_check
            atomic_json(output/'gpu-preflight-input.json',{'rf_scene':'bundle/scene.xml'})
            check=gpu_check(output/'gpu-preflight-input.json',pascal_compat=args.pascal_compat)
            atomic_json(output/'gpu-preflight.json',check)
        world=World(client,'scene.jsonc',sim_config_path=str((output/'sim_config').resolve()));world.pause()
        alignment=isolate_blocks_scene(world)
        binding=AirSimGeometryBinding(document,bindings)
        # Presentation-only glTF appearance; RF dielectric settings remain in
        # the shared geometry document. A little emission keeps dynamically
        # imported meshes visible in the packaged map's baked lighting.
        for obj in binding.plan['objects']:
            terrain=obj['id']=='Terrain'
            obj['mesh']['base_color_rgba']=[.34,.48,.22,1.] if terrain else [.48,.32,.20,1.]
            obj['mesh']['emissive_rgb']=[.07,.10,.045] if terrain else [.12,.075,.035]
        spawn_placements(world,binding.plan)
        alignment['airsim']=binding.require_static_match(world,int(world.get_sim_time()))
        marker_pose=lambda p:{'frame_id':'DEFAULT_ID','translation':dict(zip(('x','y','z'),(np.asarray(p)*[1,-1,-1]).tolist())),'rotation':{'w':1.,'x':0.,'y':0.,'z':0.}}
        for i,position in enumerate(site_positions):
            name=f'Radio_RX_{i}'
            world.spawn_object_from_file(name,'gltf',radio_marker_glb([.2,.9,.85] if i==0 else [1.,.65,.15]),True,marker_pose(np.asarray(position)-[0,0,8]),[1,1,1],False)
        drone=Drone(client,world,'OrbitDrone')
        if not args.no_render:
            client.subscribe(drone.sensors['Chase']['scene_camera'],image_received)
        drone.enable_api_control();drone.arm()
        # Exercise the same camera RPC as the mission before advertising READY.
        # The following settling step lets Unreal apply the queued view and
        # produce the actual camera frame checked during preparation.
        if not args.no_render:
            initial=normalize_kinematics(drone.get_ground_truth_kinematics())
            position,_,_=mount_kinematics(initial)
            queue_chase_camera_pose(drone,position,site_positions,initial)
        settle=await drone.move_by_velocity_z_async(v_north=0,v_east=0,z=-ALTITUDE,duration=2.1,yaw_is_rate=False,yaw=-np.pi/2)
        world.continue_until_sim_time(int(world.get_sim_time())+2_001_000_000,wait_until_complete=True)
        await asyncio.sleep(.1)
        origin=int(world.get_sim_time())
        cycles=int(np.ceil(args.duration/(2*np.pi*RADIUS/SPEED)))+1
        angles=np.linspace(0,cycles*2*np.pi,cycles*120+1)
        path=[[float(RADIUS*np.cos(a)),float(-RADIUS*np.sin(a)),-ALTITUDE] for a in angles]
        # Long flight command has a separate services-only client: its deadline
        # is wall time, including intentional simulation pauses. Ordinary scene
        # RPCs retain the normal SDK deadline and one owner still steps time.
        flight_client=ProjectAirSimClient(address=args.address);flight_client.connect_services()
        flight_client.socket_services.recv_timeout=3_600_000
        flight_drone=Drone(flight_client,world,'OrbitDrone')
        motion=await flight_drone.move_on_path_async(path=path,velocity=SPEED,timeout_sec=args.duration+10,
            yaw_control_mode=1,yaw_is_rate=False,yaw=0,lookahead=12.,adaptive_lookahead=0.)
        await asyncio.sleep(0)
        scene=rt.load_scene(str(output/'bundle/scene.xml'),merge_shapes=False)
        alignment['sionna']=require_rf_mesh_match(scene,document)
        alignment['geometry_sha256']=bundle['scene_sha256'];atomic_json(output/'scene-alignment.json',alignment)
        state['geometry_sha256']=bundle['scene_sha256'];state['origin_ns']=origin
        scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V');scene.rx_array=scene.tx_array
        scene.add(rt.Transmitter('tx0',position=[250,0,ALTITUDE]))
        for site in arrays['sites']:
            for name,offset in zip(site['channels'],site['element_offsets_m']):
                scene.add(rt.Receiver(name,position=(np.asarray(site['center_rf_m'])+[0,offset,0]).tolist()))
        count=round(ADVANCE_NS*FS/1e9);samples,reference=waveform_window(origin,count,origin)
        receiver=SDRNetworkReceiver(scene,{'tx0':SDREmitter(SampledWaveform(samples,FS,reference,boundary='error'),transmit_power_w=.1,baseband_frequency_bounds_hz=(-100000,100000))},
            PlutoSDRProfile(noise_enabled=True),renderer='basis-cuda',continuous=True,path_solver='single-bounce',max_depth=1,samples_per_link=2,seed=20261021,path_diagnostics=True)
        def record_frame(epoch,position,captures):
            binding.require_static_match(world,epoch)
            row={'sim_time_ns':epoch,'sim_elapsed_s':(epoch-origin)*1e-9,'position_rf_m':position.tolist(),
                **link_geometry(document,arrays,position,receiver.last_path_diagnostics),
                'retained_paths_per_channel':[sum(c.retained_paths.values()) for c in captures.values()],
                'max_clipped_component_fraction':max(c.clipped_component_fraction for c in captures.values())}
            if history and history[-1]['sim_time_ns']==epoch:history[-1]=row
            else:history.append(row)
            del history[:-1000]
            return row
        deadline=time.monotonic()+args.ready_timeout
        while True:
            try:sock=socket.create_connection((args.iq_host,args.iq_port),timeout=2);break
            except OSError:
                if time.monotonic()>deadline:raise RuntimeError('Receiver ingress did not become ready')
                await asyncio.sleep(.25)
        sock.settimeout(120);writer=SampleStreamWriter(sock,carrier_hz=CARRIER)
        def stop_requested():
            return (output/'command.json').exists() and json.loads((output/'command.json').read_text()).get('stop',False)
        def send_captures(captures):
            for name,capture in captures.items():
                writer.send_samples(name,capture.adc_iq_volts,timestamp_ns=capture.sim_time_ns,
                    sample_rate_hz=capture.actual_sample_rate_hz,clipped_component_fraction=capture.clipped_component_fraction)
        async def save_source_frame():
            recording.source_frame(state)
        prepared_captures=None
        if args.wait_for_mission:
            # Exercise the actual configured scene, eight-channel block and data
            # plane before advertising READY. Reuse this initial window at T+0.
            epoch=int(world.get_sim_time())
            initial=normalize_kinematics(drone.get_ground_truth_kinematics())
            position,velocity,orientation=mount_kinematics(initial)
            scene.transmitters['tx0'].position=position.tolist()
            scene.transmitters['tx0'].velocity=velocity.tolist()
            scene.transmitters['tx0'].orientation=orientation.tolist()
            samples,reference=waveform_window(epoch,count,origin)
            receiver.emitters['tx0']=SDREmitter(SampledWaveform(samples,FS,reference,boundary='error'),
                transmit_power_w=.1,baseband_frequency_bounds_hz=(-100000,100000))
            prepared_captures=receiver.capture(epoch,num_samples=count)
            row=record_frame(epoch,position,prepared_captures)
            send_captures(prepared_captures)
            if not (await commit_window(writer,stop_requested))[0]:
                recording.status('stopped');return
            row.update(windows=1,velocity_rf_m_s=velocity.tolist(),camera_frames=camera_counter[0],
                wall_elapsed_s=0.,simulation_speed=0.,raw_payload_bytes=count*8*8)
            if not args.no_render:
                deadline=time.monotonic()+30
                while not camera_counter[0] and time.monotonic()<deadline:await asyncio.sleep(.1)
                if not camera_counter[0]:raise RuntimeError('No actual ProjectAirSim camera frame during preparation')
            if state.get('recording_error'):raise RuntimeError('Camera recording failed: '+state['recording_error'])
            state.update(row);state.update(status='ready',history=list(history),camera_frames=camera_counter[0],gpu_preflight='passed',mission_started=False)
            atomic_json(output/'producer.json',state)
            await save_source_frame();recording.status('ready')
            while True:
                command=json.loads((output/'command.json').read_text())
                if command.get('stop'):
                    state.update(status='stopped');atomic_json(output/'producer.json',state);recording.status('stopped');return
                if command.get('start'):break
                await asyncio.sleep(.2)
        started=time.monotonic()
        recording.status('running')
        for index in range(max(1,round(args.duration*1e9/ADVANCE_NS))):
            while True:
                command=json.loads((output/'command.json').read_text()) if (output/'command.json').exists() else {}
                if command.get('stop'):break
                if not command.get('paused'):break
                state['status']='paused';atomic_json(output/'producer.json',state)
                if recording.manifest['status']!='paused':recording.status('paused')
                await asyncio.sleep(.2)
            if command.get('stop'):break
            if recording.manifest['status']=='paused':recording.status('running')
            if state.get('recording_error'):raise RuntimeError('Camera recording failed: '+state['recording_error'])
            if motion.done():motion.result()
            epoch=int(world.get_sim_time());kinematics=normalize_kinematics(drone.get_ground_truth_kinematics())
            position,velocity,orientation=mount_kinematics(kinematics)
            if not args.no_render:
                queue_chase_camera_pose(drone,position,site_positions,kinematics)
            scene.transmitters['tx0'].position=position.tolist();scene.transmitters['tx0'].velocity=velocity.tolist();scene.transmitters['tx0'].orientation=orientation.tolist()
            samples,reference=waveform_window(epoch,count,origin)
            receiver.emitters['tx0']=SDREmitter(SampledWaveform(samples,FS,reference,boundary='error'),transmit_power_w=.1,baseband_frequency_bounds_hz=(-100000,100000))
            if index==0 and prepared_captures is not None:
                captures=prepared_captures
            else:
                captures=receiver.capture(epoch,num_samples=count)
                send_captures(captures)
            row=record_frame(epoch,position,captures)
            elapsed=(epoch-origin)*1e-9
            state.update(row)
            state.update(status='running',sim_elapsed_s=elapsed,windows=index+1,sim_time_ns=epoch,
                position_rf_m=position.tolist(),velocity_rf_m_s=velocity.tolist(),
                retained_paths={name:cap.retained_paths for name,cap in captures.items()},history=list(history),
                wall_elapsed_s=time.monotonic()-started,simulation_speed=elapsed/max(time.monotonic()-started,.001),
                camera_frames=camera_counter[0],camera_age_s=None if not last_camera[0] else time.monotonic()-last_camera[0],
                camera_framing='Timestamped raw Chase image; physical RX beacons; no projected labels through terrain',
                geometry_sha256=bundle['scene_sha256'],raw_payload_bytes=(index+1)*count*8*8)
            # Retain measurements for this epoch, including counters and speed;
            # the host must not mix them with a newer producer state.
            row.update({key:state[key] for key in ('windows','velocity_rf_m_s','retained_paths',
                'wall_elapsed_s','simulation_speed','camera_frames','camera_age_s','raw_payload_bytes')})
            atomic_json(output/'producer.json',state)
            if index==0 and prepared_captures is not None:
                # Initial acquisition was already committed before READY.
                await save_source_frame()
                world.continue_until_sim_time(epoch+ADVANCE_NS,wait_until_complete=True)
            elif not await advance_after_commit(world,writer,epoch,ADVANCE_NS,stop_requested,
                on_committed=save_source_frame):break
            await asyncio.sleep(0)
        totals={} if writer.closed else writer.finish();writer=None
        state['acknowledged_sample_totals']=totals
        # Preserve source telemetry even if stop interrupted the stream commit.
        # Only the observer decides whether a matching application result exists.
        if history and not (recording.path/'frames'/f'{state["sim_time_ns"]}.json').is_file():
            await save_source_frame()
        if not args.no_render:
            # Give already-triggered asynchronous camera captures a chance to
            # arrive for the final RF epoch. No extra flight time is simulated.
            deadline=time.monotonic()+5
            while history and not any(abs(c['sim_time_ns']-history[-1]['sim_time_ns'])<=60_000_000 for c in camera_history):
                if time.monotonic()>=deadline:break
                await asyncio.sleep(.05)
        state.update(status='stopped' if stop_requested() else 'complete',camera_frames=camera_counter[0]);atomic_json(output/'producer.json',state)
        recording.status(state['status'])
        drone.cancel_last_task()
        world.continue_until_sim_time(int(world.get_sim_time())+3_000_000,wait_until_complete=True)
        try:await asyncio.wait_for(asyncio.shield(motion),timeout=2)
        except asyncio.TimeoutError:pass
    except BaseException as error:
        recording.status('failed',error=str(error))
        state.update(status='failed',error=str(error));atomic_json(output/'producer.json',state);raise
    finally:
        if sock:sock.close()
        if flight_client:flight_client.disconnect()
        client.disconnect()



def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=120);parser.add_argument('--address',default='127.0.0.1')
    parser.add_argument('--iq-host',default='127.0.0.1');parser.add_argument('--iq-port',type=int,default=8811)
    parser.add_argument('--recording-id',help='Coordinator-prepared source recording ID')
    parser.add_argument('--pascal-compat',action='store_true')
    parser.add_argument('--wait-for-mission',action='store_true')
    parser.add_argument('--ready-timeout',type=float,default=600)
    parser.add_argument('--no-render',action='store_true');args=parser.parse_args()
    if not 0<args.duration<=3600:parser.error('duration must be in (0,3600] seconds')
    asyncio.run(run(args))


if __name__=='__main__':main()
