#!/usr/bin/env bash
# Mount only /capture, /arrays.json, /tracking-deps, /wheel and /output.
# No checkout, emitter truth, source waveform, GPU or network is needed.
set -euo pipefail
/opt/airsim-rf/.venv/bin/python -m venv /tmp/independent-tracker
task_python=/tmp/independent-tracker/bin/python
"$task_python" -m pip install --no-deps --ignore-installed --no-index /wheel/airsim_rf-0.2.0-py3-none-any.whl
"$task_python" - <<'PY'
from pathlib import Path
Path('/tmp/independent-tracker/lib/python3.12/site-packages/qualified-dependencies.pth').write_text(
    "import site; site.addsitedir('/opt/airsim-rf/.venv/lib/python3.12/site-packages')\n")
PY
cd /tmp
"$task_python" - <<'PY'
from pathlib import Path
import airsim_rf
assert '/tmp/independent-tracker/' in airsim_rf.__file__, airsim_rf.__file__
assert not Path('/truth.json').exists()
assert not Path('/scenario.json').exists()
print('Independent installed consumer:',airsim_rf.__file__)
PY
"$task_python" -m airsim_rf.cli track /capture --arrays /arrays.json --output /output/estimates.json
if [[ "${RF_RUN_TRACK_DEMO:-0}" == 1 ]]; then
  "$task_python" -m airsim_rf.cli track-demo --backend cpu --windows 32 --output /output/installed-demo
fi
