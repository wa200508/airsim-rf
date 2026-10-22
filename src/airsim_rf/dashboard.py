"""Python localhost launcher and process supervisor for the primary RF use case."""
import argparse
from collections import deque
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from importlib.resources import files
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser


class Dashboard:
    def __init__(self,args):
        self.args=args;self.root=args.repo.resolve();self.run=args.run_dir.resolve();self.run.mkdir(parents=True,exist_ok=True)
        self.token=secrets.token_urlsafe(24);self.lock=threading.Lock();self.events=deque(maxlen=40);self.busy=False;self.error=None
        self.processes={};self.last_skill={};self.ready=False;self.mission_started=False;self.image_tags={name:getattr(args,name) for name in ('sim_image','skill_image','rf_image')};self.names={part:f'airsim-rf-dashboard-{part}-{args.port}' for part in ('sim','rf','skill')}
        self.log('Preparing separate simulator, GPU RF and MUSIC skill containers.')
        if os.getuid()==0:os.chown(self.run,10001,10001)

    def log(self,message):self.events.append({'time':time.strftime('%H:%M:%S'),'message':str(message)})
    def command(self,args,check=True):
        result=subprocess.run(args,cwd=self.root,capture_output=True,text=True,timeout=self.args.ready_timeout)
        if check and result.returncode:raise RuntimeError((result.stderr or result.stdout)[-2500:])
        return result
    def launch(self,part,args):
        log=(self.run/f'{part}.log').open('a')
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
            if part and self.processes[part].poll() is not None:
                raise RuntimeError(f'{part} exited before readiness; see {self.run}/{part}.log')
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.3):return
            except OSError:time.sleep(.25)
        raise RuntimeError(f'Process did not listen on localhost:{port}; check run logs')
    def uid(self):
        return f'{os.getuid()}:{os.getgid()}' if os.getuid() else '10001:10001'
    def prepare(self):
        script='from airsim_rf.dashboard_scenario import prepare; prepare("/run", "/opt/airsim-rf/.deps/ProjectAirSim")'
        self.command(['docker','run','--rm','--network','none','--user',self.uid(),'-e','HOME=/tmp',
            '-v',f'{self.run}:/run','--entrypoint','python',self.args.rf_image,'-c',script])
    def pull_images(self):
        revisions=[]
        for name in ('sim_image','skill_image','rf_image'):
            image=self.image_tags[name]
            self.log('Pulling '+image)
            subprocess.run(['docker','pull',image],check=True,cwd=self.root)
            metadata=json.loads(self.command(['docker','image','inspect',image]).stdout)[0]
            revision=metadata.get('Config',{}).get('Labels',{}).get('org.opencontainers.image.revision')
            revisions.append(revision)
            # The launched containers use the verified immutable local image ID.
            setattr(self.args,name,metadata['Id'])
        if len(set(revisions))!=1 or revisions[0] in (None,'unknown',''):
            raise RuntimeError('Dashboard image revisions differ or are unversioned; retry after publication completes')
        self.log('Verified all three images at revision '+revisions[0])
    def bootstrap(self):
        self.ready=False;self.mission_started=False;self.last_skill={}
        self.command(['docker','info','--format','{{.ServerVersion}}'])
        self.pull_images()
        for port in (8989,8990,self.args.iq_port,self.args.skill_port,self.args.control_port):
            with socket.socket() as test:
                if test.connect_ex(('127.0.0.1',port))==0:raise RuntimeError(f'Port {port} already in use')
        for name in ('producer.json','camera.jpg'):
            path=self.run/name
            if path.exists():path.replace(self.run/(name+'.previous'))
        self.prepare();self.write_command(start=False,paused=False,stop=False)
        sim=['docker','run','--rm','--init','--name',self.names['sim'],'--user',self.uid(),'--shm-size','1g',
             '-p','127.0.0.1:8989:8989','-p','127.0.0.1:8990:8990',self.args.sim_image]
        if self.args.no_render:
            sim[sim.index(self.args.sim_image):sim.index(self.args.sim_image)]=['--entrypoint','/opt/blocks/Blocks/Binaries/Linux/Blocks-Linux-Shipping']
            sim+=['Blocks','-nullrhi','-nosound','-unattended']
        # Start the independent containers without serial readiness waits.
        self.launch('sim',sim)
        self.launch('skill',['docker','run','--rm','--init','--name',self.names['skill'],'--user',self.uid(),
             '-p',f'127.0.0.1:{self.args.iq_port}:8811','-p',f'127.0.0.1:{self.args.skill_port}:8812',
             '-p',f'127.0.0.1:{self.args.control_port}:8813',
             '-v',f'{self.run}/arrays.json:/config/arrays.json:ro',self.args.skill_image])
        self.launch('rf',['docker','run','--rm','--init','--name',self.names['rf'],'--gpus','device=0','--network','host',
            '--user',self.uid(),'--tmpfs','/.drjit:rw,mode=1777','-e','HOME=/tmp',
            '-v',f'{self.run}:/run','--entrypoint','/opt/airsim-rf/.venv/bin/python',self.args.rf_image,
            '-m','airsim_rf.cuda_launch','-m','airsim_rf.dashboard_producer','--run-dir','/run',
            '--duration',str(self.args.duration),'--skill-port',str(self.args.iq_port),'--wait-for-mission',
            '--ready-timeout',str(self.args.ready_timeout),*(['--no-render'] if self.args.no_render else []),
            *(['--pascal-compat'] if self.args.pascal_compat else [])])
        self.wait_port(8989,self.args.ready_timeout,part='sim')
        self.wait_port(self.args.skill_port,self.args.ready_timeout,part='skill')
        deadline=time.monotonic()+self.args.ready_timeout
        while time.monotonic()<deadline:
            for part,process in self.processes.items():
                if process.poll() is not None:raise RuntimeError(f'{part} failed startup; see {self.run}/{part}.log')
            state=self.read('producer.json')
            if state.get('status')=='failed':raise RuntimeError(state.get('error','RF startup failed'))
            if state.get('status')=='ready':
                with urlopen(f'http://127.0.0.1:{self.args.skill_port}/health',timeout=2) as response:
                    if response.status==200:
                        self.ready=True;self.log('READY: GPU/OptiX/CuPy checked, scene and camera prepared, skill connected; mission paused')
                        return
            time.sleep(.25)
        raise RuntimeError('Services did not become mission-ready; inspect simulator, RF and skill logs')
    def start(self):
        if not self.ready or self.mission_started or any(p.poll() is not None for p in self.processes.values()):
            raise ValueError('Prepare healthy containers before launching a mission')
        self.write_command(start=True,paused=False,stop=False);self.mission_started=True
        self.log('Starting mission in the already prepared containers')
    def stop(self):
        self.ready=False;self.mission_started=False
        self.write_command(stop=True)
        process=self.processes.get('rf')
        if process:
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:pass
        for part in ('rf','skill','sim'):
            if part in self.processes:
                self.command(['docker','stop','-t','5',self.names[part]],check=False)
                try:self.processes[part].wait(timeout=5)
                except subprocess.TimeoutExpired:self.processes[part].terminate()
        self.log('Stopped task-owned processes')
    def action(self,name):
        with self.lock:
            if self.busy:raise ValueError('A process action is already running')
            if name not in ('prepare','start','stop','pause','resume'):raise ValueError('Unknown action')
            if name=='start' and (not self.ready or self.mission_started):raise ValueError('Services must be ready before mission launch')
            self.busy=True;self.error=None
        def work():
            try:
                if name=='prepare':self.stop();self.processes={};self.bootstrap()
                elif name=='start':self.start()
                elif name=='stop':self.stop()
                else:self.write_command(start=True,paused=name=='pause',stop=False);self.log('Simulation '+('paused' if name=='pause' else 'resumed'))
            except Exception as error:
                self.error=str(error);self.log(error)
                if name in ('start','prepare') and self.processes:self.stop()
            finally:self.busy=False
        threading.Thread(target=work,daemon=True).start()
    def snapshot(self):
        skill={}
        try:
            with urlopen(f'http://127.0.0.1:{self.args.skill_port}/status',timeout=.4) as response:skill=json.load(response)
            self.last_skill=skill
        except (OSError,ValueError,URLError):
            if self.last_skill:skill={**self.last_skill,'status':'offline','payload_bytes_per_second':0.}
        producer=self.read('producer.json')
        processes={part:{'pid':p.pid,'state':'running' if p.poll() is None else 'exited','exit_code':p.poll(),'container':self.names[part]} for part,p in self.processes.items()}
        camera=self.run/'camera.jpg'
        return {'processes':processes,'producer':producer,'skill':skill,'scenario':self.read('scenario.json'),
                'camera':{'available':camera.exists(),'age_s':time.time()-camera.stat().st_mtime if camera.exists() else None,'source':'ProjectAirSim Chase scene_camera'},
                'ready':self.ready and all(p.poll() is None for p in self.processes.values()) and skill.get('status')!='offline','mission_started':self.mission_started,'busy':self.busy,'error':self.error,'events':list(self.events),'no_render':self.args.no_render,
                'run_directory':str(self.run),'token':self.token}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path.cwd());parser.add_argument('--run-dir',type=Path,default=Path('recordings/dashboard'))
    parser.add_argument('--port',type=int,default=8765);parser.add_argument('--iq-port',type=int,default=8811)
    parser.add_argument('--skill-port',type=int,default=8812);parser.add_argument('--control-port',type=int,default=8813)
    parser.add_argument('--duration',type=float,default=120);parser.add_argument('--pascal-compat',action='store_true')
    parser.add_argument('--no-render',action='store_true',help='Explicit diagnostic mode: no Unreal camera image')
    parser.add_argument('--ready-timeout',type=float,default=300)
    registry='ghcr.io/wa200508/airsim-rf'
    parser.add_argument('--sim-image',default=registry+':dashboard-render');parser.add_argument('--rf-image',default=registry+':dashboard-gpu')
    parser.add_argument('--skill-image',default=registry+':dashboard-skill')
    parser.add_argument('--open',action='store_true');args=parser.parse_args()
    if not 0<args.duration<=3600:parser.error('duration must be in (0,3600] seconds')
    if not 0<args.ready_timeout<=1800:parser.error('ready-timeout must be in (0,1800] seconds')
    for port in (args.port,args.iq_port,args.skill_port,args.control_port):
        if not 1024<=port<=65535:parser.error('ports must be in 1024–65535')
    ports=(args.port,args.iq_port,args.skill_port,args.control_port,8989,8990)
    if len(set(ports))!=len(ports):parser.error('dashboard, I/Q, skill HTTP, control and simulator ports must be distinct')
    dashboard=Dashboard(args)
    try:dashboard.bootstrap()
    except BaseException:
        dashboard.stop();raise
    assets=Path(__file__).with_name('dashboard_static')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path=='/api/status':data=json.dumps(dashboard.snapshot(),allow_nan=False).encode();kind='application/json'
            elif self.path.startswith('/camera.jpg'):
                try:data=(dashboard.run/'camera.jpg').read_bytes();kind='image/jpeg'
                except OSError:self.send_error(404,'No ProjectAirSim camera frame received');return
            elif self.path in ('/','/app.js','/style.css'):
                name={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[self.path]
                data=assets.joinpath(name).read_bytes();kind={'index.html':'text/html','app.js':'text/javascript','style.css':'text/css'}[name]
            elif self.path.startswith('/api/log/'):
                part=self.path.rsplit('/',1)[-1]
                if part not in ('rf','sim','skill'):self.send_error(404);return
                path=dashboard.run/f'{part}.log';data=(path.read_bytes()[-18000:] if path.exists() else b'No logs yet');kind='text/plain'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
        def do_POST(self):
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{args.port}',f'http://localhost:{args.port}'):
                self.send_error(403);return
            if self.headers.get('X-Dashboard-Token')!=dashboard.token:self.send_error(403);return
            try:dashboard.action(self.path.removeprefix('/api/'));self.send_response(202);self.end_headers()
            except ValueError as error:self.send_error(409,str(error))
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'RF mission dashboard: http://localhost:{args.port}',flush=True)
    if args.open:webbrowser.open(f'http://localhost:{args.port}')
    def shutdown(*_):threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
    try:server.serve_forever()
    finally:dashboard.stop();server.server_close()


if __name__=='__main__':main()
