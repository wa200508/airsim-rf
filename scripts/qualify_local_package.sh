#!/usr/bin/env bash
# Run inside the existing qualification image, with the checkout at /work/repo
# and a writable evidence mount at /evidence. No GPU or simulator is accessed.
set -euo pipefail
task_python=/tmp/airsim-rf-clean/bin/python
/usr/local/bin/python -m venv /tmp/airsim-rf-clean
/usr/local/bin/python - <<'PY'
from pathlib import Path
import json, shutil, subprocess
pins=json.loads(Path('/work/repo/sources.json').read_text())
for key,source,destination in (
    ('sionna_rt','/opt/airsim-rf/.deps/sionna-rt','/tmp/clean-sionna'),
    ('projectairsim','/opt/airsim-rf/.deps/ProjectAirSim','/tmp/clean-client'),
):
    head=subprocess.check_output(['git','-c',f'safe.directory={source}','-C',source,'rev-parse','HEAD'],text=True).strip()
    if head!=pins[key]['commit']:
        raise RuntimeError(f'{key}: cached source differs from sources.json')
    dirty=subprocess.check_output(['git','-c',f'safe.directory={source}','-C',source,'status','--porcelain'],text=True).strip()
    if dirty:
        raise RuntimeError(f'{key}: cached source has local changes')
    tree=Path(source) if key=='sionna_rt' else Path(source)/'client/python/projectairsim'
    shutil.copytree(tree,destination,ignore=shutil.ignore_patterns('.git','*.egg-info','__pycache__'))
PY
"$task_python" -m pip install -r /work/repo/requirements-lock.txt \
  -r /work/repo/requirements-geometry.txt /tmp/clean-sionna /tmp/clean-client \
  /evidence/local-build/airsim_rf-0.2.0-py3-none-any.whl
"$task_python" -m pip check
cd /tmp
"$task_python" /work/repo/scripts/qualify_installed_package.py --output "${RF_PACKAGE_EVIDENCE_DIR:-/evidence/clean-install}"
"$task_python" -m pytest /work/repo/tests -q -rs -p no:cacheprovider > /evidence/full-standard-cpu-tests.log 2>&1
