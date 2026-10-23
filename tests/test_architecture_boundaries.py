"""Regression guards for real-receiver skills versus source/environment code."""
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def checker():
    spec=importlib.util.spec_from_file_location('architecture_check',ROOT/'scripts/check_architecture.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_all_first_party_package_modules_have_an_allowed_role():
    report=checker().audit()
    assert not report['failures'],report['failures']
    assert report['modules']>=60 and report['total_python_files']>200


def test_guard_catches_receiver_importing_simulator_and_source_importing_algorithm(tmp_path):
    root=tmp_path/'src/airsim_rf';(root/'skills').mkdir(parents=True)
    (root/'skills/music.py').write_text('import sionna.rt\n')
    (root/'dashboard_producer.py').write_text('from .skills.music import MusicSkill\n')
    report=checker().audit(tmp_path)
    assert len(report['failures'])>=2
    assert any('source backend' in failure for failure in report['failures'])
    assert any('receiver/observer' in failure for failure in report['failures'])


def test_guard_checks_module_aliases_and_literal_dynamic_imports(tmp_path):
    root=tmp_path/'src/airsim_rf';(root/'processing').mkdir(parents=True)
    (root/'processing/music.py').write_text('import importlib\nimportlib.import_module("airsim_rf.receiver")\n')
    (root/'receiver.py').write_text('from .processing import music\n')
    report=checker().audit(tmp_path)
    assert any('airsim_rf.receiver' in failure for failure in report['failures'])
    assert any('airsim_rf.processing.music' in failure for failure in report['failures'])


def test_legacy_analysis_exports_cannot_be_imported_by_generator_code(tmp_path):
    root=tmp_path/'src/airsim_rf';root.mkdir(parents=True)
    path=root/'radar.py'
    path.write_text('from .processing.radar import range_compress\n')
    assert any('outside its legacy API shim' in failure for failure in checker().audit(tmp_path)['failures'])
    path.write_text('def __getattr__(name):\n from .processing.radar import range_compress\n return range_compress\n')
    assert checker().audit(tmp_path)['status']=='passed'


def test_importing_receiver_app_does_not_load_or_attempt_source_dependencies():
    program='''
import importlib.abc,sys
class DenySource(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'sionna','mitsuba','drjit','cupy','projectairsim'} or fullname in {'airsim_rf.receiver','airsim_rf.sdr','airsim_rf.recording','airsim_rf.dashboard_recording','airsim_rf.aoa_tracking'}:
   raise RuntimeError('Receiver imported forbidden source module: '+fullname)
sys.meta_path.insert(0,DenySource())
from airsim_rf.skills.music import MusicSkill
from airsim_rf.processing.tracking import track_windows
assert 'airsim_rf.receiver' not in sys.modules
'''
    result=subprocess.run([sys.executable,'-c',program],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
