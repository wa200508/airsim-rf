"""Create a finite waveform and matched two-radio configuration, without a server."""
import argparse
import json
from pathlib import Path
from importlib.resources import files

import numpy as np


def prepare(output, *, address='127.0.0.1', propagation='specular', geometry='ground'):
    if geometry not in ('ground', 'shared'):
        raise ValueError('geometry must be ground or shared')
    if propagation not in ('direct','specular','diffuse-angular','diffuse-surface'):
        raise ValueError('Unknown propagation mode')
    if geometry == 'shared':
        try:
            import pxr  # Check optional dependency before creating output.
        except ImportError as error:
            raise RuntimeError('Shared example requires OpenUSD; install airsim-rf[geometry] with usd-core==26.8') from error
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    assets=files('airsim_rf').joinpath('assets')
    fs=2_000_000;duration=.25;frequency=150_000
    np.save(output/'tx0.npy',np.exp(2j*np.pi*frequency*np.arange(round(duration*fs))/fs))
    for name,destination in [('ground.xml','rf_ground.xml'),('ground.ply','ground.ply')]:
        (output/destination).write_bytes(assets.joinpath(name).read_bytes())
    sim=output/'sim_config';sim.mkdir()
    # Minimal non-physics robot: this smoke scene tests client/timestamps/RF, not flight control.
    (sim/'robot_rf.jsonc').write_text(json.dumps({'physics-type':'non-physics',
        'links':[{'name':'Frame','collision':{'enabled':False}}],'sensors':[]},indent=2)+'\n')
    actors=[{'type':'robot','name':name,'origin':{'xyz':xyz,'rpy-deg':'0 0 0'},
             'robot-config':'robot_rf.jsonc'} for name,xyz in [('Drone1','-20 0 -20'),('Drone2','20 0 -20')]]
    (sim/'scene_rf.jsonc').write_text(json.dumps({'id':'SceneRFTwoRadios','actors':actors,
        'clock':{'type':'steppable','step-ns':3_000_000,'real-time-update-rate':3_000_000,'pause-on-start':True},
        'home-geo-point':{'latitude':47.641468,'longitude':-122.140165,'altitude':122.},
        'scene-type':'UnrealNative'},indent=2)+'\n')
    if geometry == 'shared':
        for actor in actors:
            coordinates=actor['origin']['xyz'].split()
            coordinates[2]='-120'
            actor['origin']['xyz']=' '.join(coordinates)
        scene=json.loads((sim/'scene_rf.jsonc').read_text())
        scene['actors']=actors
        (sim/'scene_rf.jsonc').write_text(json.dumps(scene,indent=2)+'\n')
    config={'address':address,'scene':'scene_rf.jsonc','sim_config':'sim_config','rf_scene':'rf_ground.xml',
        'antennas':{'tx':{'pattern':'hw_dipole','polarization':'V'},'rx':{'pattern':'hw_dipole','polarization':'V'}},
        'receiver_profile':{'carrier_hz':915_000_000,'sample_rate_hz':fs,'rf_bandwidth_hz':1_000_000},
        'propagation':{'mode':propagation,'samples_per_link':4096 if propagation=='diffuse-surface' else 1028,'seed':42},'radios':{'tx0':{'robot':'Drone1','waveform_npy':'tx0.npy',
            'transmit_power_w':.0001,'baseband_frequency_bounds_hz':[frequency,frequency],'mount_body_m':[0,0,0]},
            'rx0':{'robot':'Drone2','mount_body_m':[0,0,0]}}}
    if geometry == 'shared':
        from .usd_geometry import import_usd
        from .geometry import export_sionna_geometry
        source=output/'geometry-source';source.mkdir()
        for name in ('shared-mesh-world.usda','shared-mesh-world.rf.json'):
            (source/name).write_bytes(assets.joinpath(name).read_bytes())
        profile_path=source/'shared-mesh-world.rf.json'
        profile=json.loads(profile_path.read_text())
        profile['stage_meters_to_ned_m'][2][3]=-100
        profile_path.write_text(json.dumps(profile,indent=2)+'\n')
        document,provenance,bindings=import_usd(source/'shared-mesh-world.usda',profile_path)
        export_sionna_geometry(document,output/'bundle',provenance=provenance,bindings=bindings)
        config.update(geometry_bundle='bundle',geometry_placement='spawn',rf_scene='bundle/scene.xml')
        config['receiver_profile']['noise_enabled']=False
        (output/'rf_ground.xml').unlink();(output/'ground.ply').unlink()
    (output/'radios.json').write_text(json.dumps(config,indent=2)+'\n')
    (output/'README.txt').write_text('RF ground z=0; NED radio poses convert to RF (-20,0,20)/(20,0,20).\n'
        'Use a simulator world with only matching ground for this smoke experiment.\n'
        'Other visible buildings/objects are NOT included in the RF mesh.\n'
        'Waveform: unit-power +150kHz CW, 500000 samples, 0.25 s at 2 MS/s.\n'
        'Minimal non-physics robots; this checks server integration, not flight dynamics.\n')
    if geometry == 'shared':
        (output/'README.txt').write_text('Shared static USD ground, sloping-roof building and rotated wall.\n'
            'Blocks 1.0.1 client GLB collision meshes and RF bundle derive from the same triangles.\n'
            'Requires a dedicated Blocks server; the standalone Runtime cannot spawn these meshes.\n'
            'Stationary non-physics radios at NED (-20,0,-120)/(20,0,-120). Ground NED z=-100.\n'
            '915 MHz carrier, 2 MS/s, unit-power +150 kHz CW; 0.25 s source; noise disabled.\n'
            'Defaults: 10 x requested 10 ms updates, rounded to 12 ms physics windows.\n'
            'Expected: 240000 complex samples, 960000 data bytes, 0.120 signal seconds at 2 MS/s.\n'
            'Preflight: airsim-rf preflight --config radios.json\n'
            'Record: airsim-rf-live --config radios.json --output ../capture\n'
            'P100: use airsim-rf-cuda -m airsim_rf.live --pascal-compat with those arguments.\n'
            'Inspect: airsim-rf inspect ../capture\n'
            'Geometry edits require a new bundle, simulator placement, RF scene and receiver.\n')
    return output/'radios.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--address',default='127.0.0.1')
    parser.add_argument('--geometry',choices=('ground','shared'),default='shared')
    parser.add_argument('--propagation',choices=['direct','specular','diffuse-angular','diffuse-surface'],default='specular')
    args=parser.parse_args()
    print(prepare(args.output,address=args.address,propagation=args.propagation,geometry=args.geometry))


if __name__=='__main__':
    main()
