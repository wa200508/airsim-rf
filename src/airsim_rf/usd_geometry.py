"""Offline OpenUSD RF profile importer. Never imports either simulation runtime."""
import argparse
import json
from pathlib import Path

import numpy as np

from .geometry import (_fields, _identifier, export_sionna_geometry, file_digest,
                       validate_geometry)


def affine(value, name):
    matrix = np.asarray(value, dtype=float)
    if (matrix.shape != (4, 4) or not np.isfinite(matrix).all()
            or not np.array_equal(matrix[3], [0, 0, 0, 1])
            or not np.isfinite(np.linalg.det(matrix[:3, :3]))
            or np.linalg.det(matrix[:3, :3]) == 0):
        raise ValueError(f'{name}: finite nonsingular affine 4x4 matrix required')
    return matrix


def read_profile(path):
    """Explicit RF selection; unselected geometry requires an exclusion reason."""
    profile = json.loads(Path(path).read_text())
    _fields(profile, 'profile_version scene_id revision geometry_kind stage_up_axis '
            'stage_meters_to_ned_m geodetic_anchor materials objects exclusions', 'USD RF profile')
    if type(profile['profile_version']) is not int or profile['profile_version'] != 1:
        raise ValueError('Only USD RF profile version 1 is supported')
    _identifier(profile['scene_id'])
    if profile['stage_up_axis'] not in ('Y', 'Z'):
        raise ValueError('stage_up_axis must be Y or Z')
    matrix = affine(profile['stage_meters_to_ned_m'], 'stage_meters_to_ned_m')
    rotation = matrix[:3, :3]
    if (not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-10, rtol=0)
            or np.linalg.det(rotation) < 0):
        raise ValueError('Stage metre to NED mapping must be a proper rigid transform')
    up = [0, 1, 0] if profile['stage_up_axis'] == 'Y' else [0, 0, 1]
    if not np.allclose(rotation @ up, [0, 0, -1], atol=1e-10, rtol=0):
        raise ValueError('Stage up axis must map to NED up (negative z)')
    anchor = profile['geodetic_anchor']
    _fields(anchor, 'latitude_deg longitude_deg altitude_hae_m', 'geodetic_anchor')
    from .ams.dis import LocalEarthFrame
    LocalEarthFrame(**anchor)  # Coordinate arithmetic only; no sockets are created.
    if not isinstance(profile['objects'], dict) or not profile['objects']:
        raise ValueError('Profile must map stable object IDs to USD prims')
    paths, names = set(), set()
    for name, binding in profile['objects'].items():
        _identifier(name)
        _fields(binding, 'prim_path material simulator identities', name)
        prim_path = binding['prim_path']
        if not isinstance(prim_path, str) or not prim_path.startswith('/') or prim_path in paths:
            raise ValueError('Each object requires a unique absolute prim path')
        paths.add(prim_path)
        simulator = binding['simulator']
        _fields(simulator, 'object_name asset_path local_to_actor_m asset_provenance', name+'.simulator')
        for key in ('object_name', 'asset_path', 'asset_provenance'):
            if not isinstance(simulator[key], str) or not simulator[key].strip():
                raise ValueError(f'{name}: simulator {key} is required')
        if simulator['object_name'] in names:
            raise ValueError('This profile requires one mesh per simulator object')
        names.add(simulator['object_name'])
        affine(simulator['local_to_actor_m'], name+'.local_to_actor_m')
        ids = binding['identities']
        _fields(ids, 'dis_entity_id oms_system_id oms_subsystem_id rf_aperture_ids', name+'.identities')
        if ids['dis_entity_id'] is not None:
            dis = ids['dis_entity_id']
            if not isinstance(dis, list) or len(dis) != 3 or any(type(v) is not int or not 1 <= v <= 65535 for v in dis):
                raise ValueError('DIS identity must be three nonzero uint16 values or null')
        from uuid import UUID
        for key in ('oms_system_id', 'oms_subsystem_id'):
            if ids[key] is not None:
                UUID(ids[key])
        apertures = ids['rf_aperture_ids']
        if not isinstance(apertures, list) or any(not isinstance(v, str) or not v for v in apertures):
            raise ValueError('rf_aperture_ids must be a list of nonempty strings')
    if not isinstance(profile['exclusions'], dict):
        raise ValueError('exclusions must map prim paths to reasons')
    for path, reason in profile['exclusions'].items():
        if not path.startswith('/') or not isinstance(reason, str) or not reason.strip() or path in paths:
            raise ValueError('Exclusions need absolute paths, reasons and no selected objects')
    return profile


def import_usd(stage_path, profile_path):
    """Compose a local stage using USD; import static, explicitly selected triangles.

    No hand-written USD parser, fan triangulation or implicit material inference.
    Time-varying geometry/transforms, subdivision and skinned meshes fail closed.
    Native instance proxies are evaluated at their composed world transforms.
    """
    try:
        from pxr import Usd, UsdGeom
    except ImportError as error:
        raise RuntimeError('OpenUSD Python bindings are required for import (pxr; install the geometry extra)') from error
    profile_hash = file_digest(profile_path)
    profile = read_profile(profile_path)
    source = Path(stage_path).resolve()
    stage = Usd.Stage.Open(str(source), load=Usd.Stage.LoadAll)
    if stage is None:
        raise ValueError(f'Cannot open USD stage: {source}')
    if not stage.HasAuthoredMetadata('metersPerUnit') or not stage.HasAuthoredMetadata('upAxis'):
        raise ValueError('USD root stage must explicitly author metersPerUnit and upAxis')
    unit = float(UsdGeom.GetStageMetersPerUnit(stage))
    if not np.isfinite(unit) or unit <= 0:
        raise ValueError('USD metersPerUnit must be finite and positive')
    if str(UsdGeom.GetStageUpAxis(stage)) != profile['stage_up_axis']:
        raise ValueError('Stage up axis differs from RF profile')
    # Local file layers only in v1: hash every composed layer, reject resolver-only
    # content rather than recording incomplete provenance.
    layers = {}
    for layer in stage.GetUsedLayers():
        if layer == stage.GetSessionLayer() and layer.empty:
            continue
        path = Path(layer.realPath)
        if not layer.realPath or not path.is_file():
            raise ValueError(f'Only local file layers are supported: {layer.identifier}')
        layers[str(path.resolve())] = file_digest(path)
    all_prims = list(Usd.PrimRange.Stage(stage, Usd.TraverseInstanceProxies()))
    if any(p.HasPayload() and not p.IsLoaded() for p in all_prims):
        raise ValueError('USD payloads must be loaded before export')
    geometry = {str(p.GetPath()): p for p in all_prims
                if p.IsA(UsdGeom.Gprim) or p.IsA(UsdGeom.PointInstancer)}
    selected = {b['prim_path'] for b in profile['objects'].values()}
    excluded = set(profile['exclusions'])
    if selected - geometry.keys() or excluded - geometry.keys():
        raise ValueError('Selected or excluded prim paths do not identify active composed geometry')
    if geometry.keys() - selected - excluded:
        raise ValueError(f'Geometry needs selection or explicit exclusion: {sorted(geometry.keys()-selected-excluded)}')
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    scale = np.diag([unit, unit, unit, 1.])
    to_ned = affine(profile['stage_meters_to_ned_m'], 'stage_meters_to_ned_m') @ scale
    objects = []
    for name, binding in profile['objects'].items():
        prim = geometry[binding['prim_path']]
        if not prim.IsA(UsdGeom.Mesh):
            raise ValueError(f'{prim.GetPath()}: export as a triangle Mesh first')
        ancestor = prim
        while ancestor and not ancestor.IsPseudoRoot():
            if (ancestor.GetTypeName() in ('SkelRoot', 'Skeleton')
                    or any(str(schema).startswith('Skel') for schema in ancestor.GetAppliedSchemas())):
                raise ValueError(f'{prim.GetPath()}: skeletal deformation is unsupported')
            if any(a.GetNumTimeSamples() for a in ancestor.GetAttributes()):
                raise ValueError(f'{ancestor.GetPath()}: profile v1 requires static attributes')
            ancestor = ancestor.GetParent()
        mesh = UsdGeom.Mesh(prim)
        if str(mesh.GetSubdivisionSchemeAttr().Get()) != 'none':
            raise ValueError(f'{prim.GetPath()}: subdivisionScheme must be none')
        if mesh.GetHoleIndicesAttr().Get():
            raise ValueError(f'{prim.GetPath()}: mesh holes are unsupported')
        counts = np.asarray(mesh.GetFaceVertexCountsAttr().Get())
        indices = np.asarray(mesh.GetFaceVertexIndicesAttr().Get())
        if not counts.size or np.any(counts != 3) or indices.size != 3*counts.size:
            raise ValueError(f'{prim.GetPath()}: triangulate explicitly before import')
        faces = indices.reshape(-1, 3)
        orientation = str(mesh.GetOrientationAttr().Get())
        if orientation == 'leftHanded':
            faces = faces[:, [0, 2, 1]]
        elif orientation != 'rightHanded':
            raise ValueError(f'{prim.GetPath()}: unsupported orientation')
        # Gf uses row-vector convention; our normalized snapshot uses columns.
        transform = to_ned @ np.asarray(cache.GetLocalToWorldTransform(prim), float).T
        objects.append({'id': name, 'material': binding['material'],
                        'vertices_local': np.asarray(mesh.GetPointsAttr().Get(), float).tolist(),
                        'faces': faces.tolist(), 'local_to_ned_m': transform.tolist()})
    document = validate_geometry({'schema_version': 1, 'scene_id': profile['scene_id'],
        'revision': profile['revision'], 'source': {'adapter': 'openusd-static-v1',
        'version': '.'.join(map(str, Usd.GetVersion())), 'asset': str(source),
        'revision': file_digest(source), 'geometry_kind': profile['geometry_kind']},
        'materials': profile['materials'], 'objects': objects})
    # Detect source edits during composition/export preparation.
    if (file_digest(profile_path) != profile_hash
            or any(file_digest(path) != digest for path, digest in layers.items())):
        raise RuntimeError('USD source layer changed during import')
    provenance = {'profile_version': 1, 'profile_sha256': profile_hash,
                  'layers_sha256': layers, 'meters_per_unit': unit,
                  'up_axis': profile['stage_up_axis'], 'exclusions': profile['exclusions'],
                  'material_policy': 'explicit RF profile; visual shaders are not RF properties'}
    bindings = {'version': 1, 'geodetic_anchor': profile['geodetic_anchor'],
                'objects': profile['objects']}
    return document, provenance, bindings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', type=Path)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    document, provenance, bindings = import_usd(args.stage, args.profile)
    export_sionna_geometry(document, args.output, provenance=provenance, bindings=bindings)


if __name__ == '__main__':
    main()
