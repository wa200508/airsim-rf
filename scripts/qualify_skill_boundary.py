"""Compatibility command: qualify the separately maintained DF-Skill image."""
from pathlib import Path
import re
import subprocess

if __name__ == '__main__':
    pin=re.search(r'/([0-9a-f]{40})\.tar\.gz', (Path(__file__).resolve().parents[1]/'requirements-df-skill.txt').read_text())
    if pin is None:raise SystemExit('Missing immutable DF-Skill source pin')
    raise SystemExit(subprocess.call(['docker','run','--rm','--network','none','--entrypoint','python',
        'ghcr.io/wa200508/df-skill:sha-'+pin.group(1),'scripts/qualify_independence.py']))
