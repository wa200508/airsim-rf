"""Host Docker regression: repeated preparation, interruption, cleanup and recovery.

Uses real Docker resources and CPU stand-ins, without qualifying a GPU mission.
The image must contain the current dashboard_scenario implementation and SDK.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('dashboard_lifecycle',ROOT/'src/airsim_rf/dashboard.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def qualify(run,image,probe_image):
    args=SimpleNamespace(repo=ROOT,run_dir=run,port=8765,ready_timeout=120,
        rf_image=image,sim_image=probe_image,skill_image=probe_image)
    obj=module.Dashboard(args);obj.acquire_run();errors=[];worker=None
    try:
        obj.configure_docker();obj.cleanup_stale()
        obj.prepare()
        manifest=(run/'bundle/manifest.json').read_bytes()
        recording=run/'preserved.iq';recording.write_bytes(b'keep me')
        # A repeat launch used to fail at the exporter's exist_ok=False mkdir.
        obj.prepare()
        assert (run/'bundle/manifest.json').read_bytes()==manifest
        obj.write_command(stop=False)
        obj.network_created=True
        obj.command(['docker','network','create',*obj.labels(),obj.network])
        for part in ('sim','skill','rf'):
            # RF exits on the same stop file as the real producer. Other roles
            # exercise the supervisor's Docker stop/remove path.
            script=('import json,time; from pathlib import Path\n'
                    'while not json.loads(Path("/run/command.json").read_text()).get("stop"): time.sleep(.1)'
                    if part=='rf' else 'import time; time.sleep(120)')
            obj.launch(part,['docker','run','--rm','--name',obj.names[part],*obj.labels(),
                '--network',obj.network,'--user',obj.uid(),'-v',f'{run}:/run',
                '--entrypoint','python',probe_image,'-c',script])
        def probe():
            try:
                with obj.operation_lock:
                    obj.one_shot(['--network','none','--user',obj.uid(),'-v',f'{run}:/run',
                        '--entrypoint','python',probe_image,'-c',
                        'import time; from pathlib import Path; Path("/run/probe-started").touch(); time.sleep(120)'])
            except RuntimeError as error:errors.append(str(error))
        worker=threading.Thread(target=probe);worker.start()
        deadline=time.monotonic()+60
        while not (run/'probe-started').exists():
            if time.monotonic()>deadline:raise RuntimeError('One-shot probe did not start')
            time.sleep(.1)
        selector='label=org.airsim-rf.dashboard.session='+obj.session
        while len(obj.command(['docker','ps','-q','--filter',selector]).stdout.split())!=4:
            if time.monotonic()>deadline:raise RuntimeError('All three services and the active probe did not become running')
            time.sleep(.1)
    finally:
        obj.close()
        if worker:worker.join(timeout=5)
    selector='label=org.airsim-rf.dashboard.run='+obj.run_key
    def resources(kind):
        command=(['docker','ps','-aq'] if kind=='containers' else ['docker','network','ls','-q'])
        return subprocess.check_output([*command,'--filter',selector],text=True).split()
    assert not resources('containers'),'Owned containers survived shutdown'
    assert not resources('networks'),'Owned network survived shutdown'
    assert errors==['Dashboard is shutting down']
    assert worker is not None and not worker.is_alive()
    assert recording.read_bytes()==b'keep me'
    reopened=module.Dashboard(args);reopened.acquire_run()
    try:
        reopened.configure_docker()
        # Simulate resources left behind by SIGKILL, which cannot be trapped.
        stale_network=reopened.network+'-stale'
        reopened.command(['docker','network','create',*reopened.labels(),stale_network])
        reopened.command(['docker','run','-d','--rm',*reopened.labels(),'--network',stale_network,
            '--entrypoint','python',probe_image,'-c','import time; time.sleep(120)'])
        reopened.cleanup_stale()
        assert not resources('containers') and not resources('networks')
        reopened.prepare()
        assert (run/'bundle/manifest.json').read_bytes()==manifest
        assert recording.read_bytes()==b'keep me'
    finally:
        # Also recover the injected stale resources if a preceding check failed.
        try:reopened.cleanup_stale()
        finally:reopened.close()
    return {'status':'passed','checks':{
        'repeated_preparation_same_directory':True,
        'active_probe_cancelled_and_reaped':True,
        'all_three_service_containers_removed':True,
        'owned_network_removed':True,
        'reopen_and_prepare_same_directory':True,
        'label_scoped_stale_resource_recovery':True,
        'recorded_data_preserved':True},
        'rootless':obj.rootless,
        'scope':'Actual Docker lifecycle and scene export; CPU service stand-ins, no CUDA or full RF mission'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='airsim-rf:test')
    parser.add_argument('--probe-image',help='Small Python image for vfs-backed test environments; defaults to --image')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='airsim-rf-lifecycle-') as temporary:
        report=qualify(Path(temporary),args.image,args.probe_image or args.image)
    print(json.dumps(report,indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
