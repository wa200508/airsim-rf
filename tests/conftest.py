"""Keep native renderer cleanup outside the next test's JIT capture."""
import gc

import pytest


@pytest.fixture(autouse=True)
def collect_at_test_boundary():
    # The combined suite with Dr.Jit 1.5.0 aborted during cyclic GC inside a
    # frozen-kernel capture after adding the optional consumer tests. Collecting
    # between tests avoids that observed interaction; the upstream cause has
    # not been established. Automatic GC stays enabled throughout each test.
    yield
    gc.collect()
