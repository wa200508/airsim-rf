"""Commit a report bundle to a new results branch; optionally push normally."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def git(*args, capture=False):
    result=subprocess.run(['git','-C',str(ROOT),*args],check=True,text=True,
        stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle',type=Path)
    p.add_argument('--push',action='store_true')
    args=p.parse_args();bundle=args.bundle.resolve()
    try: bundle.relative_to(ROOT/'results/profiling')
    except ValueError: p.error('Bundle must be inside this checkout at results/profiling/<run-id>')
    if bundle.parent!=ROOT/'results/profiling': p.error('Select one run directory')
    manifest=json.loads((bundle/'manifest.json').read_text())
    if manifest['run_id']!=bundle.name: p.error('Manifest run-id does not match directory')
    if git('status','--porcelain','--untracked-files=no',capture=True):
        p.error('Commit or resolve existing tracked/staged changes before publishing results')
    # Rebuild report/checksums from this bundle using the standard-library tool.
    subprocess.run([sys.executable,ROOT/'scripts/aggregate_gpu_profile.py',bundle],check=True)
    selected=[bundle/name for name in ('REPORT.md','manifest.json','environment.json','installed_packages.json',
        'profile_summary.json','telemetry_summary.json','checksums.json') if (bundle/name).is_file()]
    for directory,pattern in (('metrics','*.json'),('profiles','*.json'),('logs','*.log')):
        selected.extend(sorted((bundle/directory).rglob(pattern)))
    if manifest.get('scope')=='rf_pipeline_end_to_end_collection':
        selected.extend(sorted((bundle/'profiles').rglob('REPORT.md')))
    if any(path.is_symlink() for path in selected): p.error('Symlink artifacts are not supported')
    if any(path.stat().st_size>20*1024*1024 for path in selected):
        p.error('A git artifact exceeds 20 MiB; keep large profiler output in raw/')
    branch='profiling/results/'+manifest['run_id']
    subprocess.run(['git','check-ref-format','--branch',branch],check=True,capture_output=True)
    git('switch','-c',branch)
    git('add','--',*[str(path.relative_to(ROOT)) for path in selected])
    git('commit','-m',f"Record RF profiling results: {manifest['run_id']}")
    print(f'Results branch: {branch}',flush=True)
    if args.push:
        git('push','-u','origin',branch)
    else:
        print(f'Publish with: git push -u origin {branch}')


if __name__=='__main__': main()
