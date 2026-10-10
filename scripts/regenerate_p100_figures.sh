#!/usr/bin/env bash
# Use the explicit P100 image; regenerate the documented workloads without tuning.
set -euo pipefail
figure_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$figure_repo_root"
figure_image="${RF_P100_GPU_IMAGE:-airsim-rf:p100-modern-gpu}"
figure_stage="recordings/p100-documentation-figures"
mkdir -p "$figure_stage" docs/figures
figure_run=(docker run --rm --gpus "device=${RF_PROFILE_GPU:-0}" --network none
  --user "$(id -u):$(id -g)" --tmpfs /.drjit:rw,mode=1777
  -v "$figure_repo_root:/work/repo" -w /work/repo
  --entrypoint /opt/airsim-rf/.venv/bin/python
  -e PYTHONPATH=/work/repo/src -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics
  -e MPLCONFIGDIR=/tmp/matplotlib -e CUPY_CACHE_DIR=/tmp/cupy-cache
  -e CUDA_CACHE_PATH=/tmp/cuda-cache "$figure_image" scripts/basis_launch.py)
"${figure_run[@]}" scripts/generate_demo_terrain.py
"${figure_run[@]}" benchmarks/generate_rf_waterfalls.py --backend cuda --pascal-compat --output-dir "$figure_stage/waterfalls"
"${figure_run[@]}" benchmarks/generate_terrain_signature.py --backend cuda --pascal-compat --output-dir "$figure_stage/terrain"
"${figure_run[@]}" examples/pluto_esm_drones.py --backend cuda --pascal-compat --output-dir "$figure_stage/pluto"
# Publish source data; older demonstration color maps stay local.
# The sensing generator below produces the current waterfalls and line plots.
python3 - "$figure_stage" <<'PY'
from pathlib import Path
import shutil
import sys
for path in Path(sys.argv[1]).glob('*/*'):
    if path.suffix in {'.npz', '.json'}:
        shutil.copy2(path, Path('docs/figures')/path.name)
PY

"${figure_run[@]}" benchmarks/generate_sensing_figures.py --backend cuda
"${figure_run[@]}" benchmarks/check_sensing_visibility.py --backend cuda
"${figure_run[@]}" benchmarks/generate_sensing_scenarios.py
