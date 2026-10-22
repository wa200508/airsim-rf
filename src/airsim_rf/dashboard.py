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
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser


class Dashboard:
    def __init__(self,args):
        self.args=args;self.root=args.repo.resolve();self.run=args.run_dir.resolve();self.run.mkdir(parents=True,exist_ok=True)
        self.token=secrets.token_urlsafe(24);self.lock=threading.Lock();self.events=deque(maxlen=40);self.busy=False;self.error=None
        self.processes={};self.last_skill={};self.names={part:f'airsim-rf-dashboard-{part}-{args.port}' for part in ('sim','rf','skill')}
        self.log('Dashboard ready; prepare and start the three processes.')

    def log(self,message):self.events.append({'time':time.strftime('%H:%M:%S'),'message':str(message)})
    def command(self,args,check=True):
        result=subprocess.run(args,cwd=self.root,capture_output=True,text=True,timeout=120)
        if check and result.returncode:raise RuntimeError((result.stderr or result.stdout)[-2500:])
        return result
    def launch(self,part,args,**kwargs):
        log=(self.run/f'{part}.log').open('a')
        process=subprocess.Popen(args,cwd=kwargs.pop('cwd',self.root),stdout=log,stderr=subprocess.STDOUT,start_new_session=True,**kwargs)
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
    def prepare(self):
        if (self.run/'arrays.json').exists():return
        if self.args.container_runtime:
            script='from airsim_rf.dashboard_scenario import prepare; import sys; prepare(sys.argv[1],sys.argv[2])'
            self.command([sys.executable,'-c',script,str(self.run),str(self.root/'.deps/ProjectAirSim')])
            return
        script='from airsim_rf.dashboard_scenario import prepare; prepare("/run", "/work/repo/.deps/ProjectAirSim-runtime")'
        self.command(['docker','run','--rm','--network','none','--user',f'{__import__("os").getuid()}:{__import__("os").getgid()}',
            '-e','HOME=/tmp','-e','PYTHONPATH=/work/repo/src:/work/repo/.deps/openusd-26.8',
            '-v',f'{self.root}:/work/repo:ro','-v',f'{self.run}:/run','-w','/tmp','--entrypoint','python',self.args.cpu_image,'-c',script])
    def start(self):
        if self.args.container_runtime:return self.start_local()
        self.prepare();self.last_skill={}
        for name in ('producer.json','camera.jpg'):
            path=self.run/name
            if path.exists():path.replace(self.run/(name+'.previous'))
        self.write_command(paused=False,stop=False)
        for port in (8989,8990,self.args.iq_port,self.args.skill_port,self.args.control_port):
            with socket.socket() as test:
                if test.connect_ex(('127.0.0.1',port))==0:raise RuntimeError(f'Port {port} already in use; use a dedicated simulator/skill instance')
        uid=f'{__import__("os").getuid()}:{__import__("os").getgid()}'
        self.log('Starting ProjectAirSim with Unreal camera rendering')
        sim=['docker','run','--rm','--name',self.names['sim'],'--user',uid,
             '-p','127.0.0.1:8989:8989','-p','127.0.0.1:8990:8990',
             '-v',f'{self.args.blocks.resolve()}:/blocks:ro','-w','/blocks',self.args.sim_image]
        if self.args.no_render:
            sim += ['Blocks','-nullrhi','-nosound','-unattended']
            # Explicit diagnostic mode; never presented as a live rendered camera.
            sim[sim.index(self.args.sim_image):sim.index(self.args.sim_image)]=['--entrypoint','/blocks/Blocks/Binaries/Linux/Blocks-Linux-Shipping']
        self.launch('sim',sim);self.wait_port(8989,90,part='sim')
        self.log('Starting independent CPU MUSIC RF Skill container')
        self.launch('skill',['docker','run','--rm','--name',self.names['skill'],'--network','bridge','--user',uid,
             '-p',f'127.0.0.1:{self.args.iq_port}:8811','-p',f'127.0.0.1:{self.args.skill_port}:8812',
             '-p',f'127.0.0.1:{self.args.control_port}:8813',
             '-v',f'{self.run}/arrays.json:/config/arrays.json:ro',self.args.skill_image])
        self.wait_port(self.args.skill_port,60,part='skill')
        deadline=time.monotonic()+30
        while True:
            try:
                with urlopen(f'http://127.0.0.1:{self.args.skill_port}/health',timeout=1) as response:
                    if response.status==200:break
            except (OSError,URLError):pass
            if time.monotonic()>deadline:raise RuntimeError('RF skill ingress failed its health check')
            time.sleep(.2)
        self.log('Starting airsim_rf + Sionna CUDA deployment; one simulation stepping owner')
        self.launch('rf',['docker','run','--rm','--name',self.names['rf'],'--gpus','device=0','--network','host',
            '--user',uid,'--tmpfs','/.drjit:rw,mode=1777','-e','HOME=/tmp',
            '-e','PYTHONPATH=/work/repo/src:/work/repo/.deps/openusd-26.8',
            '-v',f'{self.root}:/work/repo:ro','-v',f'{self.run}:/run','-w','/tmp',
            '--entrypoint','/opt/airsim-rf/.venv/bin/python',self.args.rf_image,'-m','airsim_rf.cuda_launch',
            '-m','airsim_rf.dashboard_producer','--run-dir','/run','--duration',str(self.args.duration),
            '--skill-port',str(self.args.iq_port),*(['--pascal-compat'] if self.args.pascal_compat else [])])
        self.log('Pipeline started; waiting for actual camera and received ADC I/Q')
    def start_local(self):
        """Supervise the actual simulator, skill and CUDA producer inside one image."""
        executable=self.args.blocks.resolve()/'Blocks/Binaries/Linux/Blocks-Linux-Shipping'
        if not executable.is_file():raise RuntimeError(f'Bundled ProjectAirSim executable is missing: {executable}')
        for port in (8989,8990,self.args.iq_port,self.args.skill_port,self.args.control_port):
            with socket.socket() as test:
                if test.connect_ex(('127.0.0.1',port))==0:raise RuntimeError(f'Port {port} already in use')
        self.prepare();self.last_skill={}
        for name in ('producer.json','camera.jpg'):
            path=self.run/name
            if path.exists():path.replace(self.run/(name+'.previous'))
        self.write_command(paused=False,stop=False)
        self.log('Starting bundled ProjectAirSim, CPU MUSIC skill and CUDA RF producer')
        environment=dict(os.environ,RF_BLOCKS_DIR=str(self.args.blocks.resolve()))
        sim=([str(executable),'Blocks','-nullrhi','-nosound','-unattended'] if self.args.no_render else
             [sys.executable,str(self.root/'deploy/dashboard/render-entrypoint.py')])
        self.launch('sim',sim,cwd=self.args.blocks.resolve(),env=environment)
        self.wait_port(8989,90,part='sim')
        self.launch('skill',[sys.executable,'-m','airsim_rf.dashboard_skill','--arrays',str(self.run/'arrays.json'),
            '--iq-port',str(self.args.iq_port),'--http-port',str(self.args.skill_port),
            '--control-address',f'127.0.0.1:{self.args.control_port}'])
        self.wait_port(self.args.skill_port,60,part='skill')
        deadline=time.monotonic()+30
        while True:
            try:
                with urlopen(f'http://127.0.0.1:{self.args.skill_port}/health',timeout=1) as response:
                    if response.status==200:break
            except (OSError,URLError):pass
            if time.monotonic()>deadline:raise RuntimeError('RF skill ingress failed its health check')
            time.sleep(.2)
        self.launch('rf',[sys.executable,'-m','airsim_rf.cuda_launch','-m','airsim_rf.dashboard_producer',
            '--run-dir',str(self.run),'--duration',str(self.args.duration),'--skill-port',str(self.args.iq_port),
            *(['--pascal-compat'] if self.args.pascal_compat else [])])
        self.log('Pipeline started; waiting for actual camera and received ADC I/Q')
    def stop(self):
        self.write_command(stop=True)
        process=self.processes.get('rf')
        if process:
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:pass
        for part in ('rf','skill','sim'):
            if part in self.processes:
                if self.args.container_runtime:
                    process=self.processes[part]
                    # Kill the task-owned group, including the simulator's Xvfb child.
                    try:os.killpg(process.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:os.killpg(process.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                        process.wait(timeout=5)
                    continue
                self.command(['docker','stop','-t','5',self.names[part]],check=False)
                try:self.processes[part].wait(timeout=5)
                except subprocess.TimeoutExpired:self.processes[part].terminate()
        self.log('Stopped task-owned processes')
    def action(self,name):
        with self.lock:
            if self.busy:raise ValueError('A process action is already running')
            if name not in ('start','stop','pause','resume'):raise ValueError('Unknown action')
            if name=='start' and any(p.poll() is None for p in self.processes.values()):raise ValueError('Stop existing task processes before starting a new run')
            self.busy=True;self.error=None
        def work():
            try:
                if name=='start':self.start()
                elif name=='stop':self.stop()
                else:self.write_command(paused=name=='pause',stop=False);self.log('Simulation '+('paused' if name=='pause' else 'resumed'))
            except Exception as error:
                self.error=str(error);self.log(error)
                if name=='start' and self.processes:self.stop()
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
        processes={part:{'pid':p.pid,'state':'running' if p.poll() is None else 'exited','exit_code':p.poll(),'container':None if self.args.container_runtime else self.names[part]} for part,p in self.processes.items()}
        camera=self.run/'camera.jpg'
        return {'processes':processes,'producer':producer,'skill':skill,'scenario':self.read('scenario.json'),
                'camera':{'available':camera.exists(),'age_s':time.time()-camera.stat().st_mtime if camera.exists() else None,'source':'ProjectAirSim Chase scene_camera'},
                'busy':self.busy,'error':self.error,'events':list(self.events),'no_render':self.args.no_render,
                'run_directory':str(self.run),'token':self.token}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    bundled=os.environ.get('RF_DASHBOARD_CONTAINER')=='1'
    parser.add_argument('--container-runtime',action='store_true',default=bundled,help='Run bundled processes without a Docker socket')
    parser.add_argument('--repo',type=Path,default=Path('/opt/airsim-rf') if bundled else Path.cwd());parser.add_argument('--run-dir',type=Path,default=Path('/work/dashboard') if bundled else Path('recordings/dashboard'))
    parser.add_argument('--bind',default='0.0.0.0' if bundled else '127.0.0.1')
    parser.add_argument('--port',type=int,default=8765);parser.add_argument('--iq-port',type=int,default=8811)
    parser.add_argument('--skill-port',type=int,default=8812);parser.add_argument('--control-port',type=int,default=8813)
    parser.add_argument('--duration',type=float,default=120);parser.add_argument('--pascal-compat',action='store_true',default=bundled)
    parser.add_argument('--no-render',action='store_true',help='Explicit diagnostic mode: no Unreal camera image')
    parser.add_argument('--blocks',type=Path,default=Path('/opt/blocks') if bundled else Path('.deps/blocks-linux-1.0.1/extracted'))
    registry='ghcr.io/wa200508/airsim-rf'
    parser.add_argument('--sim-image',default=registry+':dashboard-render');parser.add_argument('--rf-image',default=registry+':dashboard-gpu')
    parser.add_argument('--skill-image',default=registry+':dashboard-skill');parser.add_argument('--cpu-image',default=registry+':dashboard-gpu')
    parser.add_argument('--build',action='store_true');parser.add_argument('--open',action='store_true');args=parser.parse_args()
    if not 0<args.duration<=3600:parser.error('duration must be in (0,3600] seconds')
    for port in (args.port,args.iq_port,args.skill_port,args.control_port):
        if not 1024<=port<=65535:parser.error('ports must be in 1024–65535')
    ports=(args.port,args.iq_port,args.skill_port,args.control_port,8989,8990)
    if len(set(ports))!=len(ports):parser.error('dashboard, I/Q, skill HTTP, control and simulator ports must be distinct')
    if args.container_runtime and args.build:parser.error('The published image already includes the runtime; --build is only for checkout deployments')
    if args.build:
        for name,image in [('simulator',args.sim_image),('skill',args.skill_image)]:
            subprocess.run(['docker','build','--build-arg','BASE_IMAGE='+args.cpu_image,'-t',image,'-f',f'deploy/dashboard/Dockerfile.{name}','.'],cwd=args.repo,check=True)
    elif not args.container_runtime:
        for image in dict.fromkeys((args.cpu_image,args.sim_image,args.skill_image,args.rf_image)):
            subprocess.run(['docker','pull',image],check=True)
    dashboard=Dashboard(args)
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
    server=ThreadingHTTPServer((args.bind,args.port),Handler)
    print(f'RF mission dashboard: http://localhost:{args.port}',flush=True)
    if args.open:webbrowser.open(f'http://localhost:{args.port}')
    def shutdown(*_):threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
    try:server.serve_forever()
    finally:dashboard.stop();server.server_close()


if __name__=='__main__':main()
