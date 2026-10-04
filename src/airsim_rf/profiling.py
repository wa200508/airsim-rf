"""Opt-in NVTX/host ranges; normal RF execution does not collect profiles."""
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from time import perf_counter

_ACTIVE = ContextVar('rf_profiler', default=None)
_NOOP = nullcontext()


def profile_range(name):
    profiler = _ACTIVE.get()
    return _NOOP if profiler is None else profiler.range(name)


class CaptureProfiler:
    """Collect inclusive host durations and separate Dr.Jit event metadata.

    No synchronization is inserted into individual ranges. GPU history must be
    collected after an externally synchronized capture; host durations and
    summed device event times are distinct, potentially overlapping measures.
    """
    def __init__(self):
        try:
            import nvtx
            self.nvtx = nvtx
        except ImportError:
            self.nvtx = None
        self.host_ranges = []

    @contextmanager
    def activate(self):
        token = _ACTIVE.set(self)
        try:
            yield self
        finally:
            _ACTIVE.reset(token)

    @contextmanager
    def range(self, name):
        if self.nvtx is not None:
            self.nvtx.push_range(name)
        start = perf_counter()
        try:
            yield
        finally:
            self.host_ranges.append({'name': name, 'inclusive_host_ms': 1000*(perf_counter()-start)})
            if self.nvtx is not None:
                self.nvtx.pop_range()

    def take_host_ranges(self):
        result, self.host_ranges = self.host_ranges, []
        return result


def summarize_kernel_history(history):
    """JSON-safe metadata without potentially huge kernel IR strings."""
    records = []
    for event in history:
        row = {}
        for key in ('backend', 'type', 'hash', 'execution_time', 'operation_count',
                    'cache_hit', 'cache_disk', 'codegen_time', 'backend_time',
                    'uses_optix', 'recording_mode'):
            if key in event:
                value = event[key]
                row[key] = getattr(value, 'name', str(value)) if key in ('backend','type','recording_mode') else value if value is None or isinstance(value, (str, int, float, bool)) else str(value)
        records.append(row)
    cuda = [r for r in records if 'CUDA' in str(r.get('backend', '')).upper()]
    return {'records': records, 'cuda_operation_count': len(cuda),
            'cuda_event_time_sum_ms': sum(float(r.get('execution_time') or 0) for r in cuda),
            'optix_kernel_count': sum(bool(r.get('uses_optix')) for r in cuda),
            'note': 'Event-time sum includes recorded CUDA operations; not critical-path latency. IR omitted.'}
