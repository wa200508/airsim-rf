"""Explicit Pascal compatibility for Mitsuba 3.8 / Dr.Jit 1.3.1.

Keep path counters on CUDA. No changes to rays, fields or propagation budgets.
"""
_COUNTER = r'''
extern "C" __global__ void counter(unsigned int* target, const unsigned int* index,
    const bool* active, unsigned int* result, int n, int mask_n) {
    int i=blockDim.x*blockIdx.x+threadIdx.x;
    if(i<n) result[i]=active[mask_n==1 ? 0 : i] ? atomicAdd(target+index[i],1u) : 0u;
}
'''


def enable_pascal_compat(*, stable_shapes=True):
    import cupy as cp
    import drjit as dr
    import mitsuba as mi
    if dr.__version__ != '1.3.1' or mi.__version__ != '3.8.0':
        raise RuntimeError('Pascal compatibility requires Dr.Jit 1.3.1 / Mitsuba 3.8.0')
    if not mi.variant().startswith('cuda'):
        raise RuntimeError('Pascal compatibility requires CUDA propagation')
    if getattr(dr.scatter_inc, '_p100_compatible', False):
        return
    # Sionna 2.2 tests this optional backend in its native sampler.
    # A sentinel preserves the false branch on CUDA/LLVM in older Dr.Jit.
    if not hasattr(dr.JitBackend, 'Metal'):
        dr.JitBackend.Metal = None
    if stable_shapes:
        _bucket_path_storage()
    native = dr.scatter_inc
    kernel = cp.RawKernel(_COUNTER, 'counter')

    def scatter_inc(target, index, active=True):
        if not type(target).__module__.startswith('drjit.cuda'):
            return native(target, index, active)
        index, active = mi.UInt(index), mi.Bool(active)
        # Materialize device state and preserve the side effect on target.
        dr.make_opaque(target, index, active)
        dr.sync_thread()
        dst, ix, mask = (cp.from_dlpack(v) for v in (target, index, active))
        if dst.dtype != cp.uint32 or ix.dtype != cp.uint32:
            raise TypeError('Pascal path counter requires uint32 storage')
        result = cp.empty(ix.shape, cp.uint32)
        if result.size:
            kernel(((result.size+127)//128,), (128,),
                (dst, ix, mask, result, result.size, mask.size))
        cp.cuda.get_current_stream().synchronize()
        return mi.UInt(result)

    scatter_inc._p100_compatible = True
    dr.scatter_inc = scatter_inc
    dr.set_flag(dr.JitFlag.ScatterReduceLocal, False)
    # Native Sionna reference samplers call counters inside their loops.
    # Evaluated loops keep arithmetic/traversal on GPU while permitting the
    # zero-copy CuPy counter operation between iterations.
    dr.set_flag(dr.JitFlag.SymbolicLoops, False)


def _bucket_path_storage():
    """Pad storage to a power of two; never add or remove physical paths."""
    import inspect
    import textwrap
    import sionna.rt as rt
    from sionna.rt.path_solvers.paths import Paths
    if rt.__version__ != '2.2.0':
        raise RuntimeError('Path storage compatibility requires Sionna RT 2.2.0')
    original = Paths.__init__
    if getattr(original, '_p100_bucketed', False):
        return
    source = textwrap.dedent(inspect.getsource(original))
    needle = 'self._max_num_paths = dr.max(num_paths)[0]'
    if source.count(needle) != 1:
        raise RuntimeError('Unsupported Sionna path constructor layout')
    source = source.replace(needle, needle+'\n    self._max_num_paths = 1 << (int(self._max_num_paths)-1).bit_length()')
    namespace = {}
    exec(compile(source, inspect.getsourcefile(original), 'exec'), original.__globals__, namespace)
    replacement = namespace['__init__']
    replacement._p100_bucketed = True
    Paths.__init__ = replacement
