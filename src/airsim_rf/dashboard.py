"""Python localhost launcher and process supervisor for the primary RF use case."""
import argparse
from collections import deque
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import fcntl
import importlib.util
from hashlib import sha256
import json
import math
import os
import re
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import ProxyHandler,build_opener
from urllib.parse import urlsplit,parse_qs

# These HTTP calls only target our own published loopback service ports.
urlopen=build_opener(ProxyHandler({})).open
import webbrowser

# Load the stdlib-only recorder alongside this file, without importing the
# numerical package __init__. The standalone run script extracts both files.
_recording_spec=importlib.util.spec_from_file_location('dashboard_recording',Path(__file__).with_name('dashboard_recording.py'))
_recording=importlib.util.module_from_spec(_recording_spec);_recording_spec.loader.exec_module(_recording)


class DashboardShutdown(SystemExit):
    """Unwind startup or the HTTP loop through the same cleanup path."""


def select_display_frame(history,available_epochs,camera_time_ns,max_offset_ns):
    """Match display diagnostics to image simulation time, never wall time."""
    if camera_time_ns is None:return None
    available=set(available_epochs)
    candidates=[row for row in history if row.get('sim_time_ns') in available]
    if not candidates:return None
    selected=min(candidates,key=lambda row:abs(row['sim_time_ns']-camera_time_ns))
    return selected if abs(selected['sim_time_ns']-camera_time_ns)<=max_offset_ns else None


def select_display_pair(history,available_epochs,cameras,max_offset_ns,minimum_epoch=None):
    """Newest complete RF epoch with its closest retained camera; never rewind."""
    pairs=[]
    for camera in cameras:
        row=select_display_frame(history,available_epochs,camera.get('sim_time_ns'),max_offset_ns)
        if row is not None and (minimum_epoch is None or row['sim_time_ns']>=minimum_epoch):
            pairs.append((row,camera))
    return max(pairs,key=lambda pair:(pair[0]['sim_time_ns'],
        -abs(pair[1]['sim_time_ns']-pair[0]['sim_time_ns'])),default=None)


_definition_spec=importlib.util.spec_from_file_location('scenario_definition',Path(__file__).with_name('scenario_definition.py'))
_definition=importlib.util.module_from_spec(_definition_spec);_definition_spec.loader.exec_module(_definition)


class Dashboard:
    def __init__(self,args):
        self.args=args;self.root=args.repo.resolve();self.run=args.run_dir.resolve();self.run.mkdir(parents=True,exist_ok=True)
        self.scenario_path=getattr(args,'scenario',None) or _definition.default_directory()
        self.definition=None if getattr(args,'replay',False) else _definition.load(self.scenario_path)
        self.duration_override=None if getattr(args,'duration_from_scenario',False) else getattr(args,'duration',None)
        if self.definition is not None:
            if self.duration_override is None:args.duration=self.definition['mission']['duration_s']
            if not getattr(args,'skill_image',None):args.skill_image=self.definition['skill']['image']
        elif not getattr(args,'skill_image',None):args.skill_image='ghcr.io/wa200508/df-skill:sha-270bfacb6ac933f5c60599aab3edf39489978c45'
        self.token=secrets.token_urlsafe(24);self.lock=threading.Lock();self.events=deque(maxlen=40);self.busy=False;self.error=None
        self.processes={};self.last_skill={};self.ready=False;self.mission_started=False;self.image_tags={name:getattr(args,name) for name in ('sim_image','skill_image','rf_image')};self.names={part:f'airsim-rf-dashboard-{part}-{args.port}' for part in ('sim','rf','skill')}
        self.log('Preparing separate simulator, GPU RF and receiver skill containers.')
        self.rootless=False;self.gpu_options=[];self.network_created=False
        self.network='airsim-rf-dashboard-'+str(args.port)+'-'+secrets.token_hex(4)
        self.session=secrets.token_hex(8)
        self.run_key=sha256(str(self.run).encode()).hexdigest()
        self.names={part:name+'-'+self.session for part,name in self.names.items()}
        self.owned_names=set();self.shutdown_event=threading.Event()
        self.operation_lock=threading.RLock();self.run_lock=None;self.owns_run=False
        self.last_display=None
        self.recordings=_recording.RecordingStore(self.run/'replays')
        self.health_updated=0.;self.skill_health={}

    def acquire_run(self):
        self.run_lock=(self.run/'.dashboard.lock').open('a')
        try:fcntl.flock(self.run_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.run_lock.close();self.run_lock=None
            raise RuntimeError('Another dashboard launcher owns this run directory. '
                f'Open http://localhost:{self.args.port} or stop that launcher first.') from None
        self.owns_run=True

    def labels(self):
        return ['--label','org.airsim-rf.dashboard.session='+self.session,
                '--label','org.airsim-rf.dashboard.run='+self.run_key]

    def ensure_running(self):
        if self.shutdown_event.is_set():raise RuntimeError('Dashboard is shutting down')

    def log(self,message):self.events.append({'time':time.strftime('%H:%M:%S'),'message':str(message)})
    def command(self,args,check=True,live=False):
        self.ensure_running()
        deadline=time.monotonic()+self.args.ready_timeout
        with subprocess.Popen(args,cwd=self.root,stdout=None if live else subprocess.PIPE,
                              stderr=None if live else subprocess.PIPE,text=True) as process:
            try:
                while True:
                    self.ensure_running()
                    try:stdout,stderr=process.communicate(timeout=.2);break
                    except subprocess.TimeoutExpired:
                        if time.monotonic()>deadline:raise TimeoutError('Timed out: '+' '.join(args[:3]))
            except BaseException:
                process.kill();process.communicate();raise
        result=subprocess.CompletedProcess(args,process.returncode,stdout or '',stderr or '')
        if check and result.returncode:raise RuntimeError((result.stderr or result.stdout)[-2500:] or 'Command failed: '+' '.join(args[:3]))
        return result
    def one_shot(self,args,check=True):
        name='airsim-rf-dashboard-probe-'+self.session+'-'+secrets.token_hex(3)
        self.owned_names.add(name)
        return self.command(['docker','run','--rm','--name',name,*self.labels(),*args],check=check)
    def launch(self,part,args):
        self.ensure_running();self.owned_names.add(self.names[part])
        with (self.run/f'{part}.log').open('a') as log:
            process=subprocess.Popen(args,cwd=self.root,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        self.processes[part]=process;return process
    def read(self,name):
        try:return json.loads((self.run/name).read_text())
        except (OSError,ValueError):return {}
    def write_command(self,**value):
        path=self.run/'command.json';tmp=self.run/'command.tmp';tmp.write_text(json.dumps(value));tmp.replace(path)
    def wait_port(self,port,timeout=60,part=None):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.ensure_running()
            if part and self.processes[part].poll() is not None:
                raise RuntimeError(f'{part} exited before readiness; see {self.run}/{part}.log')
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.3):return
            except OSError:time.sleep(.25)
        raise RuntimeError(f'Process did not listen on localhost:{port}; check run logs')
    def configure_docker(self):
        options=json.loads(self.command(['docker','info','--format','{{json .SecurityOptions}}']).stdout) or []
        self.rootless=any(option in ('rootless','name=rootless') for option in options)
        # In a rootless user namespace UID 0 maps to the calling host user.
        # Passing that host UID instead would map to an unrelated subordinate UID.
        if not self.rootless and os.getuid()==0:os.chown(self.run,10001,10001)
        self.log('Using '+('rootless' if self.rootless else 'rootful')+' Docker with a private service network')
    def uid(self):
        if self.rootless:return '0:0'
        return f'{os.getuid()}:{os.getgid()}' if os.getuid() else '10001:10001'
    def prepare(self):
        self.definition=(_definition.load(self.run/'scenario-input') if getattr(self,'inputs_frozen',False) else
            _definition.snapshot(self.scenario_path,self.run/'scenario-input'))
        self.inputs_frozen=False
        if self.duration_override is None:self.args.duration=self.definition['mission']['duration_s']
        if not self.rootless and os.getuid()==0:
            for path in (self.run/'scenario-input',*(self.run/'scenario-input').rglob('*')):os.chown(path,10001,10001)
        script=('from airsim_rf.dashboard_scenario import prepare; '
            f'prepare("/run", scenario_dir="/run/scenario-input", duration_s={self.args.duration!r}, check_iq_space=True)')
        self.one_shot(['--network','none','--user',self.uid(),'-e','HOME=/tmp',
            '-v',f'{self.run}:/run','--entrypoint','python',self.args.rf_image,'-c',script])
    def check_workspace(self):
        marker=self.run/'.dashboard-access-check'
        try:
            marker.write_text('host-wrote')
            if not self.rootless and os.getuid()==0:os.chown(marker,10001,10001)
        except OSError as error:
            raise RuntimeError('The run directory is not writable by your login user; choose a fresh --run-dir. '+str(error)) from error
        script='from pathlib import Path; p=Path("/run/.dashboard-access-check"); assert p.read_text()=="host-wrote"; p.write_text("container-wrote")'
        try:
            result=self.one_shot(['--network','none','--user',self.uid(),
                '-v',f'{self.run}:/run','--entrypoint','python',self.args.rf_image,'-c',script],check=False)
            if result.returncode or marker.read_text()!='container-wrote':
                raise RuntimeError('Container cannot read/write the host run directory. '
                    'Use the Docker context owned by your login user; do not run the launcher with sudo. '
                    'Choose a fresh --run-dir if older files have wrong ownership. Details: '+result.stderr[-1500:])
        finally:
            marker.unlink(missing_ok=True)
    def check_gpu(self):
        mode=getattr(self.args,'gpu_mode','auto')
        device=getattr(self.args,'gpu_device','0')
        options={'cdi':['--device','nvidia.com/gpu='+device],'gpus':['--gpus','all' if device=='all' else 'device='+device]}
        candidates=([mode] if mode!='auto' else ['cdi','gpus'] if self.rootless else ['gpus','cdi'])
        failures=[]
        script='import cupy as cp; assert cp.cuda.runtime.getDeviceCount()>0; assert int(cp.arange(16).sum().get())==120; print("CUDA device and kernel passed")'
        for candidate in candidates:
            result=self.one_shot(['--network','none','--user',self.uid(),*options[candidate],
                '-e','HOME=/tmp','--entrypoint','python',self.args.rf_image,
                '-m','airsim_rf.cuda_launch','-c',script],check=False)
            if result.returncode==0:
                self.gpu_options=options[candidate];self.log('GPU passthrough checked using '+candidate);return
            failures.append(candidate+': '+(result.stderr or result.stdout)[-1800:])
        raise RuntimeError('GPU passthrough failed before service launch. Rootless Docker needs NVIDIA CDI '
            'or a rootless-configured NVIDIA runtime; see the README rootless section. No CPU fallback. '+ '\n'.join(failures))
    def pull_images(self):
        revisions=[]
        for name in ('sim_image','skill_image','rf_image'):
            image=self.image_tags[name]
            self.log('Pulling '+image)
            self.command(['docker','pull',image],live=True)
            metadata=json.loads(self.command(['docker','image','inspect',image]).stdout)[0]
            revision=metadata.get('Config',{}).get('Labels',{}).get('org.opencontainers.image.revision')
            revisions.append(revision)
            # The launched containers use the verified immutable local image ID.
            setattr(self.args,name,metadata['Id'])
        required=[revisions[0],revisions[2]]
        if self.definition is None or self.definition['skill']['revision_policy']=='matching':required.append(revisions[1])
        if len(set(required))!=1 or required[0] in (None,'unknown',''):
            raise RuntimeError('Dashboard image revisions differ or are unversioned; retry after publication completes')
        self.log('Verified simulation image revision '+revisions[0]+('; independent skill image' if len(required)==2 else '; matching skill image'))
    def cleanup_stale(self):
        # The run-directory flock establishes that no live launcher owns these
        # resources. Labels restrict recovery to this exact run directory.
        selector='label=org.airsim-rf.dashboard.run='+self.run_key
        ids=self.command(['docker','ps','-aq','--filter',selector]).stdout.split()
        if ids:self.command(['docker','rm','-f',*ids]);self.log('Removed containers from an interrupted launch')
        ids=self.command(['docker','network','ls','-q','--filter',selector]).stdout.split()
        if ids:self.command(['docker','network','rm',*ids]);self.log('Removed networks from an interrupted launch')
    def bootstrap(self):
        self.ready=False;self.mission_started=False;self.last_skill={};self.last_display=None
        self.health_updated=0.;self.skill_health={}
        # Re-read edited inputs before image selection or any service starts.
        self.definition=_definition.snapshot(self.scenario_path,self.run/'scenario-input')
        self.inputs_frozen=True
        if self.duration_override is None:self.args.duration=self.definition['mission']['duration_s']
        if not getattr(self.args,'skill_image_override',True):self.image_tags['skill_image']=self.definition['skill']['image']
        self.configure_docker()
        if self.owns_run:self.cleanup_stale()
        self.pull_images()
        self.check_workspace()
        self.check_gpu()
        # The host HTTP server already owns args.port, including when the UI's
        # Prepare services button starts a second mission.
        for port in (8989,8990,self.args.iq_port,self.args.skill_port,*([self.args.control_port] if self.definition['skill']['ports']['control'] is not None else [])):
            with socket.socket() as test:
                if test.connect_ex(('127.0.0.1',port))==0:raise RuntimeError(f'Port {port} already in use')
        for name in ('producer.json','camera.jpg','camera.json'):
            path=self.run/name
            if path.exists():path.replace(self.run/(name+'.previous'))
        self.prepare();self.write_command(start=False,paused=False,stop=False)
        self.recording_id=secrets.token_hex(8)
        scenario=self.read('scenario.json')
        recording=_recording.RecordingWriter(self.run/'replays',self.recording_id,scenario,self.args.duration,
            scenario.get('advance_ns',120_000_000),no_render=self.args.no_render)
        if (self.run/'scenario-input').exists():shutil.copytree(self.run/'scenario-input',recording.path/'definition')
        _recording.atomic_json(recording.path/'deployment.json',{'image_tags':self.image_tags,
            'image_ids':{name:getattr(self.args,name) for name in self.image_tags},'skill':self.definition['skill'],
            'effective_duration_s':self.args.duration,'no_render':self.args.no_render,
            'pascal_compat':self.args.pascal_compat,'gpu_options':self.gpu_options})
        if not self.rootless and os.getuid()==0:
            # A rootful launch runs services as UID 10001. Host-created journals
            # must be writable by that same user; rootless maps UID 0 to the host.
            for path in (recording.path,*recording.path.rglob('*')):os.chown(path,10001,10001)
        self.network_created=True
        self.command(['docker','network','create',*self.labels(),self.network])
        sim=['docker','run','--rm','--init','--name',self.names['sim'],*self.labels(),'--network',self.network,'--network-alias','projectairsim',
             '--user',('10001:10001' if self.rootless else self.uid()),'--shm-size','1g',
             '-p','127.0.0.1:8989:8989','-p','127.0.0.1:8990:8990',self.args.sim_image]
        if self.args.no_render:
            sim[sim.index(self.args.sim_image):sim.index(self.args.sim_image)]=['--entrypoint','/opt/blocks/Blocks/Binaries/Linux/Blocks-Linux-Shipping']
            sim+=['Blocks','-nullrhi','-nosound','-unattended']
        # Start the independent containers without serial readiness waits.
        self.launch('sim',sim)
        skill=self.definition['skill'];ports=skill['ports']
        control=['-p',f"127.0.0.1:{self.args.control_port}:{ports['control']}"] if ports['control'] is not None else []
        self.launch('skill',['docker','run','--rm','--init','--name',self.names['skill'],*self.labels(),'--network',self.network,'--network-alias','rf-skill','--user',self.uid(),
             '-p',f"127.0.0.1:{self.args.iq_port}:{ports['iq']}",'-p',f"127.0.0.1:{self.args.skill_port}:{ports['http']}",*control,
             '-e',f"RF_IQ_PORT={ports['iq']}",'-e',f"RF_HTTP_PORT={ports['http']}",
             '-e','RF_RECEIVER_CONFIG=/config/arrays.json','-e','RF_RESULTS_DIR=/results',
             *(['-e',f"RF_CONTROL_PORT={ports['control']}"] if ports['control'] is not None else []),
             '-v',f'{self.run}/receiver-config.json:/config/arrays.json:ro',
             *(['-v',f'{self.run}/radar-mode.json:/config/radar-mode.json:ro'] if skill['kind']=='radar' else []),
             '-v',f'{self.run}/replays/{self.recording_id}/results:/results',
             self.args.skill_image,*skill['command']])
        self.launch('rf',['docker','run','--rm','--init','--name',self.names['rf'],*self.labels(),*self.gpu_options,'--network',self.network,'--network-alias','rf-acquisition',
            '--user',self.uid(),'--tmpfs','/.drjit:rw,mode=1777','-e','HOME=/tmp',
            '-v',f'{self.run}:/run','--workdir','/run','--entrypoint','/opt/airsim-rf/.venv/bin/python',self.args.rf_image,
            '-m','airsim_rf.cuda_launch','-m','airsim_rf.dashboard_producer','--run-dir','/run',
            '--duration',str(self.args.duration),'--address','projectairsim','--iq-host','rf-skill',
            '--iq-port',str(ports['iq']),'--recording-id',self.recording_id,'--wait-for-mission',
            '--ready-timeout',str(self.args.ready_timeout),*(['--no-render'] if self.args.no_render else []),
            *(['--pascal-compat'] if self.args.pascal_compat else [])])
        self.wait_port(8989,self.args.ready_timeout,part='sim')
        self.wait_port(self.args.skill_port,self.args.ready_timeout,part='skill')
        deadline=time.monotonic()+self.args.ready_timeout
        while time.monotonic()<deadline:
            self.ensure_running()
            for part,process in self.processes.items():
                if process.poll() is not None:raise RuntimeError(f'{part} failed startup; see {self.run}/{part}.log')
            state=self.read('producer.json')
            if state.get('status')=='failed':raise RuntimeError(state.get('error','RF startup failed'))
            if state.get('status')=='ready':
                with urlopen(f'http://127.0.0.1:{self.args.skill_port}/health',timeout=2) as response:
                    if response.status==200 and json.load(response).get('complete_windows',0)>=1:
                        self.ready=True;self.log('READY: GPU checked, actual scene I/Q processed by skill, camera prepared; mission paused')
                        return
            time.sleep(.25)
        raise RuntimeError('Services did not become mission-ready; inspect simulator, RF and skill logs')
    def start(self):
        if not self.ready or self.mission_started or any(p.poll() is not None for p in self.processes.values()):
            raise ValueError('Prepare healthy containers before launching a mission')
        self.write_command(start=True,paused=False,stop=False);self.mission_started=True
        self.log('Starting mission in the already prepared containers')
    def stop(self):
        with self.operation_lock:self._stop()
    def cleanup_command(self,args):
        try:
            result=subprocess.run(args,cwd=self.root,capture_output=True,text=True,timeout=8)
            unexpected=[line for line in result.stderr.splitlines()
                if 'no such container' not in line.lower() and 'not found' not in line.lower()
                and 'already in progress' not in line.lower()]
            if result.returncode and unexpected:
                message='Cleanup needs attention: '+'\n'.join(unexpected)[-1500:]
                self.log(message);print(message,file=sys.stderr,flush=True)
            return result
        except (OSError,subprocess.TimeoutExpired) as error:
            message='Cleanup command failed: '+str(error)
            self.log(message);print(message,file=sys.stderr,flush=True);return None
    def _stop(self):
        self.ready=False;self.mission_started=False
        try:self.write_command(stop=True)
        except OSError as error:self.log('Could not write stop command: '+str(error))
        process=self.processes.get('rf')
        if process:
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:pass
        services=[self.names[part] for part in self.processes]
        if services:self.cleanup_command(['docker','stop','-t','5',*services])
        owned=sorted(self.owned_names|set(services))
        if owned:self.cleanup_command(['docker','rm','-f',*owned])
        for process in self.processes.values():
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
        if self.network_created:
            for _ in range(3):
                result=self.cleanup_command(['docker','network','rm',self.network])
                if result is not None and (result.returncode==0 or 'not found' in result.stderr):
                    self.network_created=False;break
                time.sleep(.25)
            if self.network_created:self.log('Could not remove task network yet: '+self.network)
        self.log('Stopped task-owned processes')
    def close(self):
        self.shutdown_event.set()
        try:
            if self.owns_run:self.stop()
        finally:
            if self.run_lock:self.run_lock.close();self.run_lock=None
            self.owns_run=False
    def select_scenario(self,identifier):
        choices={row['id']:row for row in _definition.catalog()}
        if identifier not in choices:raise ValueError('Unknown packaged scenario')
        with self.lock:
            if self.busy or self.mission_started:raise ValueError('Stop the mission before selecting another scenario')
            if getattr(self.args,'replay',False):raise ValueError('Replay mode cannot select a live scenario')
            definition=_definition.load(choices[identifier]['directory'])
            self.scenario_path=Path(definition['_directory'])
            self.definition=definition
            self.ready=False
        self.action('prepare')

    def action(self,name):
        if getattr(self.args,'replay',False):raise ValueError('Replay mode does not launch or control simulation services')
        with self.lock:
            if self.busy:raise ValueError('A process action is already running')
            if name not in ('prepare','start','stop','pause','resume'):raise ValueError('Unknown action')
            if name=='start' and (not self.ready or self.mission_started):raise ValueError('Services must be ready before mission launch')
            self.busy=True;self.error=None
        def work():
            with self.operation_lock:
                try:
                    self.ensure_running()
                    if name=='prepare':self.stop();self.processes={};self.bootstrap()
                    elif name=='start':self.start()
                    elif name=='stop':self.stop()
                    else:self.write_command(start=True,paused=name=='pause',stop=False);self.log('Simulation '+('paused' if name=='pause' else 'resumed'))
                except Exception as error:
                    self.error=str(error);self.log(error)
                    if name in ('start','prepare'):self.stop()
                finally:self.busy=False
        threading.Thread(target=work,daemon=True).start()
    def snapshot(self):
        if getattr(self.args,'replay',False):
            recordings=self.recordings.list()
            if recordings:return self.recorded_snapshot(recordings[0]['id'],0.)
            return {**self.control_state(),'producer':{},'skill':{},'scenario':{},'camera':{'available':False},
                'synchronization':{'status':'waiting'},'recordings':[],'no_render':True}
        skill={}
        try:
            with urlopen(f'http://127.0.0.1:{self.args.skill_port}/status',timeout=.4) as response:skill=_recording.display_result(json.load(response))
            self.last_skill=skill
        except (OSError,ValueError,URLError):
            if self.last_skill:skill={**self.last_skill,'status':'offline','payload_bytes_per_second':0.}
        producer=self.read('producer.json')
        transport=skill;camera_metadata=self.read('camera.json')
        no_render=self.args.no_render
        cameras=([{'sim_time_ns':skill.get('sim_time_ns')}] if no_render else
            [camera for camera in camera_metadata.get('history',[camera_metadata])
             if camera.get('geometry_sha256')==producer.get('geometry_sha256') and
                (self.run/'camera'/(camera.get('key','')+'.jpg')).is_file()])
        previous=self.last_display
        pair=select_display_pair(producer.get('history',[]),skill.get('available_epochs',[]),cameras,self.read('scenario.json').get('advance_ns',120_000_000)//2,
            None if previous is None else previous['row']['sim_time_ns'])
        if pair is not None:
            row,camera_metadata=pair
            # Keep the closest image even if a late callback arrives out of order.
            if previous is not None and row['sim_time_ns']==previous['row']['sim_time_ns'] and not no_render:
                old_offset=abs(previous['camera']['sim_time_ns']-row['sim_time_ns'])
                if abs(camera_metadata['sim_time_ns']-row['sim_time_ns'])>=old_offset:
                    camera_metadata=previous['camera']
            try:
                if previous is not None and row['sim_time_ns']==previous['row']['sim_time_ns']:
                    diagnostics=previous['skill'];frame_producer=previous['producer']
                else:
                    with urlopen(f'http://127.0.0.1:{self.args.skill_port}/frames/{row["sim_time_ns"]}',timeout=.4) as response:
                        diagnostics=_recording.display_result(json.load(response))
                    frame_producer={**producer,**row,'history':[r for r in producer.get('history',[]) if r['sim_time_ns']<=row['sim_time_ns']]}
                if diagnostics.get('sim_time_ns')==row['sim_time_ns']:
                    self.last_display={'row':row,'skill':diagnostics,'producer':frame_producer,'camera':camera_metadata}
            except (OSError,ValueError,URLError):pass
        display=self.last_display
        synchronization={'status':'waiting','latest_rf_sim_time_ns':transport.get('sim_time_ns')}
        skill={}
        if display is not None:
            row=display['row'];skill=display['skill']
            # Service lifecycle controls stay live; all mission measurements,
            # including counters/speed/history, come from the presented frame.
            producer={**display['producer'],'status':producer.get('status'),'error':producer.get('error')}
            camera_metadata=display['camera']
            synchronization.update(status='matched',rf_sim_time_ns=row['sim_time_ns'],
                camera_sim_time_ns=None if no_render else camera_metadata.get('sim_time_ns'),
                offset_ms=None if no_render else (camera_metadata['sim_time_ns']-row['sim_time_ns'])/1e6)
        else:
            producer={key:producer[key] for key in ('status','error','presentation_session') if key in producer}
        processes={part:{'pid':p.pid,'state':'running' if p.poll() is None else 'exited','exit_code':p.poll(),'container':self.names[part]} for part,p in self.processes.items()}
        key=camera_metadata.get('key','')
        camera=self.run/'camera'/(key+'.jpg')
        camera_available=display is not None and not no_render and camera.is_file()
        return {'processes':processes,'producer':producer,'skill':skill,'scenario':self.read('scenario.json'),
                'transport':skill,'service_health':{'skill_status':transport.get('status'),'skill_error':transport.get('error')},'synchronization':synchronization,
                'camera':{'available':camera_available,'age_s':time.time()-camera.stat().st_mtime if camera_available else None,
                    'url':'/camera.jpg?frame='+key,'source':'Timestamped ProjectAirSim Chase scene_camera'},
                'ready':self.ready and all(p.poll() is None for p in self.processes.values()) and transport.get('status') not in ('offline','failed'),'mission_started':self.mission_started,'busy':self.busy,'error':self.error,'events':list(self.events),'no_render':self.args.no_render,
                'run_directory':str(self.run),'token':self.token,'recordings':self.recordings.list(),'replay_only':False}

    def control_state(self):
        replay=getattr(self.args,'replay',False)
        producer={} if replay else self.read('producer.json')
        processes={part:{'pid':p.pid,'state':'running' if p.poll() is None else 'exited','exit_code':p.poll(),
            'container':self.names[part]} for part,p in self.processes.items()}
        if not replay and processes and time.monotonic()-self.health_updated>1:
            self.health_updated=time.monotonic()
            try:
                with urlopen(f'http://127.0.0.1:{self.args.skill_port}/health',timeout=.25) as response:health=json.load(response)
                self.skill_health={'skill_status':health.get('status'),'skill_error':health.get('error')}
            except (OSError,ValueError,URLError):self.skill_health={'skill_status':'offline','skill_error':'RF skill health check failed'}
        return {'processes':processes,'control_producer':producer,
            'ready':not replay and self.ready and all(p.poll() is None for p in self.processes.values()) and producer.get('status')!='failed'
                and self.skill_health.get('skill_status') not in ('failed','offline'),
            'mission_started':self.mission_started,'busy':self.busy,'error':self.error,'events':list(self.events),
            'run_directory':str(self.run),'token':self.token,'replay_only':replay,
            'service_health':self.skill_health,
            'active_recording_id':producer.get('presentation_session') if any(p.poll() is None for p in self.processes.values()) else None}

    def recorded_snapshot(self,identifier,time_s=None):
        return {**self.recordings.snapshot(identifier,time_s),**self.control_state(),'recordings':self.recordings.list()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path.cwd());parser.add_argument('--run-dir',type=Path,default=Path('recordings/dashboard'))
    parser.add_argument('--port',type=int,default=8765);parser.add_argument('--iq-port',type=int,default=8811)
    parser.add_argument('--skill-port',type=int,default=8812);parser.add_argument('--control-port',type=int,default=8813)
    parser.add_argument('--duration',type=float,default=None);parser.add_argument('--pascal-compat',action='store_true')
    parser.add_argument('--no-render',action='store_true',help='Explicit diagnostic mode: no Unreal camera image')
    parser.add_argument('--replay',action='store_true',help='Replay saved dashboard runs without Docker, a GPU or simulation startup')
    parser.add_argument('--ready-timeout',type=float,default=600)
    parser.add_argument('--gpu-mode',choices=('auto','cdi','gpus'),default='auto')
    parser.add_argument('--gpu-device',default='0',help='NVIDIA device index or UUID')
    registry='ghcr.io/wa200508/airsim-rf'
    parser.add_argument('--sim-image',default=registry+':dashboard-render');parser.add_argument('--rf-image',default=registry+':dashboard-gpu')
    parser.add_argument('--skill-image',default=None)
    parser.add_argument('--scenario',help='Packaged scenario ID, input directory or scenario.json')
    parser.add_argument('--list-scenarios',action='store_true',help='List packaged scenario IDs without Docker')
    parser.add_argument('--check-scenario',action='store_true',help='Validate inputs, relative assets and clocks, then exit without Docker')
    parser.add_argument('--export-scenario',type=Path,help='Copy editable scenario inputs to a new directory and exit')
    parser.add_argument('--open',action='store_true');args=parser.parse_args()
    if args.list_scenarios:
        print(json.dumps(_definition.catalog(),indent=2));return
    args.duration_from_scenario=args.duration is None;args.skill_image_override=args.skill_image is not None
    if not args.replay or args.check_scenario or args.export_scenario:
        try:
            definition=_definition.load(args.scenario)
            args.scenario=Path(definition['_directory'])
            if args.export_scenario:
                if args.export_scenario.exists():parser.error('Export destination already exists; choose a new directory')
                _definition.snapshot(args.scenario,args.export_scenario);print(str(args.export_scenario.resolve()));return
            if args.check_scenario:
                print(json.dumps({'status':'valid','scenario':definition['id'],'directory':definition['_directory'],'sha256':_definition.fingerprints(args.scenario)},indent=2));return
            if args.duration is None:args.duration=definition['mission']['duration_s']
        except (OSError,ValueError,KeyError,TypeError) as error:parser.error(str(error))
    elif args.duration is None:args.duration=120
    if args.replay and not (args.run_dir/'replays').is_dir():parser.error('No replay recordings in this run directory; select --run-dir from a recorded mission')
    if not 0<args.duration<=3600:parser.error('duration must be in (0,3600] seconds')
    if not 0<args.ready_timeout<=1800:parser.error('ready-timeout must be in (0,1800] seconds')
    for port in (args.port,args.iq_port,args.skill_port,args.control_port):
        if not 1024<=port<=65535:parser.error('ports must be in 1024–65535')
    ports=(args.port,args.iq_port,args.skill_port,*([args.control_port] if args.replay or definition['skill']['ports']['control'] is not None else []),8989,8990)
    if len(set(ports))!=len(ports):parser.error('dashboard, I/Q, skill HTTP, control and simulator ports must be distinct')
    dashboard=Dashboard(args)
    assets=Path(__file__).with_name('dashboard_static')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url=urlsplit(self.path);query=parse_qs(url.query)
            if url.path=='/api/status':
                try:
                    identifier=query.get('recording',[None])[0]
                    time_s=float(query['time_s'][0]) if 'time_s' in query else None
                    if time_s is not None and not math.isfinite(time_s):raise ValueError('Playback time must be finite')
                    state=dashboard.snapshot() if identifier is None else dashboard.recorded_snapshot(identifier,time_s)
                except (ValueError,OSError,KeyError) as error:self.send_error(404,str(error));return
                state['scenario_catalog']=_definition.catalog()
                state['selected_scenario']=dashboard.definition['id'] if dashboard.definition else None
                data=json.dumps(state,allow_nan=False).encode();kind='application/json'
            elif urlsplit(self.path).path=='/camera.jpg':
                key=query.get('frame',[''])[0]
                if not re.fullmatch(r'[0-9a-f]{16}-[0-9]+',key):self.send_error(404);return
                try:
                    root=dashboard.recordings.path(query['recording'][0]) if 'recording' in query else dashboard.run
                    data=(root/'camera'/(key+'.jpg')).read_bytes();kind='image/jpeg'
                except (OSError,ValueError):self.send_error(404,'No ProjectAirSim camera frame received');return
            elif self.path in ('/','/app.js','/style.css'):
                name={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[self.path]
                data=assets.joinpath(name).read_bytes();kind={'index.html':'text/html','app.js':'text/javascript','style.css':'text/css'}[name]
            elif self.path.startswith('/api/log/'):
                part=self.path.rsplit('/',1)[-1]
                if part not in ('rf','sim','skill'):self.send_error(404);return
                path=dashboard.run/f'{part}.log';data=(path.read_bytes()[-18000:] if path.exists() else b'No logs yet');kind='text/plain'
            else:self.send_error(404);return
            try:
                self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):
                pass  # Closing the tab or abandoning an image request is normal.
        def do_POST(self):
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{args.port}',f'http://localhost:{args.port}'):
                self.send_error(403);return
            if self.headers.get('X-Dashboard-Token')!=dashboard.token:self.send_error(403);return
            try:
                if self.path=='/api/scenario':
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=4096:raise ValueError('Invalid scenario selection')
                    dashboard.select_scenario(json.loads(self.rfile.read(size))['id'])
                else:dashboard.action(self.path.removeprefix('/api/'))
                self.send_response(202);self.end_headers()
            except (ValueError,KeyError,TypeError) as error:self.send_error(409,str(error))
        def log_message(self,*args):pass
    server=None;previous_handlers={}
    def shutdown(*_):raise DashboardShutdown()
    try:
        # Install before image pulls, one-shot preparation and container launch,
        # not only after bootstrap. Terminal close also sends SIGHUP.
        for name in ('SIGINT','SIGTERM','SIGHUP'):
            number=getattr(signal,name,None)
            if number is not None:previous_handlers[number]=signal.signal(number,shutdown)
        if not args.replay:dashboard.acquire_run()
        try:server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
        except OSError as error:
            raise RuntimeError(f'Cannot open dashboard at http://localhost:{args.port}; '
                'stop the existing launcher or select another --port. '+str(error)) from error
        if not args.replay:dashboard.bootstrap()
        print(f'RF mission dashboard: http://localhost:{args.port}',flush=True)
        if args.open:webbrowser.open(f'http://localhost:{args.port}')
        server.serve_forever()
    except DashboardShutdown:
        print('Stopping dashboard and cleaning up its containers and network...',flush=True)
    finally:
        for number in previous_handlers:signal.signal(number,signal.SIG_IGN)
        try:dashboard.close()
        finally:
            if server:server.server_close()
            for number,handler in previous_handlers.items():signal.signal(number,handler)


if __name__=='__main__':main()
