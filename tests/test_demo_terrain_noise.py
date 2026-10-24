"""Low flight must clear the mesh between waypoints; noise scales independently."""
from copy import deepcopy
from dataclasses import replace
import json
import numpy as np
import pytest
from airsim_rf.dashboard_scenario import flight_path,prepare
from airsim_rf.scenario_definition import load
from airsim_rf.terrain import TerrainGrid


@pytest.mark.parametrize('scenario',['drone-orbit','mmwave-radar'])
def test_full_route_clearance_climb_grade_and_native_spawn_are_consistent(scenario,tmp_path):
    c=load(scenario);a=c['flight']['actors'][0];e=c['environment'];g=TerrainGrid(e['x_m'],e['y_m'],e['heights_m'])
    points=np.asarray(flight_path(a,1,terrain=g));np.testing.assert_allclose(points[0],points[-1],atol=1e-8)
    dense=np.concatenate([x+(y-x)*np.linspace(0,1,21)[:,None] for x,y in zip(points[:-1],points[1:])])
    clearance=dense[:,2]-g.elevation_at(dense[:,0],dense[:,1])
    assert clearance.min()>=a['flight']['terrain_clearance_m']-1e-8
    assert np.median(clearance)<25 and np.median(points[:,2])<180
    horizontal=np.linalg.norm(np.diff(points[:,:2],axis=0),axis=1)
    assert np.max(abs(np.diff(points[:,2]))/horizontal)<=a['flight']['max_vertical_grade']+1e-9
    run=tmp_path/'run';prepare(run,scenario_dir=scenario,duration_s=.004)
    runtime=json.loads((run/'runtime.json').read_text());scene=json.loads((run/'sim_config/scene.jsonc').read_text())
    first=np.asarray(runtime['compiled_routes_rf_m'][a['id']])[0]
    np.testing.assert_allclose(runtime['flight']['actors'][0]['position_rf_m'],first)
    np.testing.assert_allclose(list(map(float,scene['actors'][0]['origin']['xyz'].split())),first*[1,-1,-1])
    frozen=json.loads((run/'scenario-input/flight.json').read_text())
    assert frozen['actors'][0]['position_rf_m'][2]==120  # Authored nominal height remains editable.
    with pytest.raises(ValueError,match='heightfield'):flight_path(a,1)


def test_radar_noise_offset_scales_only_thermal_voltage():
    from airsim_rf.fmcw import IWR1843Profile,FMCWRadar
    profile=IWR1843Profile();outputs=[]
    for offset in (0.,-20.):
        cap=FMCWRadar(replace(profile,noise_power_offset_db=offset),seed=87).capture([],position_m=[0,0,100])
        outputs.append(cap.if_volts)
    np.testing.assert_allclose(outputs[1],outputs[0]*.1,rtol=2e-6,atol=1e-10)
    for value in (float('nan'),-121,61):
        with pytest.raises(ValueError,match='noise_power_offset_db'):replace(profile,noise_power_offset_db=value)


def test_sdr_noise_offset_scales_voltage_and_reported_power_once():
    import sionna.rt as rt
    from airsim_rf.sdr import PlutoSDRProfile,SDREmitter,SDRNetworkReceiver
    captures=[]
    for offset in (0.,-20.):
        scene=rt.load_scene();scene.tx_array=rt.PlanarArray(num_rows=1,num_cols=1,pattern='iso',polarization='V');scene.rx_array=scene.tx_array
        scene.add(rt.Transmitter('tx',position=[0,0,10]));scene.add(rt.Receiver('rx',position=[100,0,10]))
        emit={'tx':SDREmitter(lambda t:np.ones_like(t,dtype=complex),transmit_power_w=0)}
        receiver=SDRNetworkReceiver(scene,emit,PlutoSDRProfile(noise_power_offset_db=offset),seed=87,max_depth=0)
        captures.append(receiver.capture(0,num_samples=4096)['rx'])
    np.testing.assert_allclose(captures[1].input_iq_volts,captures[0].input_iq_volts*.1,rtol=2e-6,atol=1e-12)
    assert captures[1].thermal_noise_power_w/captures[0].thermal_noise_power_w==pytest.approx(.01)


def test_route_anticipates_a_ridge_hidden_between_declared_waypoints():
    terrain=TerrainGrid([0,10,20],[0,10],[[0,8,0],[0,8,0]])
    actor={'position_rf_m':[0,5,1],'flight':{'type':'waypoints','points_rf_m':[[0,5,1],[20,5,1]],
        'terrain_clearance_m':2.,'max_vertical_grade':.2}}
    points=np.asarray(flight_path(actor,1,terrain=terrain))
    assert points[0,2]==pytest.approx(8.) and points[-1,2]==pytest.approx(8.)
    assert points[np.argmax(points[:,2]),2]==pytest.approx(10.)
    dense=np.concatenate([x+(y-x)*np.linspace(0,1,31)[:,None] for x,y in zip(points[:-1],points[1:])])
    assert np.min(dense[:,2]-terrain.elevation_at(dense[:,0],dense[:,1]))>=2.-1e-9
