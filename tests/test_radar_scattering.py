"""First-order clutter normalization, occlusion, phase and linear echo work."""
from copy import deepcopy
from dataclasses import replace
import numpy as np
import pytest
from airsim_rf.fmcw import FMCWRadar,IWR1843Profile
from airsim_rf.radar import PointTarget
from airsim_rf.radar_scattering import TerrainBackscatter


def scene(tmp_path,wall=False):
    import sionna.rt as rt
    from airsim_rf.geometry import export_sionna_geometry
    floor=np.array([[-10,-10,0],[10,-10,0],[10,10,0],[-10,10,0.]])
    objects=[{'id':'Floor','material':'earth','vertices_local':(floor*[1,-1,-1]).tolist(),
              'faces':[[0,1,2],[0,2,3]],'local_to_ned_m':np.eye(4).tolist()}]
    if wall:
        vertices=np.array([[0,-10,0],[0,10,0],[0,10,30],[0,-10,30.]])
        objects.append({'id':'Wall','material':'earth','vertices_local':(vertices*[1,-1,-1]).tolist(),
                        'faces':[[0,1,2],[0,2,3]],'local_to_ned_m':np.eye(4).tolist()})
    doc={'schema_version':1,'scene_id':'clutter','revision':'1','source':{'adapter':'test','version':'1','asset':'fixture','revision':'1','geometry_kind':'shared'},
         'materials':{'earth':{'relative_permittivity':5.,'conductivity_s_m':.01,'assumption':'Test fixture'}},'objects':objects}
    export_sionna_geometry(doc,tmp_path/'bundle')
    return rt.load_scene(str(tmp_path/'bundle/scene.xml'),merge_shapes=False)


def configuration(count=1024):
    return {'enabled':True,'seed':72,
            'materials':{'earth':{'sigma0_db':-10.,'incidence_exponent':0.}},'shape_materials':{'obj_Floor':'earth'}}


def test_surface_area_normalization_and_stationary_sampling(tmp_path):
    s=scene(tmp_path)
    for count in (17,1024,4096):
        c=TerrainBackscatter(s,configuration(count),samples_per_link=count);c.prepare()
        assert len(c.points)==count and c.total_area_m2==pytest.approx(400.)
        assert c.rcs.sum()==pytest.approx(40.)  # sigma0 * actual represented area, for every budget.
        np.testing.assert_allclose(abs(c.weights),1.)
        np.testing.assert_allclose(c.points[:,2],0.)
        np.testing.assert_allclose(c.normals,np.tile([0,0,1.],(count,1)))
        points=c.points.copy();weights=c.weights.copy()
        c.candidates([0,0,20],100);c.candidates([5,0,20],100)
        np.testing.assert_array_equal(c.points,points);np.testing.assert_array_equal(c.weights,weights)


def test_one_patch_matches_physical_point_echo_and_preserves_slow_time_phase(tmp_path):
    s=scene(tmp_path);profile=replace(IWR1843Profile(),noise_enabled=False)
    radar=FMCWRadar(profile,rf_scene=s,clutter=configuration(1),samples_per_link=1,max_range_m=100)
    radar.clutter.prepare();patch=PointTarget('equivalent',tuple(radar.clutter.points[0]),radar.clutter.rcs[0])
    reference=FMCWRadar(profile,rf_scene=s)
    expected=reference.capture_frame([patch],position_m=[0,0,20],velocity_m_s=[.2,0,0],orientation_rad=[0,np.pi/2,0],num_chirps=3)
    actual=radar.capture_frame([],position_m=[0,0,20],velocity_m_s=[.2,0,0],orientation_rad=[0,np.pi/2,0],num_chirps=3)
    for a,b in zip(actual,expected):np.testing.assert_allclose(a.if_volts,b.if_volts*np.conj(radar.clutter.weights[0]),rtol=2e-6,atol=1e-12)
    assert radar.last_render_diagnostics['echo_terms']==1
    unix=radar.capture([],position_m=[0,0,20],orientation_rad=[0,np.pi/2,0],velocity_m_s=[.2,0,0],sim_time_ns=1790976000000000000)
    np.testing.assert_array_equal(unix.if_volts,actual[0].if_volts)
    assert np.any(actual[1].if_volts!=actual[0].if_volts)
    radar.reset_history()  # No earlier transmission exists in this independent TX-off check.
    off=radar.capture([patch],position_m=[0,0,20],orientation_rad=[0,np.pi/2,0],transmit_enabled=False)
    assert not np.any(off.if_volts) and radar.last_render_diagnostics['echo_terms']==0


def test_shared_wall_blocks_targets_and_terrain_without_secondary_echoes(tmp_path):
    radar=FMCWRadar(replace(IWR1843Profile(),noise_enabled=False),rf_scene=scene(tmp_path,wall=True),clutter=configuration(),samples_per_link=1024,max_range_m=100)
    result=radar.capture([PointTarget('hidden',(5,0,1.),1000.)],position_m=[-5,0,10],orientation_rad=[0,np.pi/2,0])
    assert radar.last_path_diagnostics['hidden']['direct_paths']==0
    assert radar.last_path_diagnostics['hidden']['reflected_paths']==0
    assert 0<radar.last_clutter_diagnostics['visible']<radar.last_clutter_diagnostics['in_range']
    assert radar.last_render_diagnostics['target_echoes']==0 and np.any(result.if_volts)


def test_range_rejection_precedes_visibility_for_targets_and_surface(tmp_path,monkeypatch):
    from airsim_rf import radar_scattering
    original=radar_scattering.segment_visibility;seen=[]
    def checked(s,p,endpoints):
        seen.append(len(endpoints));assert np.all(np.linalg.norm(endpoints-p,axis=1)<=5.)
        return original(s,p,endpoints)
    monkeypatch.setattr(radar_scattering,'segment_visibility',checked)
    radar=FMCWRadar(replace(IWR1843Profile(),noise_enabled=False),rf_scene=scene(tmp_path),clutter=configuration(),samples_per_link=1024,max_range_m=5.)
    result=radar.capture([PointTarget('far',(6,0,10),1.)],position_m=[0,0,10])
    assert seen==[0] and not np.any(result.if_volts)
    assert radar.last_path_diagnostics['far']['range_gated']


def test_1024_independent_echoes_have_linear_work_and_no_virtual_target_radios():
    import sionna.rt as rt
    radar=FMCWRadar(replace(IWR1843Profile(),noise_enabled=False),rf_scene=rt.load_scene(),max_range_m=400.)
    targets=[PointTarget(str(i),(100+i/100.,0,10.),1.) for i in range(1024)]
    radar.capture(targets,position_m=[0,0,10])
    assert radar.last_render_diagnostics['echo_terms']==1024
    assert not radar.scene.transmitters and not radar.scene.receivers
    with pytest.raises(ValueError,match='target-leg multipath'):FMCWRadar(max_depth=1)



def test_incidence_response_uses_surface_normal_and_rcs_per_actual_area(tmp_path):
    config=configuration(32);config['materials']['earth']['incidence_exponent']=1.
    c=TerrainBackscatter(scene(tmp_path),config,samples_per_link=32);points,rcs,_=c.candidates([0,0,20],100.)
    cosine=20/np.linalg.norm(points-[0,0,20],axis=1)
    np.testing.assert_allclose(rcs,40/32*cosine)


def test_terrain_returns_from_old_transmission_survive_tx_off(tmp_path):
    profile=replace(IWR1843Profile(),noise_enabled=False)
    # Artificially distant ground makes a four-PRI delay without changing the
    # production surface sampler or visibility code.
    altitude=(4*profile.pri_s+.5e-6)*299792458./2
    radar=FMCWRadar(profile,rf_scene=scene(tmp_path),clutter=configuration(32),samples_per_link=32)
    options={'position_m':[0,0,altitude],'orientation_rad':[0,np.pi/2,0]}
    first=radar.capture([],**options)
    assert not np.any(first.if_volts) and radar.last_render_diagnostics['pending_echoes']==32
    late=radar.capture([],**options,sim_time_ns=round(4*profile.pri_s*1e9),transmit_enabled=False)
    assert np.any(late.if_volts)
    assert radar.last_render_diagnostics['clutter_echoes']==32
    assert radar.last_render_diagnostics['target_echoes']==0
    expired=radar.capture([],**options,sim_time_ns=round(5*profile.pri_s*1e9),transmit_enabled=False)
    assert not np.any(expired.if_volts) and radar.last_render_diagnostics['pending_echoes']==0
