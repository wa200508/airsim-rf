# Initial quick-run investigation

The original source `2a33cd2` passed real CuPy CUDA preflight but stalled in `dr.has_backend(LLVM)` during direct-reference initialization. The required test process was terminated after over seven minutes; the subsequent CPU benchmark also stalled and the collector was interrupted. There are no completed performance measurements in this bundle.

A bounded full-suite reproduction returned **6 passed, 1 failed** in 1.32 s. It exposed the split-capture/Unix-timestamp accuracy failure; its log is retained. A bounded CPU benchmark reproduction dumped its stack in `BatchedPathRenderer.__init__` during LLVM initialization. Early backend initialization passed, but merely moving array-type imports did not resolve the hang and that source change was reverted.

The final workaround disables only unsupported Dr.Jit CUDA initialization through `DRJIT_LIBCUDA_PATH` and provides a writable `DRJIT_CACHE_DIR`. CuPy CUDA remains enabled and independently checked. The original CPU benchmark then completed and passed its capture checks. This harness-only workaround was committed as `b4d48f5`; renderer algorithms, paths, samples and accuracy thresholds are unchanged.

See [full collection](../p100-basis-full-20261004/REPORT.md). Its numerical timestamp failure remains unresolved and its overall qualification fails.
