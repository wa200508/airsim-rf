#!/usr/bin/env bash
# Task-owned Blocks server must already be running. The wheel and evidence are
# mounted at /evidence. Dependencies come from the qualified P100 parent image.
set -euo pipefail
# Use the parent's actual virtualenv as the dependency source.
/opt/airsim-rf/.venv/bin/python -m venv --system-site-packages /tmp/airsim-rf-wheel-live
task_python=/tmp/airsim-rf-wheel-live/bin/python
"$task_python" -m pip install --ignore-installed --no-deps --no-index /evidence/local-build/*.whl
cd /tmp
"$task_python" - <<'PY'
from pathlib import Path
import sys
# venv normally exposes the base interpreter's system site rather than the
# source venv. Add only its dependencies, never the mounted checkout source.
path=Path('/tmp/airsim-rf-wheel-live/lib/python3.12/site-packages/qualified-dependencies.pth')
path.write_text("import site; site.addsitedir('/opt/airsim-rf/.venv/lib/python3.12/site-packages')\n")
PY
"$task_python" - <<'PY'
from pathlib import Path
import airsim_rf
assert '/tmp/airsim-rf-wheel-live/lib/python3.12/site-packages/' in airsim_rf.__file__, airsim_rf.__file__
print('Installed module:',airsim_rf.__file__)
PY
"$task_python" -m airsim_rf.cli example --output /evidence/live-inputs
"$task_python" -m airsim_rf.cli preflight --config /evidence/live-inputs/radios.json \
  --output /evidence/live-capture --gpu --pascal-compat > /evidence/live-preflight.json
"$task_python" -m airsim_rf.cuda_launch -m airsim_rf.live --pascal-compat \
  --config /evidence/live-inputs/radios.json --output /evidence/live-capture \
  --updates 10 --advance-ns 10000000
"$task_python" -m airsim_rf.cli inspect /evidence/live-capture > /evidence/live-inspection.json
"$task_python" -m airsim_rf.cli process /evidence/live-capture > /evidence/live-processing.json
