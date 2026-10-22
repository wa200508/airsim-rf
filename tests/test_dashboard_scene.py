"""RF occlusion, echo-only I/Q and shared dashboard scene regression tests."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from airsim_rf.dashboard_geometry import isolate_blocks_scene,require_rf_mesh_match,link_geometry
from airsim_rf.geometry import export_sionna_geometry,read_bundle
from airsim_rf.sdr import SDRNetworkReceiver,SDREmitter,PlutoSDRProfile


def radios(scene,position,arrays):
    import sionna.rt as rt
    scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V')
    scene.rx_array=scene.tx_array
    scene.add(rt.Transmitter('tx0',position=position))
    for site in arrays['sites']:
        for name,offset in zip(site['channels'],site['element_offsets_m']):
            scene.add(rt.Receiver(name,position=(np.asarray(site['center_rf_m'])+[0,offset,0]).tolist()))
    return SDRNetworkReceiver(scene,{'tx0':SDREmitter(lambda t:np.exp(2j*np.pi*10000*t),transmit_power_w=.1)},
        PlutoSDRProfile(noise_enabled=False),path_solver='single-bounce',path_diagnostics=True)


def test_blocked_direct_path_keeps_reflected_signal_in_rendered_iq(tmp_path):
    import sionna.rt as rt
    # A short blocker on x=0 and a reflector on y=3: the direct 4 m
    # segment is blocked, but the 7.21 m one-bounce route goes around it.
    objects=[]
    for name,vertices in [('Blocker',[[0,-.5,0],[0,.5,0],[0,.5,2],[0,-.5,2]]),
                          ('Reflector',[[-5,3,0],[5,3,0],[5,3,3],[-5,3,3]])]:
        objects.append({'id':name,'material':'earth','vertices_local':(np.array(vertices)*[1,-1,-1]).tolist(),
            'faces':[[0,1,2],[0,2,3]],'local_to_ned_m':np.eye(4).tolist()})
    document={'schema_version':1,'scene_id':'EchoCheck','revision':'1',
        'source':{'adapter':'test','version':'1','asset':'finite-wall','revision':'1','geometry_kind':'shared'},
        'materials':{'earth':{'relative_permittivity':5.,'conductivity_s_m':.01,'assumption':'Synthetic test dielectric'}},'objects':objects}
    export_sionna_geometry(document,tmp_path/'bundle')
    scene=rt.load_scene(str(tmp_path/'bundle/scene.xml'),merge_shapes=False)
    arrays={'sites':[{'id':'site0','center_rf_m':[2,0,1],'channels':['rx0'],'element_offsets_m':[0]}]}
    receiver=radios(scene,[-2,0,1],arrays)
    blocked=receiver.capture(0,num_samples=1024)['rx0']
    state=link_geometry(document,arrays,[-2,0,1],receiver.last_path_diagnostics)
    assert state['direct_visible']==[False]
    assert receiver.last_path_diagnostics['rx0']['tx0']=={'direct_paths':0,'reflected_paths':1}
    assert np.mean(abs(blocked.adc_iq_volts)**2)>0  # actual echo-derived samples, no receiver noise
    scene.transmitters['tx0'].position=[-2,2,1]
    receiver.capture(120000000,num_samples=1024)
    assert receiver.last_path_diagnostics['rx0']['tx0']['direct_paths']==1


def test_shared_dem_orbit_checks_all_eight_sionna_receiver_elements(tmp_path):
    import sionna.rt as rt
    from airsim_rf.dashboard_scenario import prepare
    arrays=prepare(tmp_path,Path('.deps/ProjectAirSim-runtime'))
    document,_,_=read_bundle(tmp_path/'bundle')
    scene=rt.load_scene(str(tmp_path/'bundle/scene.xml'),merge_shapes=False)
    require_rf_mesh_match(scene,document)
    receiver=radios(scene,[250,0,200],arrays);states=[]
    for index,angle in enumerate(np.deg2rad(np.arange(0,360,15))):
        position=[float(250*np.cos(angle)),float(250*np.sin(angle)),200]
        scene.transmitters['tx0'].position=position
        captures=receiver.capture(index*120000000,num_samples=128)
        state=link_geometry(document,arrays,position,receiver.last_path_diagnostics)
        states.append(state)
        for name,paths in state['channel_paths'].items():
            if not paths['direct_visible']:
                assert paths['direct_paths']==0
                if paths['reflected_paths']==0:assert np.max(abs(captures[name].input_iq_volts))==0
    assert any(all(s['direct_visible']) for s in states)
    assert any(not any(s['direct_visible']) for s in states)


def test_independent_visibility_mismatch_is_rejected():
    # A known clear segment must not pass the gate with a blocked RF result.
    document={'schema_version':1,'scene_id':'Gate','revision':'1',
        'source':{'adapter':'test','version':'1','asset':'ground','revision':'1','geometry_kind':'shared'},
        'materials':{'earth':{'relative_permittivity':5.,'conductivity_s_m':.01,'assumption':'Synthetic test dielectric'}},
        'objects':[{'id':'Ground','material':'earth','vertices_local':[[0,0,0],[1,0,0],[0,1,0]],
                    'faces':[[0,1,2]],'local_to_ned_m':np.eye(4).tolist()}]}
    arrays={'sites':[{'id':'s','channels':['rx'],'center_rf_m':[0,0,2],'element_offsets_m':[0]}]}
    with pytest.raises(RuntimeError,match='disagrees'):
        link_geometry(document,arrays,[1,0,2],{'rx':{'tx0':{'direct_paths':0,'reflected_paths':0}}})


def test_native_blocks_scenery_is_removed_but_lighting_and_platform_are_retained():
    names=['Ground','TemplateCube_Rounded_1','Cone_5','Cylinder2','OrangeBall','SunSky_2','OrbitDrone','UnrealScene']
    world=SimpleNamespace(list_objects=lambda _:list(names),destroy_object=lambda name:names.remove(name) or True)
    report=isolate_blocks_scene(world)
    assert len(report['removed_native_objects'])==5
    assert names==['SunSky_2','OrbitDrone','UnrealScene']
