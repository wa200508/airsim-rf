"""First-order diffuse coverage using TX/RX antenna importance proposals.

Sionna's material/field model is preserved; this is not a calibrated stochastic
rough-ground model. Samples cover both ends of every independent TX/RX link.
"""
from dataclasses import dataclass
from time import perf_counter

import numpy as np

from .single_bounce import _PlanarCandidates, _VisibleImageMethod
from .profiling import profile_range


@dataclass(frozen=True)
class _AngularProposal:
    probability: np.ndarray
    uniform_fraction: float
    nz: int = 64
    nphi: int = 128

    @classmethod
    def from_patterns(cls, patterns, *, receive, uniform_fraction):
        import drjit as dr
        import mitsuba as mi
        from sionna.rt.antenna_pattern import antenna_pattern_to_world_implicit

        nz, nphi = 64, 128
        z = np.repeat(-1+(np.arange(nz)+.5)*2/nz, nphi)
        phi = np.tile(-np.pi+(np.arange(nphi)+.5)*2*np.pi/nphi, nz)
        r = np.sqrt(1-z*z)
        directions = mi.Vector3f(r*np.cos(phi), r*np.sin(phi), z)
        gain = np.zeros(nz*nphi)
        for pattern in patterns:
            field = antenna_pattern_to_world_implicit(
                pattern, mi.Matrix3f(1), directions,
                direction="in" if receive else "out")
            gain += dr.squared_norm(field).numpy().astype(float)
        if not np.all(np.isfinite(gain)) or np.any(gain < 0):
            raise ValueError("Antenna power must be finite and nonnegative")
        weighted = gain/gain.sum() if gain.sum() > 0 else np.full(gain.size, 1/gain.size)
        probability = (1-uniform_fraction)*weighted + uniform_fraction/gain.size
        return cls(probability, uniform_fraction, nz, nphi)

    def draw(self, rng, count):
        # Sampling is continuous inside equal-solid-angle cells. The PDF is
        # piecewise constant, not a discrete set of antenna-axis directions.
        cells = rng.choice(self.probability.size, size=count, p=self.probability)
        z = -1+(cells//self.nphi+rng.random(count))*2/self.nz
        phi = -np.pi+(cells % self.nphi+rng.random(count))*2*np.pi/self.nphi
        r = np.sqrt(np.maximum(0, 1-z*z))
        return np.stack((r*np.cos(phi), r*np.sin(phi), z))

    def pdf(self, directions):
        import drjit as dr
        import mitsuba as mi
        z = dr.minimum(mi.UInt(dr.maximum((directions.z+1)*self.nz/2, 0)), self.nz-1)
        phi = dr.atan2(directions.y, directions.x)
        azimuth = dr.minimum(mi.UInt(dr.maximum((phi+dr.pi)*self.nphi/(2*dr.pi), 0)), self.nphi-1)
        cell = z*self.nphi+azimuth
        return dr.gather(mi.Float, mi.Float(self.probability), cell)*self.probability.size/(4*dr.pi)


class _ScatteringCandidates(_PlanarCandidates):
    def __init__(self, candidate_limit, uniform_fraction, cache_sampling=True):
        super().__init__(candidate_limit)
        self.uniform_fraction = uniform_fraction
        self.cache_sampling = cache_sampling
        self._draw_cache = None
        self.scene = None
        self.synthetic_array = True
        self.last_sampling = {}
        self.last_timings = {}

    def __call__(self, **kwargs):
        import drjit as dr
        import mitsuba as mi
        from sionna.rt.constants import InteractionType, MIN_SEGMENT_LENGTH
        from sionna.rt.path_solvers.paths_buffer import PathsBuffer
        from sionna.rt.utils import rotation_matrix, spawn_ray_to

        diffuse = kwargs["diffuse_reflection"]
        self.last_timings = {}
        if diffuse and any(not isinstance(shape, mi.Mesh) for shape in kwargs["mi_scene"].shapes()):
            raise ValueError("First-order scattering supports triangle meshes only")
        if diffuse and kwargs["max_depth"] != 1:
            raise ValueError("Diffuse sampling requires exactly one interaction")
        samples = kwargs["samples_per_src"]
        if diffuse and samples < 2:
            raise ValueError("Use at least two samples/link to cover both TX and RX proposals")
        native_options = dict(kwargs, diffuse_reflection=False)
        base = super().__call__(**native_options)
        if not diffuse:
            self.last_sampling = {"diffuse_launches": 0}
            return base
        src, tgt = kwargs["src_positions"], kwargs["tgt_positions"]
        sources, targets = dr.width(src), dr.width(tgt)
        width = sources*targets*samples
        count = base.buffer_size+width
        if count > self.candidate_limit:
            raise ValueError(f"Scattering candidates {count} exceed limit {self.candidate_limit}")
        needed = count//sources
        if needed > kwargs["max_num_paths_per_src"]:
            raise ValueError(f"LoS/specular/diffuse candidates require path cap >= {needed} per source")
        paths = PathsBuffer(count, 1, False)
        base_row = dr.arange(mi.UInt, base.buffer_size)
        # Preserve the exhaustive specular paths and stable LoS slots.
        for name in ("_vertices_x", "_vertices_y", "_vertices_z", "_shapes", "_primitives",
                     "_interaction_types", "_probs"):
            dr.scatter(getattr(paths, name).array, getattr(base, name).array, base_row)
        for name in ("_valid", "_src_indices", "_tgt_indices", "_k_tx_x", "_k_tx_y", "_k_tx_z",
                     "_k_rx_x", "_k_rx_y", "_k_rx_z"):
            dr.scatter(getattr(paths, name), getattr(base, name), base_row)
        visibility = dr.full(mi.Bool, True, count)
        dr.scatter(visibility, self.visibility, base_row)
        self.visibility = visibility

        proposal_start = perf_counter()
        with profile_range("rf.channel.proposal_tables"):
            tx_proposal = _AngularProposal.from_patterns(self.scene.tx_array.antenna_pattern.patterns,
                          receive=False, uniform_fraction=self.uniform_fraction)
            rx_proposal = _AngularProposal.from_patterns(self.scene.rx_array.antenna_pattern.patterns,
                          receive=True, uniform_fraction=self.uniform_fraction)
        proposal_ms = (perf_counter()-proposal_start)*1000
        sampling_start = perf_counter()
        with profile_range("rf.channel.host_proposal_draws"):
            tx_count, rx_count = (samples+1)//2, samples//2
            pairs = sources*targets
            # Evaluate both patterns each call: mutable antenna closures must
            # invalidate sampling too. Poses are applied afresh below.
            key = (sources, targets, samples, kwargs['seed'],
                   tx_proposal.probability.tobytes(), rx_proposal.probability.tobytes())
            hit = self.cache_sampling and self._draw_cache is not None and self._draw_cache[0] == key
            if hit:
                local = self._draw_cache[1]
            else:
                rng = np.random.default_rng(kwargs['seed'])
                local = np.empty((3, pairs, samples))
                local[:, :, :tx_count] = tx_proposal.draw(rng, pairs*tx_count).reshape(3, pairs, tx_count)
                local[:, :, tx_count:] = rx_proposal.draw(rng, pairs*rx_count).reshape(3, pairs, rx_count)
                if self.cache_sampling:
                    local.flags.writeable = False
                    self._draw_cache = (key, local)
            # This region is strictly NumPy/host work, even with a CUDA backend.
            # Table preparation above includes backend evaluation and host export.
        sampling_ms = (perf_counter()-sampling_start)*1000
        local = mi.Vector3f(local.reshape(3, -1))
        dr.make_opaque(local)
        lane = dr.arange(mi.UInt, width)
        source, target = lane//(targets*samples), (lane//samples) % targets
        from_tx = lane % samples < tx_count
        tx = dr.gather(mi.Point3f, src, source)
        rx = dr.gather(mi.Point3f, tgt, target)
        tx_ort = self.scene.sources(self.synthetic_array, True)[1]
        rx_ort = self.scene.targets(self.synthetic_array, True)[1]
        dr.make_opaque(tx_ort, rx_ort)
        tx_rot = dr.gather(mi.Matrix3f, rotation_matrix(tx_ort), source)
        rx_rot = dr.gather(mi.Matrix3f, rotation_matrix(rx_ort), target)
        directions = dr.select(from_tx, tx_rot@local, rx_rot@local)
        origin = dr.select(from_tx, tx, rx)
        si = kwargs["mi_scene"].ray_intersect(mi.Ray3f(origin, directions),
                         ray_flags=mi.RayFlags.Minimal, coherent=True)
        valid = si.is_valid()
        shape = dr.reinterpret_array(mi.UInt, si.shape)
        mesh = dr.reinterpret_array(mi.MeshPtr, shape)
        normal = mesh.face_normal(si.prim_index, active=valid)
        vertex = dr.select(valid, si.p, origin+directions)
        tx_delta, rx_delta = vertex-tx, vertex-rx
        tx_length, rx_length = dr.norm(tx_delta), dr.norm(rx_delta)
        valid &= (tx_length > MIN_SEGMENT_LENGTH) & (rx_length > MIN_SEGMENT_LENGTH)
        tx_direction = tx_delta*dr.rcp(dr.maximum(tx_length, MIN_SEGMENT_LENGTH))
        rx_direction = rx_delta*dr.rcp(dr.maximum(rx_length, MIN_SEGMENT_LENGTH))
        # Diffuse reflection keeps the outgoing wave on the incident side.
        valid &= dr.dot(normal, tx_direction)*dr.dot(normal, rx_direction) > 0
        normal *= dr.sign(dr.dot(normal, -tx_direction))
        shadow = spawn_ray_to(vertex, dr.select(from_tx, rx, tx), normal)
        valid &= ~kwargs["mi_scene"].ray_test(shadow, active=valid)
        tx_cosine = dr.abs(dr.dot(normal, tx_direction))
        rx_cosine = dr.abs(dr.dot(normal, rx_direction))
        p_tx = tx_proposal.pdf(tx_rot.T@tx_direction)
        p_rx = rx_proposal.pdf(rx_rot.T@rx_direction)
        # Convert each endpoint's solid-angle PDF to area density on the hit
        # triangle, then use the complete stratified-mixture density (MIS).
        area_pdf = (tx_count/samples*p_tx*tx_cosine/dr.square(tx_length)
                    + rx_count/samples*p_rx*rx_cosine/dr.square(rx_length))
        # Sionna starts with 4*pi/N and divides it by PathsBuffer.probs.
        # This correction yields incident dOmega = cos(theta_tx)/(N*q_A*r_tx²).
        correction = 4*dr.pi*area_pdf*dr.square(tx_length)/dr.maximum(tx_cosine, 1e-20)
        valid &= dr.isfinite(correction) & (correction > 0)
        row = base.buffer_size+lane
        dr.scatter(paths._src_indices, source, row)
        dr.scatter(paths._tgt_indices, target, row)
        dr.scatter(paths._valid, valid, row)
        dr.scatter(paths.shapes.array, shape, row)
        dr.scatter(paths.primitives.array, si.prim_index, row)
        dr.scatter(paths.interaction_types.array, mi.UInt(InteractionType.DIFFUSE), row)
        dr.scatter(paths.probs.array, dr.select(valid, correction, mi.Float(1)), row)
        for axis in ("x", "y", "z"):
            dr.scatter(getattr(paths, "_vertices_"+axis).array, getattr(vertex, axis), row)
            dr.scatter(getattr(paths, "_k_tx_"+axis), getattr(tx_direction, axis), row)
            # k_rx points from RX toward the scatterer (opposite propagation),
            # matching Sionna's endpoint Doppler and array-phase conventions.
            dr.scatter(getattr(paths, "_k_rx_"+axis), getattr(rx_direction, axis), row)
        # Invalid diffuse samples must not enter the specular image method.
        # Temporarily bypass it; the complete visibility mask restores them.
        dr.scatter(self.visibility, valid, row)
        dr.scatter(paths._valid, mi.Bool(True), row)
        paths.advance_paths_counter(count)
        self.last_sampling = {"samples_per_link": samples, "diffuse_launches": width,
                              "tx_launches": pairs*tx_count, "rx_launches": pairs*rx_count,
                              "uniform_fraction": self.uniform_fraction, "sampling_cache_hit": hit}
        self.last_timings = {"proposal_table_prepare_ms": proposal_ms,
                             "host_numpy_sampling_ms": sampling_ms}
        return paths


class FirstOrderScatteringPathSolver:
    """LoS/specular paths plus importance-sampled first-order diffuse paths.

    ``samples_per_src`` now means sample ATTEMPTS per independent TX/RX link,
    half from each endpoint. Occlusion, ray misses, zero material scattering or
    antenna nulls may yield fewer retained paths; counts do not prove fidelity.
    Uses Sionna's diffuse ray-tube model, with density-corrected sampling. It
    does not introduce an independently calibrated roughness/speckle law.
    """
    def __init__(self, *, candidate_limit=2_000_000, uniform_fraction=.1, cache_sampling=True, opaque_poses=True):
        import sionna.rt as rt
        if rt.__version__ != "2.2.0":
            raise RuntimeError("Scattering adapter requires Sionna RT 2.2.0 private API")
        if not np.isfinite(uniform_fraction) or not 0 < uniform_fraction <= 1:
            raise ValueError("uniform_fraction must be in (0,1] to preserve all-direction support")
        if isinstance(candidate_limit, bool) or not isinstance(candidate_limit, int) or candidate_limit < 1:
            raise ValueError("candidate_limit must be a positive integer")
        self.opaque_poses = opaque_poses
        self._solver = rt.PathSolver(deterministic=True)
        self._candidates = _ScatteringCandidates(candidate_limit, uniform_fraction, cache_sampling)
        self._solver._candidate_generator = self._candidates
        self._solver._image_method = _VisibleImageMethod(self._solver._image_method, self._candidates)

    @property
    def sampling(self):
        return dict(self._candidates.last_sampling)

    @property
    def stage_timings(self):
        """Wall timings of table preparation and strictly host NumPy draws.

        Table preparation includes backend work/export; the remaining solve
        is mixed host/device work. These timings do not synchronize each ray
        or field stage and must not be interpreted as GPU kernel timings.
        """
        return dict(self._candidates.last_timings)

    def specular_plane_count(self, scene):
        """Prepare/reuse the geometry cache and report its exact plane count.

        Useful for budgeting all specular candidates on a triangulated DEM.
        Radio poses and material properties are not cached by this operation.
        """
        self._candidates._planes(scene.mi_scene)
        return self._candidates.plane_count

    def __call__(self, scene, **kwargs):
        import mitsuba as mi
        if self.opaque_poses and mi.variant().startswith('cuda'):
            import drjit as dr
            for device in [*scene.transmitters.values(), *scene.receivers.values()]:
                # Current values remain unchanged and are never cached. Only
                # compiler constant propagation is disabled for moving poses.
                dr.make_opaque(device.position, device.velocity, device.orientation)
        kwargs.setdefault("max_depth", 1)
        kwargs.setdefault("refraction", False)
        kwargs.setdefault("diffuse_reflection", kwargs["max_depth"] == 1)
        kwargs.setdefault("samples_per_src", 1028)
        self._candidates.scene = scene
        self._candidates.synthetic_array = kwargs.get("synthetic_array", True)
        return self._solver(scene, **kwargs)
