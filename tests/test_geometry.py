"""CPU checks of the USD contract and simulator geometry guard."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from airsim_rf.geometry import export_sionna_geometry, read_bundle, rf_mesh
from airsim_rf.geometry_sync import AirSimGeometryBinding, placement_plan, nearest_intersections, spawn_placements
from airsim_rf.usd_geometry import import_usd

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def imported():
    pytest.importorskip('pxr')
    return import_usd(ROOT/'examples/geometry/shared-world.usda', ROOT/'examples/geometry/shared-world.rf.json')


def test_usd_world_positions(imported):
    document, provenance, bindings = imported
    objects = {obj['id']:obj for obj in document['objects']}
    np.testing.assert_allclose(objects['Building']['local_to_ned_m'],
        [[2,0,0,5],[0,-2,0,0],[0,0,-2,-1],[0,0,0,1]])
    assert provenance['up_axis'] == 'Z'
    assert bindings['objects']['Wall']['prim_path'] == '/World/Wall'
    vertices,_ = rf_mesh(objects['Ground'])
    assert vertices[:,2].max() == 0


def test_bundle_hashes_and_identity(imported, tmp_path):
    document, provenance, bindings = imported
    export_sionna_geometry(document,tmp_path/'bundle',provenance=provenance,bindings=bindings)
    actual, manifest, actual_bindings = read_bundle(tmp_path/'bundle')
    assert actual == document
    assert actual_bindings == bindings
    assert manifest['load_options'] == {'merge_shapes':False}
    (tmp_path/'bundle/Building.ply').write_text('changed')
    with pytest.raises(ValueError,match='content changed'):
        read_bundle(tmp_path/'bundle')


class World:
    def __init__(self,plan):
        self.epoch=0
        self.objects={o['object_name']:deepcopy(o) for o in plan['objects']}
    def is_paused(self): return True
    def get_sim_time(self): return self.epoch
    def get_object_pose(self,name): return self.objects[name]['pose']
    def get_object_scale(self,name): return self.objects[name]['scale']


def test_shared_placement_guard_and_stale_rejection(imported):
    document,_,bindings=imported
    plan=placement_plan(document,bindings)
    world=World(plan)
    guard=AirSimGeometryBinding(document,bindings)
    report=guard.require_static_match(world,0)
    assert max(report['maximum_vertex_error_m'].values()) < 1e-12
    world.objects['RFSharedWall']['pose']['translation']['x']+=.01
    with pytest.raises(RuntimeError,match='geometry differ'):
        guard.require_static_match(world,0)


def test_snapshot_rejects_epoch_change(imported):
    document,_,bindings=imported
    world=World(placement_plan(document,bindings))
    getter=world.get_object_pose
    def changing(name):
        world.epoch+=1
        return getter(name)
    world.get_object_pose=changing
    with pytest.raises(RuntimeError,match='advanced'):
        AirSimGeometryBinding(document,bindings).snapshot(world)


def test_cpu_rays_match_analytic_box_faces(imported):
    document,_,_=imported
    hits=nearest_intersections(document,[[0,0,-1],[5,-5,-1],[0,0,-5]],
                              [[1,0,0],[0,1,0],[0,0,1]],maximum_distance_m=12)
    assert [h['object_id'] for h in hits] == ['Building','Building','Ground']
    np.testing.assert_allclose([h['distance_m'] for h in hits],[4,4,5])


@pytest.mark.parametrize('replacement,match',[
    ('metersPerUnit = 1','explicitly author'),
    ('uniform token subdivisionScheme = "none"','subdivisionScheme'),
])
def test_missing_stage_metadata_and_subdivision_rejected(tmp_path,replacement,match):
    pytest.importorskip('pxr')
    text=(ROOT/'examples/geometry/shared-world.usda').read_text().replace(replacement,'')
    stage=tmp_path/'scene.usda';stage.write_text(text)
    with pytest.raises(ValueError,match=match):
        import_usd(stage,ROOT/'examples/geometry/shared-world.rf.json')


def test_omitted_geometry_requires_exclusion(tmp_path):
    pytest.importorskip('pxr')
    profile=json.loads((ROOT/'examples/geometry/shared-world.rf.json').read_text())
    del profile['objects']['Wall']
    path=tmp_path/'profile.json';path.write_text(json.dumps(profile))
    with pytest.raises(ValueError,match='selection or explicit exclusion'):
        import_usd(ROOT/'examples/geometry/shared-world.usda',path)


def test_native_instance_and_reflected_winding(tmp_path):
    pytest.importorskip('pxr')
    from pxr import Usd, UsdGeom, Gf
    stage=Usd.Stage.CreateNew(str(tmp_path/'instance.usda'))
    UsdGeom.SetStageMetersPerUnit(stage, .01)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.Xform.Define(stage, '/Prototype')
    mesh=UsdGeom.Mesh.Define(stage,'/Prototype/Triangle')
    mesh.CreatePointsAttr([(0,0,0),(100,0,0),(0,200,0)])
    mesh.CreateFaceVertexCountsAttr([3]);mesh.CreateFaceVertexIndicesAttr([0,1,2])
    mesh.CreateSubdivisionSchemeAttr('none')
    instance=stage.DefinePrim('/Instance','Xform')
    instance.GetReferences().AddInternalReference('/Prototype');instance.SetInstanceable(True)
    transform=UsdGeom.Xformable(instance)
    transform.AddTranslateOp().Set(Gf.Vec3d(300,400,500))
    transform.AddScaleOp().Set(Gf.Vec3f(-2,3,1))
    stage.GetRootLayer().Save()
    p=json.loads((ROOT/'examples/geometry/shared-mesh-world.rf.json').read_text())
    binding=p['objects']['Building'];binding['prim_path']='/Instance/Triangle'
    p['objects']={'Instance':binding};p['exclusions']={'/Prototype/Triangle':'Template only'}
    profile=tmp_path/'profile.json';profile.write_text(json.dumps(p))
    document,_,bindings=import_usd(tmp_path/'instance.usda',profile)
    vertices,faces=rf_mesh(document['objects'][0])
    np.testing.assert_allclose(vertices,[[3,4,5],[1,4,5],[3,10,5]])
    assert faces.tolist()==[[0,2,1]]
    normal=np.cross(vertices[faces[0,1]]-vertices[faces[0,0]],vertices[faces[0,2]]-vertices[faces[0,0]])
    assert normal[2]>0
    plan=placement_plan(document,bindings)
    guard=AirSimGeometryBinding(document,bindings)
    assert max(guard.require_static_match(World(plan),0)['maximum_vertex_error_m'].values())<1e-12


def test_glb_layout_and_axis_mapping():
    import struct
    from airsim_rf.glb_geometry import triangle_glb
    data=triangle_glb([[1,2,3],[4,2,3],[1,5,3]],[[0,1,2]])
    assert struct.unpack_from('<III',data)==(0x46546c67,2,len(data))
    size,kind=struct.unpack_from('<II',data,12)
    doc=json.loads(data[20:20+size]);assert kind==0x4e4f534a
    binary_offset=20+size+8
    points=np.frombuffer(data,dtype='<f4',count=9,offset=binary_offset).reshape(-1,3)
    np.testing.assert_allclose(points,[[1,-3,2],[4,-3,2],[1,-3,5]])
    assert doc['accessors'][0]['max']==[4.,-3.,5.]


def test_generated_mesh_loader_false_success_rejected(imported):
    document,_,bindings=imported
    for binding in bindings['objects'].values():
        binding['simulator']['asset_path']='generated:glb'
    plan=placement_plan(document,bindings)
    world=World(plan)
    world.list_objects=lambda _: []
    world.spawn_object_from_file=lambda name,*args: name
    with pytest.raises(RuntimeError,match='without creating'):
        spawn_placements(world,plan)


def test_generated_mesh_bakes_shear_and_reflection(imported):
    document,_,bindings=imported
    obj=document['objects'][0]
    matrix=np.asarray(obj['local_to_ned_m'])
    matrix[:3,:3]=[[-3,.7,0],[0,2,0],[0,0,1]]
    obj['local_to_ned_m']=matrix.tolist()
    bindings['objects'][obj['id']]['simulator']['asset_path']='generated:glb'
    plan=placement_plan(document,bindings)
    mesh=plan['objects'][0]['mesh']
    rf_vertices,rf_faces=rf_mesh(obj)
    translation=np.array([plan['objects'][0]['pose']['translation'][k] for k in 'xyz'])
    np.testing.assert_allclose((np.asarray(mesh['vertices_actor_m'])+translation)*[1,-1,-1],rf_vertices)
    np.testing.assert_array_equal(mesh['faces'],rf_faces)
    assert max(AirSimGeometryBinding(document,bindings).require_static_match(World(plan),0)['maximum_vertex_error_m'].values())<1e-12


def test_revision_boundary_requires_new_geometry_and_binding(imported,tmp_path):
    document,provenance,bindings=imported
    old=AirSimGeometryBinding(document,bindings)
    world=World(old.plan)
    world.objects['RFSharedWall']['pose']['translation']['x']+=1
    with pytest.raises(RuntimeError,match='rebuild/reload'):
        old.require_static_match(world,0)
    epoch,snapshot=old.snapshot(world)
    snapshot['revision']='2'
    export_sionna_geometry(snapshot,tmp_path/'revision2',provenance=provenance,bindings=bindings)
    updated,manifest,updated_bindings=read_bundle(tmp_path/'revision2')
    new=AirSimGeometryBinding(updated,updated_bindings)
    assert new.require_static_match(world,epoch)['geometry_sha256']==manifest['scene_sha256']
    assert manifest['scene_sha256']!=old.require_static_match(World(old.plan),0)['geometry_sha256']
    # Different content hashes require a fresh scene/receiver; old bundle is
    # immutable and continues to reject the moved actor.
    with pytest.raises(RuntimeError,match='rebuild/reload'):
        old.require_static_match(world,0)
