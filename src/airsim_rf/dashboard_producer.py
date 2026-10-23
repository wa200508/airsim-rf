"""Single stepping owner: actual AirSim orbit -> Sionna -> ADC -> receiver transport."""
import argparse
import asyncio
import json
import secrets
from pathlib import Path
import socket
import time

import numpy as np
from .dashboard_scenario import atomic_json,WaveformSource,flight_path,create_receiver,emitters_for_window


async def run(args):
    output=Path(args.run_dir)
    config=json.loads((output/'runtime.json').read_text())
    radio=config['radios'];camera=config['camera'];mission=config['mission']
    FS=radio['sample_rate_hz'];CARRIER=radio['carrier_hz'];ADVANCE_NS=mission['rf_update_ns']
    actors=config['flight']['actors'];radar_mode=radio.get('mode')=='fmcw-radar'
    primary_tx=(radio['radar']['targets'][0].get('id') or radio['radar']['targets'][0]['actor']) if radar_mode else radio['transmitters'][0]['id']
    num_channels=sum(len(site['channels']) for site in radio['sites'])
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
    from .dashboard_view import (queue_chase_camera_pose,relative_camera_pose,camera_labels,
        radio_marker_glb,ground_target_placements)
    from .dashboard_geometry import isolate_blocks_scene,require_rf_mesh_match,link_geometry
    from .dashboard_sync import commit_window,advance_after_commit
    from .source_recording import RecordingWriter
    from .geometry import read_bundle
    from .geometry_sync import AirSimGeometryBinding,spawn_placements
    from .sample_stream import SampleStreamWriter
    from .sample_recording import SampleRecordingWriter
    from .sample_stream import SampleBlock

    arrays=json.loads((output/'arrays.json').read_text())
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
    state={'status':'starting','sim_elapsed_s':0,'windows':0,'camera_frames':0,'backend':'CUDA / Sionna RT','propagation':radio['propagation'],
           'flight_controller':'scenario flight plans, native ProjectAirSim controller',
           'flight_command_wall_timeout_s':3600}
    atomic_json(output/'producer.json',state)
    writer=None;sock=None;motions=[];flight_client=None;radio_server=None
    camera_counter=[0];last_camera=[0.];history=[]
    camera_mounts=[]
    camera_session=args.recording_id or secrets.token_hex(8);camera_files=[];camera_history=[]
    state['presentation_session']=camera_session
    recording=RecordingWriter(output/'replays',camera_session,json.loads((output/'scenario.json').read_text()),
        args.duration,ADVANCE_NS,no_render=args.no_render,resume=args.recording_id is not None)
    iq_recording=None
    (output/'camera').mkdir(exist_ok=True)
    site_positions=[site['center_rf_m'] for site in arrays['sites']]
    def queue_view(position,kinematics):
        if radar_mode:
            from .dashboard_radar import target_states
            readback={t['actor']:normalize_kinematics(drones[t['actor']].get_ground_truth_kinematics()) for t in radio['radar']['targets'] if 'actor' in t}
            anchors=[list(t.position_m) for t in target_states(radio['radar'],readback)]
        else:anchors=site_positions
        eye,rotation=queue_chase_camera_pose(drone,position,anchors,kinematics,
            sensor=camera['sensor'],distance_m=camera['distance_m'],elevation_bias=camera['elevation_bias'])
        camera_mounts.append((int(world.get_sim_time()),relative_camera_pose(eye,rotation,kinematics),anchors))
        del camera_mounts[:-128]
    def image_received(_,message):
        try:
            image=unpack_image(message).copy()
            epoch=int(message['time_stamp'])
            view=next(((pose,anchors) for sent,pose,anchors in reversed(camera_mounts) if sent<epoch),None)
            mount=view[0] if view is not None else None
            labels=camera_labels(message,mount,view[1],document,fov_deg=camera['fov_deg'],
                receiver_labels=[t.get('id') or t['actor'] for t in radio['radar']['targets']] if radar_mode else None,
                platform_label='RADAR / DRONE' if radar_mode else 'TX / DRONE' if any(tx['actor']==camera['actor'] for tx in radio['transmitters']) else camera['actor']) if mount is not None and camera['labels'] else []
            height,width=image.shape[:2]
            for label in labels:
                x,y=round(label['x']),round(label['y']);color=tuple(reversed(label['color_rgb']))
                cv2.circle(image,(x,y),6,color,2)
                anchor=(max(5,min(width-150,x+10)),max(20,min(height-8,y-12)))
                cv2.putText(image,label['text'],anchor,cv2.FONT_HERSHEY_SIMPLEX,.5,(5,10,15),4)
                cv2.putText(image,label['text'],anchor,cv2.FONT_HERSHEY_SIMPLEX,.5,color,1,cv2.LINE_AA)
            success,jpeg=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,82])
            if success:
                key=camera_session+'-'+str(epoch)
                path=output/'camera'/(key+'.jpg');temp=path.with_suffix('.tmp')
                if path.exists():return  # Published URLs are immutable.
                temp.write_bytes(jpeg.tobytes());temp.replace(path)
                temp=output/'camera.tmp';temp.write_bytes(jpeg.tobytes());temp.replace(output/'camera.jpg')
                camera_counter[0]+=1;last_camera[0]=time.monotonic()
                metadata={'key':key,'sim_time_ns':epoch,'frames':camera_counter[0],
                    'position_ned_m':[message['pos_'+axis] for axis in ('x','y','z')],
                    'labels':labels,
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
        if mission.get('record_iq',True):
            iq_recording=SampleRecordingWriter(recording.path/'iq',arrays)
            state['iq_recording']='iq'
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
            obj['mesh']['base_color_rgba']=config['appearance']['terrain_base_color_rgba']
            obj['mesh']['emissive_rgb']=config['appearance']['terrain_emissive_rgb']
        spawn_placements(world,binding.plan)
        alignment['airsim']=binding.require_static_match(world,int(world.get_sim_time()))
        marker_pose=lambda p:{'frame_id':'DEFAULT_ID','translation':dict(zip(('x','y','z'),(np.asarray(p)*[1,-1,-1]).tolist())),'rotation':{'w':1.,'x':0.,'y':0.,'z':0.}}
        for i,position in enumerate([] if radar_mode else site_positions):
            name=f'Radio_RX_{i}'
            world.spawn_object_from_file(name,'gltf',radio_marker_glb([.2,.9,.85] if i==0 else [1.,.65,.15]),True,marker_pose(np.asarray(position)-[0,0,8]),[1,1,1],False)
        if radar_mode:spawn_placements(world,ground_target_placements(radio['radar']['targets']))
        drones={actor['id']:Drone(client,world,actor['id']) for actor in actors}
        drone=drones[camera['actor']]
        if not args.no_render:
            client.subscribe(drone.sensors[camera['sensor']]['scene_camera'],image_received)
        for platform in drones.values():platform.enable_api_control();platform.arm()
        # Exercise the same camera RPC as the mission before advertising READY.
        # The following settling step lets Unreal apply the queued view and
        # produce the actual camera frame checked during preparation.
        if not args.no_render:
            initial=normalize_kinematics(drone.get_ground_truth_kinematics())
            position,_,_=mount_kinematics(initial)
            queue_view(position,initial)
        for actor in actors:
            await drones[actor['id']].move_by_velocity_z_async(v_north=0,v_east=0,z=-actor['position_rf_m'][2],
                duration=max(actor['settle_s'],.01)+.1,yaw_is_rate=False,yaw=-np.deg2rad(actor['yaw_deg']))
        step=mission['physics_step_ns']
        settle_ns=int(np.ceil(max(max(actor['settle_s'] for actor in actors),camera['capture_interval_s'])*1e9/step))*step
        if settle_ns:world.continue_until_sim_time(int(world.get_sim_time())+settle_ns,wait_until_complete=True)
        await asyncio.sleep(.1)
        origin=int(world.get_sim_time())
        # Flight command deadlines include intentional wall-time pauses. Only
        # this source process owns physics stepping, across all declared actors.
        flight_client=ProjectAirSimClient(address=args.address);flight_client.connect_services()
        flight_client.socket_services.recv_timeout=3_600_000
        for actor in actors:
            platform=Drone(flight_client,world,actor['id']);flight=actor['flight']
            path=flight_path(actor,args.duration)
            if path:
                task=await platform.move_on_path_async(path=(np.asarray(path)*[1,-1,-1]).tolist(),
                    velocity=flight['speed_m_s'],timeout_sec=args.duration+10,yaw_control_mode=1,
                    yaw_is_rate=False,yaw=0,lookahead=flight['lookahead_m'],adaptive_lookahead=flight['adaptive_lookahead'])
            else:
                task=await platform.move_by_velocity_z_async(v_north=0,v_east=0,z=-actor['position_rf_m'][2],
                    duration=args.duration+10,yaw_is_rate=False,yaw=-np.deg2rad(actor['yaw_deg']))
            motions.append((platform,task))
        await asyncio.sleep(0)
        scene=rt.load_scene(str(output/'bundle/scene.xml'),merge_shapes=False)
        alignment['sionna']=require_rf_mesh_match(scene,document)
        alignment['geometry_sha256']=bundle['scene_sha256'];atomic_json(output/'scene-alignment.json',alignment)
        state['geometry_sha256']=bundle['scene_sha256'];state['origin_ns']=origin
        count=round(ADVANCE_NS*FS/1e9)
        sources={tx['id']:WaveformSource(output/'scenario-input',tx['waveform'],FS) for tx in radio['transmitters']}
        if radar_mode:
            from .dashboard_radar import RadarWindowReceiver
            from .radar_control import serve_transceiver
            receiver=RadarWindowReceiver(scene,radio,arrays)
            radio_server=serve_transceiver(receiver.control,('0.0.0.0',args.radio_control_port))
            if not await asyncio.to_thread(receiver.control.ready.wait,args.ready_timeout):
                raise RuntimeError('Radar skill did not configure and enable transceiver receive acquisition')
        else:receiver=create_receiver(scene,radio,arrays,sources,origin,count)
        tx_positions={};platform_positions={}
        def update_platforms(epoch):
            kinematics={name:normalize_kinematics(platform.get_ground_truth_kinematics()) for name,platform in drones.items()}
            platform_positions.update({name:mount_kinematics(kin)[0].tolist() for name,kin in kinematics.items()})
            for tx in radio['transmitters']:
                position,velocity,orientation=mount_kinematics(kinematics[tx['actor']],tx['mount_body_m'])
                device=scene.transmitters[tx['id']];device.position=position.tolist();device.velocity=velocity.tolist();device.orientation=orientation.tolist()
                tx_positions[tx['id']]=position
            if radar_mode:
                receiver.update(kinematics)
                platform_positions.update({t.name:list(t.position_m) for t in receiver.targets})
                tx_positions[primary_tx]=np.asarray(receiver.targets[0].position_m)
                site_positions[:]=[site['center_rf_m'] for site in arrays['sites']]
            else:receiver.emitters.update(emitters_for_window(radio,sources,epoch,count,origin))
            return kinematics[camera['actor']],mount_kinematics(kinematics[camera['actor']])
        def record_frame(epoch,position,captures):
            binding.require_static_match(world,epoch)
            row={'sim_time_ns':epoch,'sim_elapsed_s':(epoch-origin)*1e-9,'position_rf_m':position.tolist(),'primary_tx_position_rf_m':tx_positions[primary_tx].tolist(),'visibility_transmitter':primary_tx,'platform_positions_rf_m':dict(platform_positions),
                **link_geometry(document,arrays,tx_positions[primary_tx],receiver.last_path_diagnostics,transmitter_id=primary_tx),
                'retained_paths_per_channel':[sum(c.retained_paths.values()) for c in captures.values()],
                'max_clipped_component_fraction':max(c.clipped_component_fraction for c in captures.values())}
            if radar_mode:row.update(radar_truth=receiver.truth,line_target_position_rf_m=tx_positions[primary_tx].tolist(),
                transceiver=receiver.control.snapshot())
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
            blocks=[SampleBlock(name,captures[name].adc_iq_volts,writer.states.get(name,(0,))[0],
                captures[name].sim_time_ns,captures[name].actual_sample_rate_hz,CARRIER,
                captures[name].clipped_component_fraction)
                for site in arrays['sites'] for name in site['channels']]
            if iq_recording is not None:
                started_io=time.monotonic();iq_recording.write_window(blocks)
                state['iq_recording_wall_s']=state.get('iq_recording_wall_s',0.)+time.monotonic()-started_io
                state['iq_recording_bytes']=iq_recording.manifest['payload_bytes']
            for block in blocks:
                writer.send_samples(block.receiver,block.samples,timestamp_ns=block.timestamp_ns,
                    sample_rate_hz=block.sample_rate_hz,clipped_component_fraction=block.clipped_component_fraction)
        async def save_source_frame():
            recording.source_frame(state)
        prepared_captures=None
        if args.wait_for_mission:
            # Exercise the actual configured scene, eight-channel block and data
            # plane before advertising READY. Reuse this initial window at T+0.
            epoch=int(world.get_sim_time())
            initial,(position,velocity,orientation)=update_platforms(epoch)
            prepared_captures=receiver.capture(epoch,num_samples=count)
            row=record_frame(epoch,position,prepared_captures)
            send_captures(prepared_captures)
            if not (await commit_window(writer,stop_requested))[0]:
                recording.status('stopped');return
            row.update(windows=1,velocity_rf_m_s=velocity.tolist(),camera_frames=camera_counter[0],
                wall_elapsed_s=0.,simulation_speed=0.,raw_payload_bytes=count*num_channels*8)
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
        for index in range(max(1,int(np.ceil(args.duration*1e9/ADVANCE_NS)))):
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
            for platform,motion in motions:
                if motion.done():motion.result()
            epoch=int(world.get_sim_time());kinematics,(position,velocity,orientation)=update_platforms(epoch)
            if not args.no_render:queue_view(position,kinematics)
            if index==0 and prepared_captures is not None:
                captures=prepared_captures
            else:
                if radar_mode:
                    while not receiver.control.ready.is_set():
                        if stop_requested():break
                        await asyncio.sleep(.05)
                    if stop_requested():break
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
                camera_framing=f"{camera['distance_m']} m Chase view toward receivers; actual-frame labels",
                geometry_sha256=bundle['scene_sha256'],raw_payload_bytes=(index+1)*count*num_channels*8)
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
            while history and not any(abs(c['sim_time_ns']-history[-1]['sim_time_ns'])<=ADVANCE_NS//2 for c in camera_history):
                if time.monotonic()>=deadline:break
                await asyncio.sleep(.05)
        state.update(status='stopped' if stop_requested() else 'complete',camera_frames=camera_counter[0]);atomic_json(output/'producer.json',state)
        recording.status(state['status'])
        for platform,motion in motions:platform.cancel_last_task()
        world.continue_until_sim_time(int(world.get_sim_time())+mission['physics_step_ns'],wait_until_complete=True)
        for platform,motion in motions:
            try:await asyncio.wait_for(asyncio.shield(motion),timeout=2)
            except asyncio.TimeoutError:pass
    except BaseException as error:
        recording.status('failed',error=str(error))
        state.update(status='failed',error=str(error));atomic_json(output/'producer.json',state);raise
    finally:
        if radio_server is not None:
            receiver.control.set_state({'transmit':False,'receive':False})
            radio_server.shutdown();radio_server.server_close()
        try:
            if iq_recording is not None:iq_recording.close(state['status'] if state['status'] in ('complete','stopped') else 'failed')
        finally:
            if sock:sock.close()
            if flight_client:flight_client.disconnect()
            client.disconnect()



def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=120);parser.add_argument('--address',default='127.0.0.1')
    parser.add_argument('--iq-host',default='127.0.0.1');parser.add_argument('--iq-port',type=int,default=8811)
    parser.add_argument('--radio-control-port',type=int,default=8814)
    parser.add_argument('--recording-id',help='Coordinator-prepared source recording ID')
    parser.add_argument('--pascal-compat',action='store_true')
    parser.add_argument('--wait-for-mission',action='store_true')
    parser.add_argument('--ready-timeout',type=float,default=600)
    parser.add_argument('--no-render',action='store_true');args=parser.parse_args()
    if not 0<args.duration<=3600:parser.error('duration must be in (0,3600] seconds')
    asyncio.run(run(args))


if __name__=='__main__':main()
