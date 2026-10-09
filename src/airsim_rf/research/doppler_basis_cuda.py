"""CuPy/CUDA all-path Doppler-basis filtering, independent of Dr.Jit/OptiX.

Research scope: equal clocks. FP64/complex128, private link data, every path.
Host validation/packing and transfers are included in synchronized rendering.
Temporal coefficient construction, path projection, FFTs and sums run on GPU.
"""
from contextlib import contextmanager
from time import perf_counter

import numpy as np
from scipy.fft import next_fast_len

from .doppler_basis import DopplerBasisRenderer, doppler_degree
from ..sampled_waveform import SampledWaveform
from ..rendering import _epoch, _oscillator_cycles


def temporal_coefficients(xp, z, degree):
    """DCT-II via a mirrored complex FFT; no CPU Bessel calls on CUDA.

    2*(degree+1) Gauss nodes place DCT aliases beyond the retained tail.
    Rank is chosen at half the requested temporal tolerance; omitted terms
    plus coefficient aliasing are bounded by the full tolerance, in exact
    arithmetic. NumPy execution is an independent test of this same transform.
    """
    nodes = 2*(degree+1)
    theta = (xp.arange(nodes, dtype=xp.float64)+.5)*(np.pi/nodes)
    values = xp.exp(1j*z[..., None]*xp.cos(theta))
    mirrored = xp.concatenate((values, values[..., ::-1]), axis=-1)
    q = xp.arange(degree+1)
    coefficients = xp.fft.fft(mirrored, axis=-1)[..., :degree+1]
    coefficients *= xp.exp(-1j*np.pi*q/(2*nodes))/nodes
    coefficients[..., 0] *= .5
    return coefficients


_PROJECT = r'''
extern "C" __global__ void project(
    const int* starts, const double* interp, const double* coeff,
    double* kernels, int paths, int taps, int rank, int support,
    int min_lag, long long entries) {
    long long index = (long long)blockDim.x*blockIdx.x+threadIdx.x;
    if (index >= entries) return;
    int k = index % support;
    int q = (index/support) % rank;
    int job = index/((long long)support*rank);
    int lag = min_lag+k;
    const int* row = starts+(long long)job*paths;
    int lo=0, hi=paths;
    while (lo < hi) {
        int mid=(lo+hi)/2;
        if (row[mid] < lag-taps+1) lo=mid+1; else hi=mid;
    }
    int first=lo;
    lo=0; hi=paths;
    while (lo < hi) {
        int mid=(lo+hi)/2;
        if (row[mid] <= lag) lo=mid+1; else hi=mid;
    }
    double real=0., imag=0.;
    for (int p=first; p<lo; ++p) {
        double w=interp[((long long)job*paths+p)*taps+lag-row[p]];
        long long c=((long long)job*rank+q)*paths+p;
        real += w*coeff[2*c]; imag += w*coeff[2*c+1];
    }
    kernels[2*index]=real; kernels[2*index+1]=imag;
}
'''

# Each warp owns one lag and up to 32 basis coefficients. A weight is loaded
# once and broadcast; the transposed coefficient layout makes rank lanes
# contiguous. Every contributing path is retained in the original order.
_PROJECT_WARP = r'''
extern "C" __global__ void project_warp(
    const int* starts, const double* interp, const double* coeff,
    double* kernels, int paths, int taps, int rank, int support,
    int min_lag, long long entries, const double* factors, int fused) {
    long long thread = (long long)blockDim.x*blockIdx.x+threadIdx.x;
    long long warp = thread/32;
    int lane = thread%32, tiles = (rank+31)/32;
    long long jobs = entries/((long long)rank*support);
    if (warp >= jobs*support*tiles) return;
    int k = warp%support, q = ((warp/support)%tiles)*32+lane;
    int job = warp/((long long)support*tiles), lag = min_lag+k;
    const int* row = starts+(long long)job*paths;
    int first=0, last=0;
    if (lane==0) {
        int lo=0, hi=paths;
        while (lo<hi) { int mid=(lo+hi)/2;
            if (row[mid]<lag-taps+1) lo=mid+1; else hi=mid; }
        first=lo; lo=0; hi=paths;
        while (lo<hi) { int mid=(lo+hi)/2;
            if (row[mid]<=lag) lo=mid+1; else hi=mid; }
        last=lo;
    }
    first=__shfl_sync(0xffffffffu,first,0);
    last=__shfl_sync(0xffffffffu,last,0);
    double real=0., imag=0.;
    for (int p=first; p<last; ++p) {
        double w=lane==0 ? interp[((long long)job*paths+p)*taps+lag-row[p]] : 0.;
        w=__shfl_sync(0xffffffffu,w,0);
        if (q<rank) {
            long long c=((long long)job*paths+p)*rank+q;
            double cr=coeff[2*c], ci=coeff[2*c+1];
            if (fused) {
                long long f=(long long)job*paths+p;
                double fr=factors[2*f], fi=factors[2*f+1];
                double r=cr*fr-ci*fi;
                ci=cr*fi+ci*fr; cr=r;
            }
            real+=w*cr; imag+=w*ci;
        }
    }
    if (q<rank) {
        long long index=((long long)job*rank+q)*support+k;
        kernels[2*index]=real; kernels[2*index+1]=imag;
    }
}
'''

_RECONSTRUCT = r'''
extern "C" __global__ void reconstruct(
    const double* filtered, const double* offsets, const double* base_cycles,
    double* result, int rank, int fft_size, int first, int count,
    int start, double fs, long long entries) {
    long long index=(long long)blockDim.x*blockIdx.x+threadIdx.x;
    if (index >= entries) return;
    int job=index/count, n=index%count;
    double u=count > 1 ? 2.*n/(count-1)-1. : 0.;
    double previous=1., current=u, real=0., imag=0.;
    for (int q=0; q<rank; ++q) {
        double value;
        if (q==0) value=1.;
        else if (q==1) value=u;
        else { value=2.*u*current-previous; previous=current; current=value; }
        long long k=((long long)job*rank+q)*fft_size+first+n;
        real += value*filtered[2*k]; imag += value*filtered[2*k+1];
    }
    double phase=6.283185307179586476925286766559*
        fmod(base_cycles[job]+offsets[job]*(start+n)/fs,1.);
    double sine, cosine;
    sincos(phase,&sine,&cosine);
    result[2*index]=real*cosine-imag*sine;
    result[2*index+1]=real*sine+imag*cosine;
}
'''


class CudaDopplerBasisRenderer:
    def __init__(self, *, sample_rate_hz, max_delay_s, max_doppler_hz,
                 block_samples=2048, temporal_tolerance=1e-10, batch_links=8,
                 projection='gather', delay_map='double', fft_inplace=False,
                 reuse_buffers=False, fused_projection=False, adaptive_temporal=False):
        # Reuse parameter guards, but not CPU channel construction.
        self.config = DopplerBasisRenderer(sample_rate_hz=sample_rate_hz,
            max_delay_s=max_delay_s, max_doppler_hz=max_doppler_hz,
            block_samples=block_samples, temporal_tolerance=temporal_tolerance)
        if isinstance(batch_links, bool) or not isinstance(batch_links, int) or batch_links < 1:
            raise ValueError('Positive integer batch_links required')
        if projection not in ('gather', 'warp', 'dense'):
            raise ValueError('Projection must be gather, warp or dense')
        if delay_map not in ('double', 'single'):
            raise ValueError('Delay map must be double or single')
        self.delay_map, self.fft_inplace = delay_map, bool(fft_inplace)
        if self.fft_inplace:
            from cupyx.scipy import fft
            self.inplace_fft = fft
        try:
            import cupy as cp
            if cp.cuda.runtime.getDeviceCount() < 1:
                raise RuntimeError('No CUDA device')
            cp.cuda.Device().use()
        except Exception as exc:
            raise RuntimeError('CuPy CUDA unavailable; no CPU fallback') from exc
        if fused_projection and projection != 'warp':
            raise ValueError('Fused projection requires warp projection')
        if not isinstance(adaptive_temporal, bool):
            raise ValueError('adaptive_temporal must be boolean')
        self.adaptive_temporal = adaptive_temporal
        self.reuse_buffers = bool(reuse_buffers)
        self.fused_projection = bool(fused_projection)
        self._buffers, self._channels = {}, {}
        self.cp, self.batch_links = cp, batch_links
        self.projection = projection
        self.project = cp.RawKernel(_PROJECT_WARP if projection == 'warp' else _PROJECT,
                                   'project_warp' if projection == 'warp' else 'project',
                                   options=('--std=c++11',))
        self.reconstruct = cp.RawKernel(_RECONSTRUCT, 'reconstruct', options=('--std=c++11',))
        self.last_metrics = {}

    def clear_cache(self):
        """Release this renderer's retained buffers and prepared channel state."""
        self._buffers.clear()
        self._channels.clear()

    def _pack(self, jobs, sim_time_ns, num_samples, slot, revision, profile):
        packed_started = perf_counter()
        cfg, cp = self.config, self.cp
        half = jobs[0].waveform.interpolation_taps//2
        min_lag = -half
        max_lag = int(np.ceil(cfg.max_delay_s*cfg.fs))+half
        if max_lag-min_lag+1 > 1_000_000:
            raise ValueError('Declared delay support exceeds research resource limit')
        paths = max(len(job.coefficients) for job in jobs)
        count = len(jobs)
        # Small capacity buckets avoid reallocating as physical path counts
        # and 120 Hz integer sample windows vary. Padding is never a path.
        if self.reuse_buffers:
            paths = ((paths+31)//32)*32
        source_width = num_samples+max_lag-min_lag
        if self.reuse_buffers:
            source_width = ((source_width+255)//256)*256
        shapes = dict(a=((count, paths), np.complex128), d=((count, paths), np.float64),
                      fd=((count, paths), np.float64), valid=((count, paths), np.bool_),
                      source=((count, source_width), np.complex128),
                      offsets=((count,), np.float64), base_cycles=((count,), np.float64))
        buffered = self._buffers.get(slot) if self.reuse_buffers else None
        buffers_reused = buffered is not None and buffered['shapes'] == shapes
        if not buffers_reused:
            host = {}
            device = {}
            for key, (shape, dtype) in shapes.items():
                if self.reuse_buffers:
                    memory = cp.cuda.alloc_pinned_memory(int(np.prod(shape))*np.dtype(dtype).itemsize)
                    host[key] = np.ndarray(shape, dtype=dtype, buffer=memory)
                    device[key] = cp.empty(shape, dtype=dtype)
                else:
                    host[key] = np.empty(shape, dtype=dtype)
            buffered = dict(shapes=shapes, host=host, device=device)
            if self.reuse_buffers:
                self._buffers[slot] = buffered
        host, device = buffered['host'], buffered['device']
        for array in host.values():
            array.fill(0)
        a, d, fd, valid = (host[key] for key in ('a', 'd', 'fd', 'valid'))
        private_input, offsets, base_cycles = (host[key] for key in ('source', 'offsets', 'base_cycles'))
        actual_doppler_hz = 0.
        for j, job in enumerate(jobs):
            wave = job.waveform
            if wave.sample_rate_hz != cfg.fs or job.time_scale != 1.:
                raise ValueError('CUDA research backend requires equal sample clocks')
            arrays = [np.asarray(job.coefficients), np.asarray(job.delays_s), np.asarray(job.doppler_hz)]
            if arrays[0].ndim != 1 or any(v.shape != arrays[0].shape for v in arrays):
                raise ValueError('Expected path arrays [paths]')
            if not all(np.isfinite(v).all() for v in arrays):
                raise ValueError('All supplied paths must be finite')
            if np.any(arrays[1] < 0) or np.any(arrays[1] > cfg.max_delay_s) or np.any(abs(arrays[2]) > cfg.max_doppler_hz):
                raise ValueError('Path outside declared delay/Doppler range')
            if self.adaptive_temporal and arrays[2].size:
                # Bound all supplied physical paths, including zero-gain paths.
                # Declared limits above still validate the complete input range.
                actual_doppler_hz = max(actual_doppler_hz, float(np.max(np.abs(arrays[2]))))
            if not np.isfinite([job.amplitude_scale, job.frequency_offset_hz, job.phase_offset_rad]).all():
                raise ValueError('Finite amplitude and oscillator parameters required')
            position = (int(sim_time_ns)-int(wave.reference_time_ns))*cfg.fs*1e-9
            anchor = int(round(position))
            if abs(position-anchor) > 1e-7:
                raise ValueError('Output start must align with source sample grid')
            lo, hi = anchor-max_lag, anchor+num_samples-min_lag
            if wave.boundary == 'error' and (lo < 0 or hi > wave.samples.size):
                raise ValueError('Insufficient private source history/lookahead')
            clipped_lo, clipped_hi = max(0, lo), min(wave.samples.size, hi)
            if clipped_hi > clipped_lo:
                private_input[j, clipped_lo-lo:clipped_hi-lo] = wave.samples[clipped_lo:clipped_hi]
            n = len(arrays[0])
            a[j, :n] = arrays[0]*job.amplitude_scale*np.exp(1j*job.phase_offset_rad)
            d[j, :n], fd[j, :n], valid[j, :n] = arrays[1], arrays[2], True
            offsets[j] = job.frequency_offset_hz
            base_cycles[j] = _oscillator_cycles(job.frequency_offset_hz, sim_time_ns)
        channel_keys = ('a', 'd', 'fd', 'valid', 'offsets')
        cached = self._channels.get(slot)
        channel_reused = revision is not None and cached is not None and cached['revision'] == revision
        if channel_reused:
            if any(not np.array_equal(host[key], cached['host'][key]) for key in channel_keys):
                raise ValueError('Channel data changed without a new channel_revision')
        else:
            self._channels.pop(slot, None)
            if revision is not None:
                cached = dict(revision=revision,
                              host={key: host[key].copy() for key in channel_keys})
                self._channels[slot] = cached
        prepared_ms = (perf_counter()-packed_started)*1000
        upload_start, upload_end = (cp.cuda.Event(), cp.cuda.Event()) if profile else (None, None)
        submission_started = perf_counter()
        if profile:
            upload_start.record()
        uploaded_bytes = 0
        uploaded_keys = []
        for key, array in host.items():
            if channel_reused and key in channel_keys:
                continue
            uploaded_bytes += array.nbytes
            uploaded_keys.append(key)
            if self.reuse_buffers:
                device[key].set(array, stream=cp.cuda.get_current_stream())
            else:
                device[key] = cp.asarray(array)
        if profile:
            upload_end.record()
        self._pack_stats.append(dict(cpu_prepare_ms=prepared_ms,
            upload_submission_ms=(perf_counter()-submission_started)*1000,
            uploaded_bytes=uploaded_bytes, uploaded_keys=uploaded_keys, buffers_reused=buffers_reused,
            channel_reused=channel_reused))
        if profile:
            self._upload_events.append((upload_start, upload_end))
        data = dict(device, count=count, paths=paths, half=half, min_lag=min_lag, max_lag=max_lag,
                    temporal_bound_hz=actual_doppler_hz if self.adaptive_temporal else cfg.max_doppler_hz,
                    channel_reused=channel_reused, channel_cache=cached if revision is not None else None)
        if channel_reused:
            data.update(cached['device'])
        return data

    def render(self, jobs, *, num_samples, sim_time_ns=0, channel_epoch_ns=None,
               sum_output=False, profile=False, channel_revision=None, workspace_id=None):
        if isinstance(num_samples, bool) or not isinstance(num_samples, int) or num_samples < 1:
            raise ValueError('Positive integer num_samples required')
        if not isinstance(sum_output, bool) or not isinstance(profile, bool):
            raise ValueError('Boolean sum_output/profile required')
        _epoch(sim_time_ns)
        channel_epoch_ns = sim_time_ns if channel_epoch_ns is None else channel_epoch_ns
        _epoch(channel_epoch_ns)
        if channel_revision is not None:
            if not self.reuse_buffers:
                raise ValueError('Channel reuse requires reuse_buffers')
            hash(channel_revision)
        hash(workspace_id)
        cfg, cp = self.config, self.cp
        started = perf_counter()
        self._pack_stats, self._upload_events = [], []
        jobs = list(jobs)
        groups = {}
        for index, job in enumerate(jobs):
            if not isinstance(job.waveform, SampledWaveform):
                raise TypeError('CUDA research backend requires sampled I/Q')
            groups.setdefault(job.waveform.interpolation_taps, []).append((index, job))
        events, blocks = [], []
        peak_pool_used = 0

        @contextmanager
        def stage(name):
            nonlocal peak_pool_used
            if not profile:
                yield
                return
            start, end = cp.cuda.Event(), cp.cuda.Event()
            cp.cuda.nvtx.RangePush(name)
            start.record()
            try:
                yield
            finally:
                end.record()
                cp.cuda.nvtx.RangePop()
                events.append((name, start, end))
                peak_pool_used = max(peak_pool_used, cp.get_default_memory_pool().used_bytes())

        output = cp.zeros(num_samples if sum_output else (len(jobs), num_samples), cp.complex128)
        for members in groups.values():
            for begin in range(0, len(members), self.batch_links):
                batch = members[begin:begin+self.batch_links]
                if max(len(job.coefficients) for _, job in batch) == 0:
                    continue
                with stage('basis.host_pack_and_upload'):
                    data = self._pack([job for _, job in batch], sim_time_ns, num_samples,
                                      (workspace_id, batch[0][1].waveform.interpolation_taps, begin), channel_revision, profile)
                count, paths, half = data['count'], data['paths'], data['half']
                support = data['max_lag']-data['min_lag']+1
                if not data['channel_reused']:
                    with stage('basis.delay_map'):
                        if self.delay_map == 'double':
                            order = cp.argsort(data['d'], axis=1)
                            for key in ('a', 'd', 'fd', 'valid'):
                                data[key] = cp.take_along_axis(data[key], order, axis=1)
                        starts = cp.ceil(data['d']*cfg.fs).astype(cp.int32)-half
                        starts = cp.where(data['valid'], starts, np.iinfo(np.int32).max).astype(cp.int32)
                        # Sort invalid lanes after real paths, including zero-delay paths.
                        if self.delay_map == 'double' or self.projection != 'dense':
                            order = cp.argsort(starts, axis=1)
                            for key in ('a', 'd', 'fd', 'valid'):
                                data[key] = cp.take_along_axis(data[key], order, axis=1)
                            starts = cp.take_along_axis(starts, order, axis=1)
                        lag = starts[..., None]+cp.arange(2*half)
                        distance = lag-data['d'][..., None]*cfg.fs
                        interp = cp.sinc(distance)*cp.sinc(distance/half)
                        norm = interp.sum(axis=-1, keepdims=True)
                        interp = cp.where(data['valid'][..., None], interp/cp.where(norm == 0, 1., norm), 0.)
                        gains = data['a']*cp.exp(-2j*np.pi*data['offsets'][:, None]*data['d'])
                        base_cycles = data['base_cycles']
                        if self.projection == 'dense':
                            # A private interpolation matrix per link; no path or
                            # waveform sharing. Construct fresh on every capture.
                            dense = cp.zeros((count, paths, support), cp.float64)
                            indices = cp.where(data['valid'][..., None], lag-data['min_lag'], 0)
                            dense[cp.arange(count)[:, None, None],
                                  cp.arange(paths)[None, :, None], indices] = interp
                    if data['channel_cache'] is not None:
                        data['channel_cache']['device'] = {key: data[key] for key in ('a', 'd', 'fd', 'valid', 'offsets')}
                        data['channel_cache'].update(starts=starts, interp=interp, gains=gains, temporal={})
                        if self.projection == 'dense':
                            data['channel_cache']['dense'] = dense
                else:
                    cached = data['channel_cache']
                    starts, interp, gains = (cached[key] for key in ('starts', 'interp', 'gains'))
                    if self.projection == 'dense':
                        dense = cached['dense']
                base_cycles = data['base_cycles']
                cache = data['channel_cache']['temporal'] if data['channel_cache'] is not None else {}
                degree_cache = {}
                for start in range(0, num_samples, cfg.block_samples):
                    n = min(cfg.block_samples, num_samples-start)
                    duration = (n-1)/cfg.fs
                    if n not in degree_cache:
                        degree_cache[n] = doppler_degree(data['temporal_bound_hz'], duration, cfg.temporal_tolerance/2)
                    degree, tail = degree_cache[n]
                    rank = degree+1
                    with stage('basis.temporal_coefficients'):
                        if n not in cache:
                            temporal = temporal_coefficients(cp, np.pi*data['fd']*duration, degree)
                            cache[n] = cp.ascontiguousarray(temporal if self.fused_projection else temporal.transpose(0, 2, 1))
                        centre = (start+(n-1)/2)/cfg.fs
                        phase = cp.remainder(data['fd']*((int(sim_time_ns)-int(channel_epoch_ns))*1e-9), 1.)+data['fd']*centre
                        factors = cp.ascontiguousarray(gains*cp.exp(2j*np.pi*cp.remainder(phase, 1.)))
                        coeff = cache[n] if self.fused_projection else cp.ascontiguousarray(cache[n]*factors[:, None, :])
                    with stage('basis.path_projection'):
                        kernels = cp.empty((count, rank, support), cp.complex128)
                        entries = kernels.size
                        if self.projection == 'dense':
                            kernels.real[:] = cp.matmul(cp.ascontiguousarray(coeff.real), dense)
                            kernels.imag[:] = cp.matmul(cp.ascontiguousarray(coeff.imag), dense)
                        else:
                            if self.projection == 'warp':
                                if not self.fused_projection:
                                    coeff = cp.ascontiguousarray(coeff.transpose(0, 2, 1))
                                warps = count*support*((rank+31)//32)
                                grid = ((warps+3)//4,)
                            else:
                                grid = ((entries+127)//128,)
                            kernel_args = (starts, interp, coeff, kernels,
                                np.int32(paths), np.int32(2*half), np.int32(rank), np.int32(support),
                                np.int32(data['min_lag']), np.int64(entries))
                            if self.projection == 'warp':
                                kernel_args += (factors, np.int32(self.fused_projection))
                            if profile:
                                project_begin, project_end = cp.cuda.Event(), cp.cuda.Event()
                                project_begin.record()
                            self.project(grid, (128,), kernel_args)
                            if profile:
                                project_end.record()
                                events.append(('basis.projection_call', project_begin, project_end))
                    with stage('basis.private_fft_filters'):
                        source = data['source'][:, start:start+n+support-1]
                        size = next_fast_len(source.shape[1])
                        private_fft = cp.fft.fft(source, size, axis=-1)
                        if self.fft_inplace:
                            # Only disposable filter buffers may be overwritten.
                            # Source windows overlap and must remain intact.
                            transformed = self.inplace_fft.fft(kernels, size, axis=-1, overwrite_x=True)
                            transformed *= private_fft[:, None, :]
                            filtered = self.inplace_fft.ifft(transformed, axis=-1, overwrite_x=True)
                        else:
                            filtered = cp.fft.ifft(cp.fft.fft(kernels, size, axis=-1)*private_fft[:, None, :], axis=-1)
                    with stage('basis.reconstruction_and_sum'):
                        # One kernel evolves the basis in registers, combines
                        # filters and applies the oscillator. No rank-many
                        # Python launches or rank-by-sample basis allocation.
                        rendered = cp.empty((count, n), cp.complex128)
                        self.reconstruct(((rendered.size+127)//128,), (128,),
                            (filtered, data['offsets'], base_cycles, rendered,
                             np.int32(rank), np.int32(size), np.int32(support-1),
                             np.int32(n), np.int32(start), np.float64(cfg.fs), np.int64(rendered.size)))
                        if sum_output:
                            output[start:start+n] += rendered.sum(axis=0)
                        else:
                            indices = cp.asarray([index for index, _ in batch])
                            output[indices, start:start+n] = rendered
                    blocks.append(dict(jobs=count, samples=n, degree=degree, temporal_tail_bound=tail,
                                       coefficient_aliasing_included=True, delay_coefficients=support,
                                       temporal_bound_hz=data['temporal_bound_hz']))
        with stage('basis.final_output_export'):
            result = cp.asnumpy(output)
        cp.cuda.get_current_stream().synchronize()
        for stats, (begin, end) in zip(self._pack_stats, self._upload_events):
            stats['upload_cuda_span_ms'] = float(cp.cuda.get_elapsed_time(begin, end))
        event_ms = [{ 'name': name, 'cuda_ms': float(cp.cuda.get_elapsed_time(a, b)) } for name, a, b in events]
        self.last_metrics = dict(total_ms=(perf_counter()-started)*1000, backend='cuda_cupy',
            projection=self.projection, delay_map=self.delay_map, fft_inplace=self.fft_inplace,
            reuse_buffers=self.reuse_buffers, fused_projection=self.fused_projection, adaptive_temporal=self.adaptive_temporal,
            packing=self._pack_stats,
            projection_calls=[v for v in event_ms if v['name'] == 'basis.projection_call'],
            valid_paths=sum(len(job.coefficients) for job in jobs), blocks=blocks, sum_output=sum_output,
            events=[v for v in event_ms if v['name'] != 'basis.projection_call'],
            cuda_event_span_ms=sum(v['cuda_ms'] for v in event_ms if v['name'] != 'basis.projection_call') if profile else None,
            pool_used_bytes=cp.get_default_memory_pool().used_bytes(),
            pool_reserved_bytes=cp.get_default_memory_pool().total_bytes(),
            max_checkpoint_pool_used_bytes=peak_pool_used if profile else None,
            pool_measurement_note='Allocator snapshots include persistent plans/cache; not process-wide peak VRAM',
            profile=profile, no_cpu_fallback=True, precision='complex128/float64')
        return result
