"""Single stepping owner: actual AirSim orbit -> Sionna -> ADC -> Docker skill."""
import argparse
import asyncio
import json
from pathlib import Path
import socket
import time

import numpy as np
from .dashboard_scenario import ADVANCE_NS,FS,CARRIER,SPEED,RADIUS,atomic_json,waveform_window


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
    from .bridge import mount_kinematics
    from .geometry import read_bundle
    from .geometry_sync import AirSimGeometryBinding,spawn_placements,nearest_intersections
    from .iq_stream import IQStreamWriter
    from .sampled_waveform import SampledWaveform
    from .sdr import SDREmitter,SDRNetworkReceiver,PlutoSDRProfile

    output=Path(args.run_dir);arrays=json.loads((output/'arrays.json').read_text())
    document,bundle,bindings=read_bundle(output/'bundle')
    client=ProjectAirSimClient(address=args.address);client.connect()
    state={'status':'starting','sim_elapsed_s':0,'windows':0,'camera_frames':0,'backend':'CUDA / Sionna RT','propagation':'direct + first-order specular'}
    atomic_json(output/'producer.json',state)
    writer=None;sock=None;motion=None
    camera_counter=[0];last_camera=[0.]
    def image_received(_,message):
        try:
            image=unpack_image(message)
            success,jpeg=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,82])
            if success:
                temp=output/'camera.tmp';temp.write_bytes(jpeg.tobytes());temp.replace(output/'camera.jpg')
                camera_counter[0]+=1;last_camera[0]=time.monotonic()
        except Exception as error:state['camera_error']=str(error)
    try:
        world=World(client,'scene.jsonc',sim_config_path=str((output/'sim_config').resolve()));world.pause()
        binding=AirSimGeometryBinding(document,bindings);spawn_placements(world,binding.plan)
        binding.require_static_match(world,int(world.get_sim_time()))
        visual={}
        for name in ('Terrain','RidgeScreen'):
            try:visual[name]=world.set_object_material(name,'/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial')
            except Exception as error:visual[name]=str(error)
        state['visual_materials']=visual
        drone=Drone(client,world,'OrbitDrone')
        client.subscribe(drone.sensors['Chase']['scene_camera'],image_received)
        drone.enable_api_control();drone.arm()
        motion=await drone.move_by_velocity_body_frame_z_async(v_forward=SPEED,v_right=0,z=-160.,duration=args.duration+5,yaw_is_rate=True,yaw=-SPEED/RADIUS)
        world.continue_until_sim_time(int(world.get_sim_time())+2_001_000_000,wait_until_complete=True)
        await asyncio.sleep(.1)
        origin=int(world.get_sim_time());scene=rt.load_scene(str(output/'bundle/scene.xml'),merge_shapes=False)
        scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V');scene.rx_array=scene.tx_array
        scene.add(rt.Transmitter('tx0',position=[250,0,160]))
        for site in arrays['sites']:
            for name,offset in zip(site['channels'],site['element_offsets_m']):
                scene.add(rt.Receiver(name,position=(np.asarray(site['center_rf_m'])+[0,offset,0]).tolist()))
        count=round(ADVANCE_NS*FS/1e9);samples,reference=waveform_window(origin,count,origin)
        receiver=SDRNetworkReceiver(scene,{'tx0':SDREmitter(SampledWaveform(samples,FS,reference,boundary='error'),transmit_power_w=.1,baseband_frequency_bounds_hz=(-100000,100000))},
            PlutoSDRProfile(noise_enabled=True),renderer='basis-cuda',continuous=True,path_solver='single-bounce',max_depth=1,samples_per_link=2,seed=20261021)
        sock=socket.create_connection((args.skill_host,args.skill_port),timeout=120);writer=IQStreamWriter(sock,carrier_hz=CARRIER)
        started=time.monotonic();history=[]
        for index in range(max(1,round(args.duration*1e9/ADVANCE_NS))):
            while True:
                command=json.loads((output/'command.json').read_text()) if (output/'command.json').exists() else {}
                if command.get('stop'):break
                if not command.get('paused'):break
                state['status']='paused';atomic_json(output/'producer.json',state);await asyncio.sleep(.2)
            if command.get('stop'):break
            epoch=int(world.get_sim_time());position,velocity,orientation=mount_kinematics(drone.get_ground_truth_kinematics())
            scene.transmitters['tx0'].position=position.tolist();scene.transmitters['tx0'].velocity=velocity.tolist();scene.transmitters['tx0'].orientation=orientation.tolist()
            samples,reference=waveform_window(epoch,count,origin)
            receiver.emitters['tx0']=SDREmitter(SampledWaveform(samples,FS,reference,boundary='error'),transmit_power_w=.1,baseband_frequency_bounds_hz=(-100000,100000))
            captures=receiver.capture(epoch,num_samples=count)
            for name,capture in captures.items():writer.send_capture(name,capture)
            direct=[]
            for site in arrays['sites']:
                a=np.asarray(site['center_rf_m'])*[1,-1,-1];b=position*[1,-1,-1];distance=np.linalg.norm(b-a)
                hit=nearest_intersections(document,[a],[b-a],maximum_distance_m=float(distance-.01))[0]
                direct.append(hit is None)
            elapsed=(epoch-origin)*1e-9
            history.append({'sim_elapsed_s':elapsed,'position_rf_m':position.tolist(),'direct_visible':direct})
            history=history[-1000:]
            state.update(status='running',sim_elapsed_s=elapsed,windows=index+1,sim_time_ns=epoch,
                position_rf_m=position.tolist(),velocity_rf_m_s=velocity.tolist(),direct_visible=direct,
                retained_paths={name:cap.retained_paths for name,cap in captures.items()},history=history,
                wall_elapsed_s=time.monotonic()-started,simulation_speed=elapsed/max(time.monotonic()-started,.001),
                camera_frames=camera_counter[0],camera_age_s=None if not last_camera[0] else time.monotonic()-last_camera[0],
                geometry_sha256=bundle['scene_sha256'],raw_payload_bytes=(index+1)*count*8*8)
            atomic_json(output/'producer.json',state)
            world.continue_until_sim_time(epoch+ADVANCE_NS,wait_until_complete=True)
            await asyncio.sleep(0)
        writer.finish();writer=None
        state.update(status='complete',camera_frames=camera_counter[0]);atomic_json(output/'producer.json',state)
        drone.cancel_last_task()
    except BaseException as error:
        state.update(status='failed',error=str(error));atomic_json(output/'producer.json',state);raise
    finally:
        if sock:sock.close()
        client.disconnect()



def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=120);parser.add_argument('--address',default='127.0.0.1')
    parser.add_argument('--skill-host',default='127.0.0.1');parser.add_argument('--skill-port',type=int,default=8811)
    parser.add_argument('--pascal-compat',action='store_true');args=parser.parse_args()
    if not 0<args.duration<=3600:parser.error('duration must be in (0,3600] seconds')
    asyncio.run(run(args))


if __name__=='__main__':main()
