"""Single stepping owner: actual AirSim orbit -> Sionna -> ADC -> Docker skill."""
import argparse
import asyncio
import json
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
    from .dashboard_view import queue_chase_camera_pose,project_radios,radio_marker_glb
    from .geometry import read_bundle
    from .geometry_sync import AirSimGeometryBinding,spawn_placements,nearest_intersections
    from .iq_stream import IQStreamWriter
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
    camera_counter=[0];last_camera=[0.];view=[None]
    site_positions=[site['center_rf_m'] for site in arrays['sites']]
    def image_received(_,message):
        try:
            image=unpack_image(message).copy()
            if view[0] is not None:
                eye,rotation,points=view[0];height,width=image.shape[:2]
                projected=project_radios(eye,rotation,points,width,height)
                for label,point,color in zip(('TX / DRONE','RX 0','RX 1'),projected,((40,180,255),(210,230,70),(80,200,255))):
                    x,y,depth=point
                    if depth>0 and 0<x<width and 0<y<height:
                        anchor=(round(x),round(y));cv2.circle(image,anchor,7,color,2)
                        cv2.putText(image,label,(max(5,min(width-150,round(x)+12)),max(20,round(y)-12)),cv2.FONT_HERSHEY_SIMPLEX,.55,(5,10,15),4)
                        cv2.putText(image,label,(max(5,min(width-150,round(x)+12)),max(20,round(y)-12)),cv2.FONT_HERSHEY_SIMPLEX,.55,color,1)
            success,jpeg=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,82])
            if success:
                temp=output/'camera.tmp';temp.write_bytes(jpeg.tobytes());temp.replace(output/'camera.jpg')
                camera_counter[0]+=1;last_camera[0]=time.monotonic()
        except Exception as error:state['camera_error']=str(error)
    try:
        if args.wait_for_mission:
            from .preflight import gpu_check
            atomic_json(output/'gpu-preflight-input.json',{'rf_scene':'bundle/scene.xml'})
            check=gpu_check(output/'gpu-preflight-input.json',pascal_compat=args.pascal_compat)
            atomic_json(output/'gpu-preflight.json',check)
        world=World(client,'scene.jsonc',sim_config_path=str((output/'sim_config').resolve()));world.pause()
        binding=AirSimGeometryBinding(document,bindings)
        # Presentation-only glTF appearance; RF dielectric settings remain in
        # the shared geometry document. A little emission keeps dynamically
        # imported meshes visible in the packaged map's baked lighting.
        for obj in binding.plan['objects']:
            terrain=obj['id']=='Terrain'
            obj['mesh']['base_color_rgba']=[.34,.48,.22,1.] if terrain else [.48,.32,.20,1.]
            obj['mesh']['emissive_rgb']=[.07,.10,.045] if terrain else [.12,.075,.035]
        spawn_placements(world,binding.plan)
        binding.require_static_match(world,int(world.get_sim_time()))
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
            eye,rotation=queue_chase_camera_pose(drone,position,site_positions,initial)
            view[0]=(eye,rotation,[position.tolist(),*site_positions])
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
        scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V');scene.rx_array=scene.tx_array
        scene.add(rt.Transmitter('tx0',position=[250,0,ALTITUDE]))
        for site in arrays['sites']:
            for name,offset in zip(site['channels'],site['element_offsets_m']):
                scene.add(rt.Receiver(name,position=(np.asarray(site['center_rf_m'])+[0,offset,0]).tolist()))
        count=round(ADVANCE_NS*FS/1e9);samples,reference=waveform_window(origin,count,origin)
        receiver=SDRNetworkReceiver(scene,{'tx0':SDREmitter(SampledWaveform(samples,FS,reference,boundary='error'),transmit_power_w=.1,baseband_frequency_bounds_hz=(-100000,100000))},
            PlutoSDRProfile(noise_enabled=True),renderer='basis-cuda',continuous=True,path_solver='single-bounce',max_depth=1,samples_per_link=2,seed=20261021)
        deadline=time.monotonic()+args.ready_timeout
        while True:
            try:sock=socket.create_connection((args.skill_host,args.skill_port),timeout=2);break
            except OSError:
                if time.monotonic()>deadline:raise RuntimeError('RF skill ingress did not become ready')
                await asyncio.sleep(.25)
        sock.settimeout(120);writer=IQStreamWriter(sock,carrier_hz=CARRIER)
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
            for name,capture in prepared_captures.items():writer.send_capture(name,capture)
            if not args.no_render:
                deadline=time.monotonic()+30
                while not camera_counter[0] and time.monotonic()<deadline:await asyncio.sleep(.1)
                if not camera_counter[0]:raise RuntimeError('No actual ProjectAirSim camera frame during preparation')
            state.update(status='ready',camera_frames=camera_counter[0],gpu_preflight='passed',mission_started=False)
            atomic_json(output/'producer.json',state)
            while True:
                command=json.loads((output/'command.json').read_text())
                if command.get('stop'):
                    state.update(status='stopped');atomic_json(output/'producer.json',state);return
                if command.get('start'):break
                await asyncio.sleep(.2)
        started=time.monotonic();history=[]
        for index in range(max(1,round(args.duration*1e9/ADVANCE_NS))):
            while True:
                command=json.loads((output/'command.json').read_text()) if (output/'command.json').exists() else {}
                if command.get('stop'):break
                if not command.get('paused'):break
                state['status']='paused';atomic_json(output/'producer.json',state);await asyncio.sleep(.2)
            if command.get('stop'):break
            if motion.done():motion.result()
            epoch=int(world.get_sim_time());kinematics=normalize_kinematics(drone.get_ground_truth_kinematics())
            position,velocity,orientation=mount_kinematics(kinematics)
            if not args.no_render:
                eye,rotation=queue_chase_camera_pose(drone,position,site_positions,kinematics)
                view[0]=(eye,rotation,[position.tolist(),*site_positions])
            scene.transmitters['tx0'].position=position.tolist();scene.transmitters['tx0'].velocity=velocity.tolist();scene.transmitters['tx0'].orientation=orientation.tolist()
            samples,reference=waveform_window(epoch,count,origin)
            receiver.emitters['tx0']=SDREmitter(SampledWaveform(samples,FS,reference,boundary='error'),transmit_power_w=.1,baseband_frequency_bounds_hz=(-100000,100000))
            if index==0 and prepared_captures is not None:
                captures=prepared_captures
            else:
                captures=receiver.capture(epoch,num_samples=count)
                for name,capture in captures.items():writer.send_capture(name,capture)
            direct=[]
            for site in arrays['sites']:
                a=np.asarray(site['center_rf_m'])*[1,-1,-1];b=position*[1,-1,-1];distance=np.linalg.norm(b-a)
                hit=nearest_intersections(document,[a],[b-a],maximum_distance_m=float(distance-.01))[0]
                direct.append(hit is None)
            elapsed=(epoch-origin)*1e-9
            history.append({'sim_elapsed_s':elapsed,'position_rf_m':position.tolist(),'direct_visible':direct,
                'retained_paths_per_channel':[sum(c.retained_paths.values()) for c in captures.values()],
                'max_clipped_component_fraction':max(c.clipped_component_fraction for c in captures.values())})
            history=history[-1000:]
            state.update(status='running',sim_elapsed_s=elapsed,windows=index+1,sim_time_ns=epoch,
                position_rf_m=position.tolist(),velocity_rf_m_s=velocity.tolist(),direct_visible=direct,
                retained_paths={name:cap.retained_paths for name,cap in captures.items()},history=history,
                wall_elapsed_s=time.monotonic()-started,simulation_speed=elapsed/max(time.monotonic()-started,.001),
                camera_frames=camera_counter[0],camera_age_s=None if not last_camera[0] else time.monotonic()-last_camera[0],
                camera_framing='Actual gimballed Chase view; projected TX/RX labels; presentation-only radio beacons',
                geometry_sha256=bundle['scene_sha256'],raw_payload_bytes=(index+1)*count*8*8)
            atomic_json(output/'producer.json',state)
            world.continue_until_sim_time(epoch+ADVANCE_NS,wait_until_complete=True)
            await asyncio.sleep(0)
        totals=writer.finish();writer=None
        state['acknowledged_sample_totals']=totals
        state.update(status='complete',camera_frames=camera_counter[0]);atomic_json(output/'producer.json',state)
        drone.cancel_last_task()
        world.continue_until_sim_time(int(world.get_sim_time())+3_000_000,wait_until_complete=True)
        try:await asyncio.wait_for(asyncio.shield(motion),timeout=2)
        except asyncio.TimeoutError:pass
    except BaseException as error:
        state.update(status='failed',error=str(error));atomic_json(output/'producer.json',state);raise
    finally:
        if sock:sock.close()
        if flight_client:flight_client.disconnect()
        client.disconnect()



def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=120);parser.add_argument('--address',default='127.0.0.1')
    parser.add_argument('--skill-host',default='127.0.0.1');parser.add_argument('--skill-port',type=int,default=8811)
    parser.add_argument('--pascal-compat',action='store_true')
    parser.add_argument('--wait-for-mission',action='store_true')
    parser.add_argument('--ready-timeout',type=float,default=300)
    parser.add_argument('--no-render',action='store_true');args=parser.parse_args()
    if not 0<args.duration<=3600:parser.error('duration must be in (0,3600] seconds')
    asyncio.run(run(args))


if __name__=='__main__':main()
