"""ProjectAirSim geometry bindings and paused readback, with no runtime imports.

Constructing a plan is offline. Applying it or taking a snapshot calls only the
provided World handle; these functions never connect, step or reload a world.
"""
from copy import deepcopy

import numpy as np
from scipy.spatial.transform import Rotation

from .geometry import geometry_digest, validate_geometry
from .usd_geometry import affine


def _pose_matrix(pose):
    translation, quaternion = pose['translation'], pose['rotation']
    position = np.asarray([translation[k] for k in ('x', 'y', 'z')], float)
    q = np.asarray([quaternion[k] for k in ('x', 'y', 'z', 'w')], float)
    if not np.isfinite(position).all() or not np.isfinite(q).all() or abs(np.linalg.norm(q)-1) > 1e-5:
        raise ValueError('AirSim object pose must have finite position and unit quaternion')
    result = np.eye(4)
    result[:3, :3] = Rotation.from_quat(q).as_matrix()
    result[:3, 3] = position
    return result


def _decompose(transform):
    """Positive scale and rotation only: Unreal actor transforms cannot carry shear."""
    scale = np.linalg.norm(transform[:3, :3], axis=0)
    if np.any(scale <= 0) or not np.isfinite(scale).all():
        raise ValueError('Invalid actor scale')
    rotation = transform[:3, :3] / scale
    if (not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-9, rtol=0)
            or np.linalg.det(rotation) < 0):
        raise ValueError('Actor placement requires positive scale without shear/reflection; bake the asset first')
    q = Rotation.from_matrix(rotation).as_quat()
    pose = {'frame_id': 'DEFAULT_ID',
            'translation': dict(zip(('x', 'y', 'z'), transform[:3, 3].tolist())),
            'rotation': dict(zip(('x', 'y', 'z', 'w'), q.tolist()))}
    return pose, scale.tolist()


def placement_plan(document, bindings):
    """Derive placements from the SAME mesh transforms used by the RF exporter.

    local_to_actor_m maps USD local vertex numbers into the packaged actor's
    unscaled NED-aligned local metre coordinates. Asset provenance is an explicit
    operator assertion; this API cannot inspect Unreal collision triangles.
    """
    document = validate_geometry(document)
    if not isinstance(bindings, dict) or bindings.get('version') != 1:
        raise ValueError('Geometry bindings version 1 required')
    if set(bindings['objects']) != {obj['id'] for obj in document['objects']}:
        raise ValueError('Every RF object needs exactly one simulator binding')
    plan, names = [], set()
    for obj in document['objects']:
        entry = bindings['objects'][obj['id']]['simulator']
        name = entry['object_name']
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError('Simulator object names must be nonempty and unique')
        names.add(name)
        local = affine(entry['local_to_actor_m'], name+'.local_to_actor_m')
        mesh = None
        if entry['asset_path'] == 'generated:glb':
            # Bake all affine linear terms (including shear/reflection) into the
            # shared mesh. Only translation remains on the simulator actor.
            local = np.asarray(obj['local_to_ned_m']).copy()
            local[:3, 3] = 0
            vertices = np.asarray(obj['vertices_local']) @ local[:3, :3].T
            faces = np.asarray(obj['faces'])
            if np.linalg.det(local[:3, :3]) < 0:
                faces = faces[:, [0, 2, 1]]
            mesh = {'vertices_actor_m': vertices.tolist(), 'faces': faces.tolist()}
        actor = np.asarray(obj['local_to_ned_m']) @ np.linalg.inv(local)
        pose, scale = _decompose(actor)
        plan.append({'id': obj['id'], 'object_name': name, 'asset_path': entry['asset_path'],
                     'asset_provenance': entry['asset_provenance'],
                     'pose': pose, 'scale': scale, 'enable_physics': False})
        plan[-1]['local_to_actor_m'] = local.tolist()
        if mesh is not None:
            plan[-1]['mesh'] = mesh
    return {'version': 1, 'geometry_sha256': geometry_digest(document), 'objects': plan,
            'scope': 'placement plan; packaged mesh/collision equivalence requires independent qualification'}


def spawn_placements(world, plan):
    """Explicit opt-in mutation of a dedicated paused world, never called by capture.

    No overwrites or automatic cleanup: a partial failure reports created names
    and leaves them available for inspection. Caller owns scene lifecycle.
    """
    if not world.is_paused():
        raise RuntimeError('Pause the dedicated simulator before spawning geometry')
    epoch = int(world.get_sim_time())
    created = []
    try:
        for obj in plan['objects']:
            if obj['object_name'] in world.list_objects('.*'):
                raise RuntimeError(f'Object name already exists: {obj["object_name"]}')
            if 'mesh' in obj:
                from .glb_geometry import triangle_glb
                payload = triangle_glb(**obj['mesh'])
                actual = world.spawn_object_from_file(obj['object_name'], 'gltf', payload, True,
                                                     obj['pose'], obj['scale'], False)
            else:
                actual = world.spawn_object(obj['object_name'], obj['asset_path'], obj['pose'],
                                            obj['scale'], obj['enable_physics'])
            if actual:
                created.append(actual)
            if actual != obj['object_name']:
                raise RuntimeError(f'Object spawn failed or name collided: requested {obj["object_name"]}, got {actual!r}')
            if actual not in world.list_objects('.*'):
                raise RuntimeError(f'Object loader returned a name without creating it: {actual}')
            # The pinned loader can return the requested name on parse failure.
            _pose_matrix(world.get_object_pose(actual))
            scale = np.asarray(world.get_object_scale(actual), float)
            if scale.shape != (3,) or not np.isfinite(scale).all() or np.any(scale <= 0):
                raise RuntimeError(f'Object spawn did not create a readable actor: {actual}')
        if not world.is_paused() or int(world.get_sim_time()) != epoch:
            raise RuntimeError('World advanced during geometry placement')
    except Exception as error:
        raise RuntimeError(f'Placement incomplete; created objects retained: {created}; {error}') from error
    return created


class AirSimGeometryBinding:
    """Snapshot bound actors and reject stale static geometry before RF capture."""

    def __init__(self, document, bindings, *, tolerance_m=1e-5):
        self.document = validate_geometry(document)
        self.bindings = deepcopy(bindings)
        self.plan = placement_plan(self.document, self.bindings)
        if not np.isfinite(tolerance_m) or tolerance_m <= 0:
            raise ValueError('Geometry tolerance must be finite and positive')
        self.tolerance_m = float(tolerance_m)
        self.last_report = None

    def snapshot(self, world, *, expected_epoch=None):
        """Return a complete geometry revision from a paused actor-pose readback.

        Scale is sampled each time. Topology/material edits require a new asset
        bundle and are not discoverable through the current World pose API.
        """
        if not world.is_paused():
            raise RuntimeError('Pause the simulator before geometry readback')
        epoch = int(world.get_sim_time())
        if expected_epoch is not None and epoch != expected_epoch:
            raise RuntimeError('Geometry epoch differs from radio snapshot epoch')
        result = deepcopy(self.document)
        planned = {obj['id']: obj for obj in self.plan['objects']}
        for obj in result['objects']:
            binding = self.bindings['objects'][obj['id']]['simulator']
            name = binding['object_name']
            pose = _pose_matrix(world.get_object_pose(name))
            scale = np.asarray(world.get_object_scale(name), float)
            if scale.shape != (3,) or not np.isfinite(scale).all() or np.any(scale <= 0):
                raise ValueError(f'{name}: invalid object scale')
            transform = pose @ np.diag([*scale, 1.]) @ affine(planned[obj['id']]['local_to_actor_m'], name)
            obj['local_to_ned_m'] = transform.tolist()
        if not world.is_paused() or int(world.get_sim_time()) != epoch:
            raise RuntimeError('Simulation advanced during geometry readback')
        return epoch, validate_geometry(result)

    def require_static_match(self, world, epoch):
        """Gate the current static RF scene; moving obstacles require re-export/reload.

        This checks transformed vertices, not actual simulator collision surfaces.
        """
        _, actual = self.snapshot(world, expected_epoch=epoch)
        errors = {}
        for expected, observed in zip(self.document['objects'], actual['objects']):
            vertices = np.asarray(expected['vertices_local'])
            a, b = np.asarray(expected['local_to_ned_m']), np.asarray(observed['local_to_ned_m'])
            delta = vertices @ (a[:3, :3]-b[:3, :3]).T + a[:3, 3]-b[:3, 3]
            errors[expected['id']] = float(np.max(np.linalg.norm(delta, axis=1)))
        report = {'sim_time_ns': int(epoch), 'geometry_sha256': geometry_digest(self.document),
                  'observed_geometry_sha256': geometry_digest(actual),
                  'maximum_vertex_error_m': errors, 'tolerance_m': self.tolerance_m}
        self.last_report = report
        if any(not np.isfinite(v) or v > self.tolerance_m for v in errors.values()):
            raise RuntimeError(f'AirSim and static RF geometry differ; rebuild/reload before capture: {errors}')
        return report


def nearest_intersections(document, origins_ned_m, directions_ned, *, maximum_distance_m):
    """CPU triangle-ray reference for future independent probe comparisons.

    Distances are metres; directions are normalized. This does not contact a
    simulator or establish agreement until compared to independent readbacks.
    """
    document = validate_geometry(document)
    origins, directions = np.asarray(origins_ned_m, float), np.asarray(directions_ned, float)
    if (origins.ndim != 2 or origins.shape[1] != 3 or origins.shape != directions.shape
            or not np.isfinite(origins).all() or not np.isfinite(directions).all()
            or np.any(np.linalg.norm(directions, axis=1) == 0)
            or not np.isfinite(maximum_distance_m) or maximum_distance_m <= 0):
        raise ValueError('Finite Nx3 rays, nonzero directions and positive range required')
    directions = directions / np.linalg.norm(directions, axis=1)[:, None]
    triangles, identifiers = [], []
    for obj in document['objects']:
        matrix = np.asarray(obj['local_to_ned_m'])
        vertices = np.asarray(obj['vertices_local']) @ matrix[:3, :3].T + matrix[:3, 3]
        mesh = vertices[np.asarray(obj['faces'])]
        triangles.extend(mesh)
        identifiers.extend([obj['id']]*len(mesh))
    triangles = np.asarray(triangles)
    a = triangles[:, 0]
    e1, e2 = triangles[:, 1]-a, triangles[:, 2]-a
    hits = []
    for origin, direction in zip(origins, directions):
        h = np.cross(direction, e2)
        determinant = np.einsum('ij,ij->i', e1, h)
        valid = np.abs(determinant) > 1e-12*np.linalg.norm(e1, axis=1)*np.linalg.norm(e2, axis=1)
        inverse = np.divide(1., determinant, out=np.zeros_like(determinant), where=valid)
        s = origin-a
        u = inverse*np.einsum('ij,ij->i', s, h)
        q = np.cross(s, e1)
        v = inverse*(q @ direction)
        distance = inverse*np.einsum('ij,ij->i', e2, q)
        valid &= (u >= 0) & (v >= 0) & (u+v <= 1) & (distance >= 0) & (distance <= maximum_distance_m)
        if not np.any(valid):
            hits.append(None)
        else:
            index = int(np.argmin(np.where(valid, distance, np.inf)))
            hits.append({'object_id': identifiers[index], 'distance_m': float(distance[index]),
                         'position_ned_m': (origin+direction*distance[index]).tolist()})
    return hits


def main():
    """Write an offline placement plan; never connect to or modify a simulator."""
    import argparse
    import json
    from pathlib import Path
    from .geometry import read_bundle
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    document, _, bindings = read_bundle(args.bundle)
    plan = placement_plan(document, bindings)
    with args.output.open('x') as stream:
        stream.write(json.dumps(plan, indent=2)+'\n')


if __name__ == '__main__':
    main()
