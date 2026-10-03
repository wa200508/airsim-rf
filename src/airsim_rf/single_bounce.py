"""Exhaustive first-order specular candidates for Sionna RT 2.2.0.

This adapter changes candidate discovery only. Sionna still checks visibility
and computes polarization, material response, antenna gain, delay and Doppler.
No reciprocity or radar/two-way propagation assumption is made.
"""
from fractions import Fraction
from functools import reduce
from math import gcd, lcm

def _plane_key(triangle):
    """Exact plane of the mesh's binary floating-point vertices.

    Integer canonicalization merges coplanar triangles without merging nearby
    surfaces or imposing a geometry tolerance. This runs only on mesh changes.
    """
    a, b, c = [[Fraction(float(x)) for x in v] for v in triangle]
    u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
    n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
    if not any(n):
        raise ValueError("Single-bounce solver requires nondegenerate mesh triangles")
    plane = n + [-sum(n[i]*a[i] for i in range(3))]
    scale = lcm(*(x.denominator for x in plane))
    integers = [int(x*scale) for x in plane]
    divisor = reduce(gcd, integers)
    sign = 1 if next(x for x in integers if x) > 0 else -1
    return tuple(sign*x//divisor for x in integers)


class _PlanarCandidates:
    def __init__(self, candidate_limit):
        self.candidate_limit = candidate_limit
        self._fingerprint = None
        self._buffers = None
        self.plane_count = 0
        self.mesh_rebuilds = 0

    def _planes(self, scene):
        import drjit as dr
        import mitsuba as mi

        shapes = scene.shapes()
        if any(not isinstance(shape, mi.Mesh) for shape in shapes):
            raise ValueError("Single-bounce solver supports triangle meshes only; use native for other shapes")
        buffers = [(shape.vertex_positions_buffer(), shape.faces_buffer()) for shape in shapes]
        fingerprint = tuple((shape, vertices.index, faces.index)
                            for shape, (vertices, faces) in zip(shapes, buffers))
        if fingerprint == self._fingerprint:
            return self._shape_ids, self._primitive_ids
        planes = {}
        for shape, (vertices, faces) in zip(shapes, buffers):
            xyz = vertices.numpy().reshape(-1, 3)
            indices = faces.numpy().reshape(-1, 3)
            shape_id = int(dr.reinterpret_array(mi.UInt, mi.MeshPtr(shape))[0])
            for primitive, triangle in enumerate(xyz[indices]):
                planes.setdefault(_plane_key(triangle), (shape_id, primitive))
        self.plane_count = len(planes)
        self._shape_ids = mi.UInt([p[0] for p in planes.values()])
        self._primitive_ids = mi.UInt([p[1] for p in planes.values()])
        # Retain the buffers so Dr.Jit cannot recycle their variable IDs while
        # the fingerprint is cached. Radio poses/materials are never cached.
        self._fingerprint, self._buffers = fingerprint, buffers
        self.mesh_rebuilds += 1
        return self._shape_ids, self._primitive_ids

    def __call__(self, *, mi_scene, src_positions, tgt_positions,
                 max_depth, max_num_paths_per_src, los, specular_reflection,
                 diffuse_reflection, refraction, diffraction, edge_diffraction,
                 **unused):
        import drjit as dr
        import mitsuba as mi
        from sionna.rt.constants import InteractionType
        from sionna.rt.constants import MIN_SEGMENT_LENGTH
        from sionna.rt.utils import spawn_ray_to
        from sionna.rt.path_solvers.paths_buffer import PathsBuffer

        if max_depth not in (0, 1) or any((diffuse_reflection, refraction, diffraction, edge_diffraction)):
            raise ValueError("Single-bounce solver supports depth 0/1, LoS and specular reflection only")
        sources, targets = dr.width(src_positions), dr.width(tgt_positions)
        planes = 0
        if max_depth and specular_reflection:
            shape_ids, primitive_ids = self._planes(mi_scene)
            planes = self.plane_count
        per_source = targets * (int(los) + planes)
        if per_source > max_num_paths_per_src:
            raise ValueError(f"Exhaustive candidates require path cap >= {per_source} per source")
        count = sources * per_source
        if count > self.candidate_limit:
            raise ValueError(f"Exhaustive candidate count {count} exceeds limit {self.candidate_limit}; simplify the RF mesh or use native")
        paths = PathsBuffer(count, max_depth, False)
        self.visibility = dr.full(mi.Bool, True, count)
        if los:
            width = sources * targets
            row = dr.arange(mi.UInt, width)
            origins = dr.repeat(src_positions, targets)
            endpoints = dr.tile(tgt_positions, sources)
            ray = spawn_ray_to(origins, endpoints)
            valid = dr.norm(endpoints-origins) > MIN_SEGMENT_LENGTH
            valid &= ~mi_scene.ray_test(ray, active=valid)
            dr.scatter(self.visibility, valid, row)
            dr.scatter(paths._src_indices, row // targets, row)
            dr.scatter(paths._tgt_indices, row % targets, row)
            # All direct slots bypass the reflection image method. Their
            # visibility mask is restored immediately afterward, before fields
            # are calculated. Keeping slots avoids recompilation when LoS
            # count changes as platforms move.
            dr.scatter(paths._valid, mi.Bool(True), row)
            for axis in ("x", "y", "z"):
                dr.scatter(getattr(paths, "_k_tx_"+axis), getattr(ray.d, axis), row)
                dr.scatter(getattr(paths, "_k_rx_"+axis), -getattr(ray.d, axis), row)
            paths.advance_paths_counter(width)
        if planes:
            width = sources * targets * planes
            lane = dr.arange(mi.UInt, width)
            plane = lane % planes
            source = lane // (targets * planes)
            target = (lane // planes) % targets
            row = paths.paths_counter + lane
            dr.scatter(paths._src_indices, source, row)
            dr.scatter(paths._tgt_indices, target, row)
            dr.scatter(paths.shapes.array, dr.gather(mi.UInt, shape_ids, plane), row)
            dr.scatter(paths.primitives.array, dr.gather(mi.UInt, primitive_ids, plane), row)
            dr.scatter(paths.interaction_types.array, mi.UInt(InteractionType.SPECULAR), row)
            dr.scatter(paths.probs.array, mi.Float(1), row)
            mesh = dr.reinterpret_array(mi.MeshPtr, dr.gather(mi.UInt, shape_ids, plane))
            primitive = dr.gather(mi.UInt, primitive_ids, plane)
            vertex = mesh.vertex_position(mesh.face_indices(primitive).x)
            dr.scatter(paths.vertices_x.array, vertex.x, row)
            dr.scatter(paths.vertices_y.array, vertex.y, row)
            dr.scatter(paths.vertices_z.array, vertex.z, row)
            # Any point on the candidate plane defines its image. The image
            # method traces the actual reflection and uses the material on
            # the actual intersected mesh.
            paths.advance_paths_counter(width)
        return paths


class _VisibleImageMethod:
    def __init__(self, image_method, candidates):
        self.image_method, self.candidates = image_method, candidates

    def __call__(self, **kwargs):
        paths = self.image_method(**kwargs)
        paths.valid &= self.candidates.visibility
        return paths


class SingleBouncePathSolver:
    """One-way, exhaustive LoS + first-order specular Sionna path solver.

    ``samples_per_src`` and ``seed`` are accepted for native API compatibility,
    but discovery has no random rays. Unsupported physics raises an error.
    Geometry edits invalidate the plane cache automatically. The native solver
    remains available for diffuse scattering, diffraction and deeper paths.
    """
    def __init__(self, *, candidate_limit=2_000_000):
        import sionna.rt as rt
        if rt.__version__ != "2.2.0":
            raise RuntimeError("Single-bounce adapter requires Sionna RT 2.2.0 private buffer API")
        if isinstance(candidate_limit, bool) or not isinstance(candidate_limit, int) or candidate_limit < 1:
            raise ValueError("candidate_limit must be a positive integer")
        self._solver = rt.PathSolver(deterministic=True)
        self._candidates = _PlanarCandidates(candidate_limit)
        self._solver._candidate_generator = self._candidates
        self._solver._image_method = _VisibleImageMethod(self._solver._image_method, self._candidates)

    @property
    def plane_count(self):
        return self._candidates.plane_count

    @property
    def mesh_rebuilds(self):
        return self._candidates.mesh_rebuilds

    def __call__(self, scene, **kwargs):
        kwargs.setdefault("max_depth", 1)
        kwargs.setdefault("refraction", False)
        return self._solver(scene, **kwargs)
