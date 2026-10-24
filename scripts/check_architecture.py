#!/usr/bin/env python3
"""Audit every first-party Python module and enforce receiver/source import walls."""
import argparse
import ast
from collections import Counter
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE={'receiver','sdr','radar','fmcw','rendering','batched_rendering','sampled_waveform',
    'single_bounce','scattering','radar_scattering','bridge','sdr_bridge','terrain','geometry','geometry_sync','glb_geometry',
    'usd_geometry','scenario','scenario_definition','live','dashboard_producer','dashboard_scenario','dashboard_geometry',
    'dashboard_view','dashboard_radar','radar_control','dashboard_sync','source_recording','p100_compat','cuda_launch','preflight','example'}
EXTERNAL_SOURCE={'sionna','mitsuba','drjit','projectairsim'}
CONTRACT={'sample_stream','sample_recording','gnuradio_export','processing.results','ams.squall_rf_pb2','ams.squall_rf_pb2_grpc'}
ADAPTER={'iq_stream','recording','aoa_tracking'}


def role(module):
    name=module.removeprefix('airsim_rf.').removesuffix('.__init__')
    if name.startswith(('processing.','skills.')) or name in ('processing','skills'):return 'receiver application/math'
    if name in CONTRACT:return 'receiver contract/result I/O'
    if name in ADAPTER:return 'legacy source-format adapter'
    if name in SOURCE or name.startswith(('distributed.','research.')) or name in ('ams.backend','ams.dis'):return 'simulation/source'
    if name.startswith('evaluation.'):return 'held-out evaluation'
    if module=='airsim_rf' or name in ('ams','distributed','research','evaluation'):return 'package boundary'
    if name in ('observer_exports','dashboard','dashboard_recording','skill_display','dashboard_skill','music_plots','sensing_analysis','inspection','aoa_example','cli','profiling','runtime_metrics'):return 'observer/orchestration/compatibility'
    raise ValueError('Unclassified first-party module: '+module)


def imports(module,path):
    tree=ast.parse(path.read_text());result=set()
    package=module if path.name=='__init__.py' else module.rpartition('.')[0]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):result.update(alias.name for alias in node.names)
        elif isinstance(node,ast.ImportFrom):
            base=importlib.util.resolve_name('.'*node.level+(node.module or ''),package) if node.level else (node.module or '')
            result.add(base)
            # Include potential submodules, including `from .processing import music`.
            result.update(base+'.'+alias.name for alias in node.names if alias.name!='*')
        elif isinstance(node,ast.Call) and node.args and isinstance(node.args[0],ast.Constant):
            function=node.func
            if ((isinstance(function,ast.Attribute) and function.attr=='import_module') or
                (isinstance(function,ast.Name) and function.id=='__import__')):
                name=node.args[0].value
                if isinstance(name,str):
                    result.add(importlib.util.resolve_name(name,package) if name.startswith('.') else name)
    return result


def audit(root=ROOT):
    modules={}
    for path in sorted((root/'src/airsim_rf').rglob('*.py')):
        relative=path.relative_to(root/'src').with_suffix('')
        module='.'.join(relative.parts)
        if module.endswith('.__init__'):module=module[:-9]
        modules[module]=path
    failures=[];inventory=[]
    for module,path in modules.items():
        try:layer=role(module)
        except ValueError as error:failures.append(str(error));continue
        dependencies=imports(module,path)
        inventory.append({'file':str(path.relative_to(root)),'role':layer,'imports':sorted(dependencies)})
        if layer=='receiver application/math' or module in ('airsim_rf.sample_stream',):
            for dependency in dependencies:
                if dependency.split('.')[0] in EXTERNAL_SOURCE:
                    failures.append(f'{module} imports source backend {dependency}')
                if dependency.startswith('airsim_rf.'):
                    local_role=role(dependency) if dependency in modules else None
                    # Namespace packages and generated control contracts are neutral.
                    if local_role not in ('receiver application/math','receiver contract/result I/O','package boundary',None):
                        failures.append(f'{module} imports {local_role}: {dependency}')
        if layer=='simulation/source':
            for dependency in dependencies:
                if dependency in ('df_skill','radar_skill') or dependency.startswith(('df_skill.','radar_skill.')):
                    failures.append(f'{module} imports external receiver implementation {dependency}')
                if dependency.startswith(('airsim_rf.skills','airsim_rf.processing',
                    'airsim_rf.aoa_tracking','airsim_rf.music_plots','airsim_rf.evaluation','airsim_rf.dashboard_recording')):
                    if module in ('airsim_rf.radar','airsim_rf.fmcw') and dependency.startswith('airsim_rf.processing.radar'):
                        continue  # Legacy math exports are checked by scope below.
                    failures.append(f'{module} imports receiver/observer implementation {dependency}')
            # The only source -> observer/math dependencies retained are explicit
            # historical API shims, never generator code. Guard their exact scope.
            tree=ast.parse(path.read_text())
            permitted={}
            if module in ('airsim_rf.radar','airsim_rf.fmcw'):
                capture='RadarCapture' if module.endswith('.radar') else 'FMCWCapture'
                for node in tree.body:
                    if isinstance(node,ast.FunctionDef) and node.name=='__getattr__':
                        permitted.update({id(child):'airsim_rf.processing.radar' for child in ast.walk(node)})
                    if isinstance(node,ast.ClassDef) and node.name==capture:
                        for method in node.body:
                            if isinstance(method,ast.FunctionDef) and method.name=='save':
                                permitted.update({id(child):'airsim_rf.observer_exports' for child in ast.walk(method)})
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom):
                    package=module.rpartition('.')[0]
                    base=importlib.util.resolve_name('.'*node.level+(node.module or ''),package) if node.level else node.module
                    if base and base.startswith(('airsim_rf.processing.radar','airsim_rf.observer_exports')):
                        if permitted.get(id(node))!=base:
                            failures.append(f'{module} imports observer/math outside its legacy API shim: {base}')
                if isinstance(node,ast.Import):
                    for alias in node.names:
                        if alias.name.startswith('airsim_rf.observer_exports'):
                            failures.append(f'{module} imports observer implementation {alias.name}')
    # Repository-wide inventory: source-aware orchestration, evaluation and
    # qualification intentionally join planes. They are not deployed skills.
    support=[]
    for directory,layer in (('scripts','orchestration/qualification'),('examples','example orchestration or source-format adapter'),
        ('benchmarks','benchmark/evaluation'),('tests','test/qualification')):
        for path in sorted((root/directory).rglob('*.py')):
            ast.parse(path.read_text())
            support.append({'file':str(path.relative_to(root)),'role':layer})
    return {'support_files':support,'total_python_files':len(inventory)+len(support),'status':'failed' if failures else 'passed','modules':len(inventory),
        'roles':dict(Counter(row['role'] for row in inventory)),'failures':failures,'inventory':inventory}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
    report=audit()
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('inventory','support_files')},indent=2))
    if report['failures']:raise SystemExit(1)

if __name__=='__main__':main()
