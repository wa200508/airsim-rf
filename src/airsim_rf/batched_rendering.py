"""Bounded batches of independent path jobs with replayable LLVM/CUDA kernels.

Each job owns disjoint path data and an independent output. Packing jobs never
aliases transmitter data. All valid paths and narrowband Dopplers are retained.
"""
from dataclasses import dataclass
from numbers import Integral
from time import perf_counter

import numpy as np

from .rendering import LFMChirpWaveform, ToneWaveform, _epoch, _finite, _oscillator_cycles
from .sampled_waveform import SampledWaveform


def _runtime_array(kind, values):
    # LLVM can map NumPy buffers directly. Inconsistent external alignment
    # forces dr.freeze to retrace otherwise identical input configurations.
    # Each argument gets its own aligned copy; source data is never aliased.
    values = np.asarray(values).ravel()
    storage = np.empty(values.nbytes+255, dtype=np.uint8)
    offset = (-storage.ctypes.data) % 256
    aligned = np.ndarray(values.shape, dtype=values.dtype, buffer=storage, offset=offset)
    aligned[:] = values
    return kind(aligned)


@dataclass(frozen=True)
class PathRenderJob:
    coefficients: np.ndarray
    delays_s: np.ndarray
    doppler_hz: np.ndarray
    waveform: object
    amplitude_scale: float = 1.
    time_scale: float = 1.
    frequency_offset_hz: float = 0.
    phase_offset_rad: float = 0.


def _prepare(job, fs, count, sim_time_ns, channel_epoch_ns):
    if not isinstance(job.waveform, (ToneWaveform, LFMChirpWaveform, SampledWaveform)):
        raise TypeError("Batched renderer requires tone/LFM or sampled waveform descriptors")
    _finite(job.amplitude_scale, job.time_scale, job.frequency_offset_hz, job.phase_offset_rad)
    if job.time_scale <= 0:
        raise ValueError("Time scale must be positive")
    a = np.asarray(job.coefficients, dtype=np.complex128)
    tau = np.asarray(job.delays_s, dtype=np.float64)
    fd = np.asarray(job.doppler_hz, dtype=np.float64)
    if a.ndim != 1 or tau.shape != a.shape or fd.shape != a.shape:
        raise ValueError("Expected coefficients, delays and Dopplers [paths]")
    valid = np.isfinite(tau) & (tau >= 0)
    a, tau, fd = a[valid], tau[valid], fd[valid]
    if not np.isfinite(a).all() or not np.isfinite(fd).all():
        raise ValueError("Nonfinite coefficients or Dopplers")
    wave = job.waveform
    epoch_s = int(sim_time_ns)*1e-9
    local_s = (int(sim_time_ns)-int(wave.reference_time_ns))*1e-9
    u = local_s+epoch_s*(job.time_scale-1.)-tau*job.time_scale
    delta = (int(sim_time_ns)-int(channel_epoch_ns))*1e-9
    lo_phase = 2*np.pi*_oscillator_cycles(job.frequency_offset_hz, sim_time_ns)+job.phase_offset_rad
    if isinstance(wave, SampledWaveform):
        slope = 0.
        initial_phase = np.zeros(a.size)
        initial_frequency = np.zeros(a.size)
        first, last = np.zeros(a.size), np.full(a.size, count)
        position = u*wave.sample_rate_hz
        increment = job.time_scale*wave.sample_rate_hz/fs
        if wave.boundary == "error" and a.size:
            half = wave.interpolation_taps//2
            lower = np.floor(np.min(position))-half+1
            upper = np.floor(np.max(position)+(count-1)*increment)+half
            if lower < 0 or upper >= wave.samples.size:
                raise ValueError("Insufficient waveform history/lookahead")
    elif isinstance(wave, ToneWaveform):
        slope = 0.
        initial_phase = 2*np.pi*np.remainder(wave.frequency_hz*u, 1.)+wave.phase_rad
        initial_frequency = np.full(a.size, wave.frequency_hz*job.time_scale)
        first, last = np.zeros(a.size), np.full(a.size, count)
    else:
        slope = wave.bandwidth_hz/wave.pulse_width_s
        initial_phase = np.pi*slope*u*u-np.pi*wave.bandwidth_hz*u+wave.phase_rad
        initial_frequency = (slope*u-wave.bandwidth_hz/2)*job.time_scale
        first = np.ceil(-u*fs/job.time_scale-1e-9)
        last = np.ceil((wave.pulse_width_s-u)*fs/job.time_scale-1e-9)
    initial_phase += lo_phase-2*np.pi*job.frequency_offset_hz*tau+2*np.pi*np.remainder(fd*delta, 1.)
    phase = np.remainder(initial_phase, 2*np.pi)
    omega = 2*np.pi*(initial_frequency+job.frequency_offset_hz+fd)/fs
    curvature = 2*np.pi*slope*job.time_scale**2/fs**2
    # Initialize weighted phase once per path, then evolve that complex value.
    # This removes a second complex gain multiply at every analytic sample.
    z0 = a*job.amplitude_scale*np.exp(1j*phase)
    step = np.exp(1j*(omega+.5*curvature))
    return dict(z0=z0, omega=omega, step=step, curvature=curvature,
                first=first, last=last, paths=a.size,
                position=position if isinstance(wave, SampledWaveform) else np.zeros(a.size),
                increment=increment if isinstance(wave, SampledWaveform) else 0.,
                source=wave.samples if isinstance(wave, SampledWaveform) else None,
                taps=wave.interpolation_taps if isinstance(wave, SampledWaveform) else 0,
                curved=isinstance(wave, LFMChirpWaveform))


class BatchedPathRenderer:
    """Persistent executor; channels/clock parameters are runtime inputs.

    Valid paths are padded to whole path tiles, never truncated. ``max_lanes``
    bounds the per-batch recurrence width (not total backend allocation bytes).
    Outputs are either private per-job waveforms or their coherent sum. No
    source-buffer sharing is used. FP64 is retained throughout.
    """
    def __init__(self, *, backend="llvm", path_tile=128, sample_tile=32,
                 max_lanes=1_000_000, replay=True, reduction="auto"):
        import drjit as dr
        from drjit import cuda, llvm
        if backend not in ("llvm", "cuda"):
            raise ValueError("backend must be llvm or cuda")
        for value in (path_tile, sample_tile, max_lanes):
            if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
                raise ValueError("Tile sizes and lane budget must be positive integers")
        if not isinstance(replay, bool):
            raise ValueError("replay must be boolean")
        if reduction not in ('auto', 'local', 'expand'):
            raise ValueError("reduction must be auto, local or expand")
        if backend == 'cuda' and reduction == 'expand':
            raise ValueError("expand reduction is LLVM-only; use auto or local for CUDA")
        kind = dr.JitBackend.CUDA if backend == "cuda" else dr.JitBackend.LLVM
        if not dr.has_backend(kind):
            raise RuntimeError(f"Requested {backend} backend unavailable; no CPU fallback")
        self.types = cuda if backend == "cuda" else llvm
        self.backend, self.path_tile, self.sample_tile = backend, path_tile, sample_tile
        self.max_lanes, self.replay = max_lanes, replay
        self.reduction = reduction
        self._kernels = {}
        self.last_metrics = {}

    def _kernel(self, jobs, capacity, samples, sum_output, taps, curved):
        import drjit as dr
        resolved = self.reduction
        if resolved == 'auto':
            if self.backend == 'llvm' and jobs*samples <= dr.expand_threshold():
                resolved = 'expand'
            else:
                resolved = 'local' if dr.flag(dr.JitFlag.ScatterReduceLocal) else 'direct'
        key = (jobs, capacity, samples, sum_output, taps, curved, resolved, self.path_tile, self.sample_tile)
        if key in self._kernels:
            return self._kernels[key]
        Float, UInt, Int = self.types.Float64, self.types.UInt, self.types.Int
        path_tile, sample_tile = self.path_tile, self.sample_tile
        time_tiles = (samples+sample_tile-1)//sample_tile
        reduce_mode = {'local': dr.ReduceMode.Local, 'expand': dr.ReduceMode.Expand,
                       'direct': dr.ReduceMode.Direct}[resolved]

        def execute(zr0, zi0, omega, stepr0, stepi0, first, last, valid,
                    curvature, rotr, roti, timer, timei,
                    positions, increments, source_r, source_i, offsets, lengths, half_taps,
                    tap_cosines, tap_sines, interp_step_r, interp_step_i,
                    interp_wrap_r, interp_wrap_i):
            out_r, out_i = dr.zeros(Float, jobs*samples), dr.zeros(Float, jobs*samples)
            lane = dr.arange(UInt, jobs*path_tile*time_tiles)
            path = lane % path_tile
            time_tile = (lane//path_tile) % time_tiles
            job = lane//(path_tile*time_tiles)
            base = time_tile*sample_tile
            b = Float(base)
            cr = dr.gather(Float, curvature, job) if curved else Float(0)
            if curved:
                rr, ri = dr.gather(Float, rotr, job), dr.gather(Float, roti, job)
                tr = dr.gather(Float, timer, job*time_tiles+time_tile)
                ti = dr.gather(Float, timei, job*time_tiles+time_tile)
            if taps:
                increment = dr.gather(Float, increments, job)
                source_offset = dr.gather(UInt, offsets, job)
                source_length = dr.gather(UInt, lengths, job)
                half = dr.gather(Float, half_taps, job)
                sampled = half > 0
                isr = dr.gather(Float, interp_step_r, job)
                isi = dr.gather(Float, interp_step_i, job)
                iwr = dr.gather(Float, interp_wrap_r, job)
                iwi = dr.gather(Float, interp_wrap_i, job)
            for begin in range(0, capacity, path_tile):
                index = job*capacity+begin+path
                w = dr.gather(Float, omega, index)
                p_r, p_i = dr.gather(Float, zr0, index), dr.gather(Float, zi0, index)
                ds0, dc0 = dr.gather(Float, stepi0, index), dr.gather(Float, stepr0, index)
                lo, hi = dr.gather(Float, first, index), dr.gather(Float, last, index)
                good = dr.gather(UInt, valid, index) != 0
                if taps:
                    position = dr.gather(Float, positions, index)
                    coordinate0 = position+b*increment
                    fraction0 = coordinate0-dr.floor(coordinate0)
                    sh, ch = dr.sincos(dr.pi*fraction0/dr.maximum(half, 1.))
                else:
                    sh, ch = Float(0), Float(1)
                sine, cosine = dr.sincos(w*b+.5*cr*b*b)
                z_r, z_i = p_r*cosine-p_i*sine, p_r*sine+p_i*cosine
                dc, ds = (dc0*tr-ds0*ti, ds0*tr+dc0*ti) if curved else (dc0, ds0)

                def body(k, zr, zi, dc, ds, sh, ch, real, imag):
                    n = base+k
                    active = good & (n < samples) & (Float(n) >= lo) & (Float(n) < hi)
                    value_r, value_i = zr, zi
                    if taps:
                        # Far outside an explicitly finite transmission all
                        # interpolation fetches are zero. Clamp coordinates
                        # before conversion to signed indices to avoid overflow.
                        raw_coordinate = position+Float(n)*increment
                        coordinate = dr.clip(raw_coordinate,
                                             -float(taps), Float(source_length)+taps)
                        anchor = Int(dr.floor(coordinate))
                        fraction = raw_coordinate-dr.floor(raw_coordinate)
                        xr, xi, norm = dr.zeros(Float, 1), dr.zeros(Float, 1), dr.zeros(Float, 1)
                        for offset in range(-taps//2+1, taps//2+1):
                            source_index = anchor+offset
                            d = fraction-offset
                            # Different jobs can select different interpolation
                            # supports. Every tap is input interpolation, never a
                            # merged/pruned propagation path or average Doppler.
                            supported = sampled & (offset > -half) & (offset <= half)
                            table_index = job*taps+(offset+taps//2-1)
                            tap_cos = dr.gather(Float, tap_cosines, table_index)
                            tap_sin = dr.gather(Float, tap_sines, table_index)
                            # The common half*sin(pi*fraction)/pi**2 factor
                            # cancels in normalized Lanczos coefficients. One
                            # division per tap and no per-tap trig are needed.
                            grid_point = (fraction == 0) | (fraction == 1)
                            denominator = dr.select(d == 0, 1., d*d)
                            raw_weight = ((-1.)**offset)*(sh*tap_cos-ch*tap_sin)/denominator
                            weight = dr.select(supported, dr.select(grid_point, Float(d == 0), raw_weight), 0.)
                            norm += weight
                            fetch = active & supported & (source_index >= 0) & (source_index < Int(source_length))
                            address = source_offset+UInt(source_index)
                            xr += weight*dr.gather(Float, source_r, address, fetch)
                            xi += weight*dr.gather(Float, source_i, address, fetch)
                        inv = dr.rcp(dr.select(sampled, norm, 1.))
                        xr, xi = xr*inv, xi*inv
                        value_r = dr.select(sampled, zr*xr-zi*xi, zr)
                        value_i = dr.select(sampled, zr*xi+zi*xr, zi)
                        # Advance interpolation phase with clock ratio. A
                        # fractional-coordinate wrap subtracts pi/half. This
                        # works for arbitrary positive ratios, not just unity.
                        next_coordinate = position+Float(n+1)*increment
                        wraps = dr.floor(next_coordinate)-dr.floor(raw_coordinate)-dr.floor(increment) > .5
                        ns, nc = sh*isr+ch*isi, ch*isr-sh*isi
                        sh = dr.select(wraps, ns*iwr+nc*iwi, ns)
                        ch = dr.select(wraps, nc*iwr-ns*iwi, nc)
                    # Job-major private outputs avoid false sharing of cache
                    # lines between simultaneously rendered transmitters.
                    dest = job*samples+n
                    dr.scatter_reduce(dr.ReduceOp.Add, real, value_r, dest, active, mode=reduce_mode)
                    dr.scatter_reduce(dr.ReduceOp.Add, imag, value_i, dest, active, mode=reduce_mode)
                    next_dc, next_ds = (dc*rr-ds*ri, ds*rr+dc*ri) if curved else (dc, ds)
                    return k+1, zr*dc-zi*ds, zi*dc+zr*ds, next_dc, next_ds, sh, ch, real, imag

                _, _, _, _, _, _, _, out_r, out_i = dr.while_loop(
                    (UInt(0), z_r, z_i, dc, ds, sh, ch, out_r, out_i),
                    lambda k, *state: k < sample_tile, body, mode="symbolic",
                    label="rf_batched_path_recurrence")
                dr.eval(out_r, out_i)
            if sum_output:
                # Sum independent jobs on-device without materializing a
                # transposed jobs-by-samples array or per-path contributions.
                n = dr.arange(UInt, samples)
                private_r, private_i = out_r, out_i
                def add_job(j, real, imag):
                    index = j*samples+n
                    return j+1, real+dr.gather(Float, private_r, index), imag+dr.gather(Float, private_i, index)
                _, out_r, out_i = dr.while_loop(
                    (UInt(0), dr.zeros(Float, samples), dr.zeros(Float, samples)),
                    lambda j, *state: j < jobs, add_job, mode="symbolic",
                    label="rf_batched_job_sum")
            dr.eval(out_r, out_i)
            return out_r, out_i

        # Runtime arrays are opaque: changing geometry, Doppler, gains or clock
        # values never freezes physical state into the recorded execution.
        kernel = dr.freeze(execute, limit=4, auto_opaque=False, enabled=self.replay)
        if len(self._kernels) >= 16:
            self._kernels.pop(next(iter(self._kernels)))
        self._kernels[key] = kernel
        return kernel

    def render(self, jobs, *, sample_rate_hz, num_samples, sim_time_ns=0,
               channel_epoch_ns=None, sum_output=False):
        import drjit as dr
        start = perf_counter()
        _finite(sample_rate_hz)
        if sample_rate_hz <= 0 or isinstance(num_samples, bool) or not isinstance(num_samples, Integral) or num_samples < 1:
            raise ValueError("Positive sample rate and integer sample count required")
        if not isinstance(sum_output, bool):
            raise ValueError("sum_output must be boolean")
        _epoch(sim_time_ns)
        channel_epoch_ns = sim_time_ns if channel_epoch_ns is None else channel_epoch_ns
        _epoch(channel_epoch_ns)
        jobs = list(jobs)
        prepared = [_prepare(job, sample_rate_hz, num_samples, sim_time_ns, channel_epoch_ns) for job in jobs]
        time_tiles = (num_samples+self.sample_tile-1)//self.sample_tile
        per_job_lanes = self.path_tile*time_tiles
        max_jobs = self.max_lanes//per_job_lanes
        if max_jobs < 1:
            raise ValueError("Lane budget too small for one job; increase max_lanes or sample_tile")
        result = np.zeros(num_samples if sum_output else (len(jobs), num_samples), dtype=np.complex128)
        preparation_ms = (perf_counter()-start)*1000
        Float, UInt = self.types.Float64, self.types.UInt
        execution_ms = export_ms = 0.
        groups = []
        recordings_added = 0
        device_r = device_i = None
        for begin in range(0, len(prepared), max_jobs):
            group = prepared[begin:begin+max_jobs]
            paths = max(row['paths'] for row in group)
            if paths == 0:
                continue
            count = len(group)
            capacity = ((paths+self.path_tile-1)//self.path_tile)*self.path_tile
            if count*capacity >= 2**32 or count*num_samples >= 2**32:
                raise ValueError("Batch exceeds 32-bit indexing; use a smaller lane budget")
            tick = perf_counter()
            shape = (count, capacity)
            zr, zi, omega, sr, si, lo, hi, positions = [np.zeros(shape) for _ in range(8)]
            valid = np.zeros(shape, dtype=np.uint32)
            curvature = np.array([row['curvature'] for row in group])
            for j, row in enumerate(group):
                end = row['paths']
                zr[j, :end], zi[j, :end] = row['z0'].real, row['z0'].imag
                omega[j, :end] = row['omega']
                sr[j, :end], si[j, :end] = row['step'].real, row['step'].imag
                lo[j, :end], hi[j, :end] = row['first'], row['last']
                valid[j, :end] = 1
                positions[j, :end] = row['position']
            rotation = np.exp(1j*curvature)
            time_rotation = np.exp(1j*curvature[:, None]*np.arange(time_tiles)*self.sample_tile)
            arguments = [_runtime_array(Float, x) for x in (zr, zi, omega, sr, si, lo, hi)]
            arguments += [_runtime_array(UInt, valid), _runtime_array(Float, curvature),
                          _runtime_array(Float, rotation.real), _runtime_array(Float, rotation.imag),
                          _runtime_array(Float, time_rotation.real), _runtime_array(Float, time_rotation.imag)]
            # Disjoint copies for every job, including jobs that happen to be
            # passed the same descriptor. No deduplication across transmitters
            # or receivers, and no TX-buffer/transform reuse is credited.
            sources = [row['source'] if row['source'] is not None else np.zeros(1, complex) for row in group]
            lengths = np.array([len(source) for source in sources], dtype=np.uint32)
            offsets = np.r_[0, np.cumsum(lengths[:-1], dtype=np.uint64)]
            if int(sum(int(v) for v in lengths)) >= 2**31:
                raise ValueError("Private input batch exceeds signed interpolation indexing")
            source = np.concatenate(sources)
            taps = max(row['taps'] for row in group)
            arguments += [_runtime_array(Float, positions),
                          _runtime_array(Float, np.array([row['increment'] for row in group])),
                          _runtime_array(Float, source.real), _runtime_array(Float, source.imag),
                          _runtime_array(UInt, offsets.astype(np.uint32)), _runtime_array(UInt, lengths),
                          _runtime_array(Float, np.array([row['taps']/2 for row in group]))]
            if taps:
                tap_offsets = np.arange(-taps//2+1, taps//2+1)
                half = np.array([max(row['taps']/2, 1.) for row in group])
                tap_rotation = np.exp(1j*np.pi*tap_offsets[None, :]/half[:, None])
            else:
                tap_rotation = np.zeros((count, 1), complex)
            arguments += [_runtime_array(Float, tap_rotation.real), _runtime_array(Float, tap_rotation.imag)]
            half = np.array([max(row['taps']/2, 1.) for row in group])
            increment = np.array([row['increment'] for row in group])
            interp_step = np.exp(1j*np.pi*(increment-np.floor(increment))/half)
            interp_wrap = np.exp(-1j*np.pi/half)
            arguments += [_runtime_array(Float, interp_step.real), _runtime_array(Float, interp_step.imag),
                          _runtime_array(Float, interp_wrap.real), _runtime_array(Float, interp_wrap.imag)]
            dr.make_opaque(*arguments)
            kernel = self._kernel(count, capacity, num_samples, sum_output, taps,
                                  any(row['curved'] for row in group))
            before_recordings = kernel.n_recordings
            real, imag = kernel(*arguments)
            recordings_added += kernel.n_recordings-before_recordings
            if sum_output:
                device_r = real if device_r is None else device_r+real
                device_i = imag if device_i is None else device_i+imag
                dr.eval(device_r, device_i)
            execution_ms += (perf_counter()-tick)*1000
            tick = perf_counter()
            if not sum_output:
                output = np.asarray(real)+1j*np.asarray(imag)
                result[begin:begin+count] = output.reshape(count, num_samples)
            export_ms += (perf_counter()-tick)*1000
            groups.append(dict(jobs=count, capacity_paths_per_job=capacity,
                               lanes=count*per_job_lanes,
                               reduction=('expand' if self.backend == 'llvm' and count*num_samples <= dr.expand_threshold()
                                          else 'local' if dr.flag(dr.JitFlag.ScatterReduceLocal) else 'direct')
                                         if self.reduction == 'auto' else self.reduction))
        if sum_output and device_r is not None:
            tick = perf_counter()
            result = np.asarray(device_r)+1j*np.asarray(device_i)
            export_ms += (perf_counter()-tick)*1000
        self.last_metrics = dict(preparation_ms=preparation_ms,
                                 schedule_pack_ms=execution_ms, export_wait_ms=export_ms,
                                 total_ms=(perf_counter()-start)*1000,
                                 retained_paths=sum(row['paths'] for row in prepared), groups=groups,
                                 recordings_added=recordings_added,
                                 reduction=self.reduction,
                                 replay=self.replay, sum_output=sum_output)
        return result
