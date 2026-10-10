"""Create a finite waveform and matched two-radio configuration, without a server."""
import argparse
import json
from pathlib import Path
import shutil

import numpy as np


def prepare(output, *, address='127.0.0.1'):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1]
    fs=2_000_000;duration=.25;frequency=150_000
    np.save(output/'tx0.npy',np.exp(2j*np.pi*frequency*np.arange(round(duration*fs))/fs))
    shutil.copy2(root/'benchmarks/scenes/ground.xml',output/'rf_ground.xml')
    shutil.copy2(root/'benchmarks/scenes/ground.ply',output/'ground.ply')
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
    config={'address':address,'scene':'scene_rf.jsonc','sim_config':'sim_config','rf_scene':'rf_ground.xml',
        'receiver_profile':{'carrier_hz':915_000_000,'sample_rate_hz':fs,'rf_bandwidth_hz':1_000_000},
        'samples_per_link':1028,'radios':{'tx0':{'robot':'Drone1','waveform_npy':'tx0.npy',
            'transmit_power_w':.0001,'baseband_frequency_bounds_hz':[frequency,frequency],'mount_body_m':[0,0,0]},
            'rx0':{'robot':'Drone2','mount_body_m':[0,0,0]}}}
    (output/'radios.json').write_text(json.dumps(config,indent=2)+'\n')
    (output/'README.txt').write_text('RF ground z=0; NED radio poses convert to RF (-20,0,20)/(20,0,20).\n'
        'Use a simulator world with only matching ground for this smoke experiment.\n'
        'Other visible buildings/objects are NOT included in the RF mesh.\n'
        'Waveform: unit-power +150kHz CW, 500000 samples, 0.25 s at 2 MS/s.\n'
        'Minimal non-physics robots; real server loading remains to be qualified.\n')
    return output/'radios.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--address',default='127.0.0.1')
    args=parser.parse_args()
    print(prepare(args.output,address=args.address))


if __name__=='__main__':
    main()
