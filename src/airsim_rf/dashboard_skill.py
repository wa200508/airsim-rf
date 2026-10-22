"""CPU MUSIC skill container: coherent framed I/Q ingress and live diagnostics.

The SQUALL control protobuf is retained; coherent TCP is an explicit metadata
extension to stock SQUALL's bare SC16 UDP, not a native MEL conformance claim.
"""
import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
import time

import numpy as np

from .aoa_tracking import estimate_bearing, read_arrays
from .iq_stream import iter_stream
from .music_plots import frequency_psd, spatial_spectrum


class Skill:
    def __init__(self,arrays):
        self.arrays=read_arrays(arrays);self.lock=threading.Lock();self.started=time.monotonic()
        self.state={'status':'starting','ingress_ready':False,'payload_bytes':0,'complex_samples':0,'complete_windows':0,'payload_bytes_per_second':0.,'bearings':[],'history':[]}
        self.mode=4;self.traffic=deque();self.history=deque(maxlen=1000);self.waterfall=deque(maxlen=60);self.frames=deque(maxlen=128)

    def snapshot(self,epoch_ns=None):
        with self.lock:
            if epoch_ns is None:
                result=dict(self.state);result['available_epochs']=[frame['sim_time_ns'] for frame in self.frames]
            else:
                frame=next((frame for frame in reversed(self.frames) if frame['sim_time_ns']==epoch_ns),None)
                if frame is None:raise KeyError(epoch_ns)
                result=dict(frame)
        # Per-epoch snapshots stay immutable while the display waits for video.
        # Only live service status has an aging rate/clock.
        if epoch_ns is None:
            result['uptime_s']=time.monotonic()-self.started
            result['seconds_since_update']=time.monotonic()-result.pop('updated_monotonic',self.started)
            if result['seconds_since_update']>3:result['payload_bytes_per_second']=0.
        return result

    def epoch_status(self,epoch_ns):
        with self.lock:
            if self.state['status']=='failed':raise RuntimeError(self.state.get('error','RF skill failed'))
            frame=next((frame for frame in reversed(self.frames) if frame['sim_time_ns']==epoch_ns),None)
            if frame is None:raise KeyError(epoch_ns)
            return {key:frame[key] for key in ('sim_time_ns','complete_windows')}

    def process(self,blocks):
        start=time.monotonic();names=[n for s in self.arrays['sites'] for n in s['channels']]
        first=blocks[names[0]]
        if any((b.sim_time_ns,b.sample_start,len(b.samples),b.sample_rate_hz,b.carrier_hz)!=(first.sim_time_ns,first.sample_start,len(first.samples),first.sample_rate_hz,first.carrier_hz) for b in blocks.values()):
            raise ValueError('Coherent array block epochs/offsets/rates differ')
        if first.sample_rate_hz!=self.arrays['sample_rate_hz'] or first.carrier_hz!=self.arrays['carrier_hz']:raise ValueError('Array rate/carrier mismatch')
        grid=np.linspace(-70,70,1401);bearings=[];curves=[];eigen=[];phase=None;psd=None
        for index,site in enumerate(self.arrays['sites']):
            gain=np.asarray(site['calibration_complex']);gain=gain[:,0]+1j*gain[:,1]
            # Every sample is transported; a declared 24k simultaneous snapshot
            # bounds covariance/plot latency without changing the producer rate.
            matrix=np.stack([blocks[n].samples[:24000]/g for n,g in zip(site['channels'],gain)])
            result=estimate_bearing(matrix,site['element_offsets_m'],first.carrier_hz,grid_deg=grid)
            result['received_power_dbm']=float(10*np.log10(max(float(np.mean(abs(matrix)**2))/50,1e-30)*1000))
            bearings.append(result)
            curves.append(spatial_spectrum(matrix,site['element_offsets_m'],first.carrier_hz,grid).tolist())
            eig=np.linalg.eigvalsh(np.cov(matrix))[::-1];eigen.append((10*np.log10(np.maximum(eig/eig[0],1e-12))).tolist())
            if index==0:
                f,t,p=frequency_psd(matrix[0],first.sample_rate_hz);mask=abs(f)<=100000
                psd={'frequency_khz':(f[mask]/1000).tolist(),'density_db_v2_hz':(10*np.log10(np.maximum(p[mask].mean(axis=1),1e-30))).tolist()}
                phase=np.unwrap(np.angle(np.mean(matrix*matrix[0].conj(),axis=1))).tolist()
        now=time.monotonic();self.traffic.append((now,self.state['payload_bytes']))
        while len(self.traffic)>1 and self.traffic[0][0]<now-3:self.traffic.popleft()
        elapsed=now-self.traffic[0][0]
        rate=(self.state['payload_bytes']-self.traffic[0][1])/elapsed if elapsed>.01 else 0.
        self.waterfall.append({'sim_time_ns':first.sim_time_ns,'psd_db':psd['density_db_v2_hz']})
        self.history.append({'sim_time_ns':first.sim_time_ns,'angles_deg':[b['angle_deg'] if b['detected'] else None for b in bearings],
            'detected':[b['detected'] for b in bearings],'payload_bytes':self.state['payload_bytes'],'sample_start':first.sample_start})
        with self.lock:
            self.state.update(status='processing',complete_windows=self.state['complete_windows']+1,
                sim_time_ns=first.sim_time_ns,sample_start=first.sample_start,samples_per_channel=len(first.samples),
                payload_bytes_per_second=rate,bearings=bearings,psd=psd,angle_grid_deg=grid.tolist(),music_db=curves,
                eigenvalues_db=eigen,phase_rad=phase,history=list(self.history),waterfall=list(self.waterfall),updated_monotonic=now,
                processing_latency_ms=(now-start)*1000,source='received ADC complex volts; no emitter truth',
                ambiguity='ULA cone angle; full-circle front/back and elevation ambiguities; multipath peaks are candidates')
            self.frames.append({key:value for key,value in self.state.items() if key!='updated_monotonic'})

    def healthy(self):
        state=self.snapshot()
        return state['ingress_ready'] and state['status']!='failed'

    def serve_stream(self,port):
        try:self._serve_stream(port)
        except Exception as error:
            with self.lock:self.state.update(status='failed',ingress_ready=False,error=str(error))

    def _serve_stream(self,port):
        names={n for s in self.arrays['sites'] for n in s['channels']}
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);server.bind(('0.0.0.0',port));server.listen(1)
            with self.lock:self.state.update(status='listening',ingress_ready=True)
            while True:
                conn,_=server.accept();pending={};epoch=None;completed=0
                with conn:
                    conn.settimeout(3600)
                    try:
                        def validate_end():
                            if pending:raise ValueError('Stream completed with incomplete coherent array')
                            if not completed:raise ValueError('Stream contains no coherent array windows')
                        for block in iter_stream(conn,validate_end=validate_end):
                            if block.receiver not in names or block.receiver in pending:raise ValueError('Unknown or duplicate array channel')
                            if epoch is None:epoch=block.sim_time_ns
                            if block.sim_time_ns!=epoch:raise ValueError('Incomplete array window before next epoch')
                            pending[block.receiver]=block
                            with self.lock:
                                self.state['payload_bytes']+=block.samples.nbytes;self.state['complex_samples']+=len(block.samples)
                            if set(pending)==names:
                                self.process(pending);pending={};epoch=None;completed+=1
                        if pending:raise ValueError('Stream completed with incomplete coherent array')
                        with self.lock:self.state['status']='complete'
                    except Exception as error:
                        with self.lock:self.state.update(status='failed',error=str(error))


def start_control(skill,address):
    import grpc
    from .ams import squall_rf_pb2 as pb, squall_rf_pb2_grpc as rpc
    class Control(rpc.SquallRfControlServicer):
        def GetStatus(self,request,context):
            state=skill.snapshot()
            return pb.GetStatusResponse(name='music-rf-skill',domain='rf',running=True,ready=skill.healthy(),uptime_seconds=int(state['uptime_s']),rf_status=pb.RfStatus(center_frequency_hz=915000000,sample_rate=2000000,block_size=240000,source_type='coherent_iq_tcp_extension',current_mode=skill.mode))
        def TuneRf(self,request,context):
            valid=request.center_frequency_hz in (0,915000000) and request.sample_rate in (0,2000000) and request.bandwidth_hz in (0,200000) and not request.HasField('gain') and not request.HasField('agc')
            return pb.TuneRfResponse(success=valid,actual_center_frequency_hz=915000000,error_message='' if valid else 'Fixed demo profile; tuning requires a new coherent stream')
        def CommandRf(self,request,context):
            # This consumer cannot truthfully control the producer's acquisition.
            return pb.CommandRfResponse(success=False,error_message='Consumer-only skill; use dashboard run/pause controls on the producer')
        def AddDataDestination(self,request,context):
            return pb.AddDataDestinationResponse(success=False,error_message='Coherent MUSIC consumes framed TCP; bare SQUALL UDP cannot preserve array timing')
        def RemoveDataDestination(self,request,context):
            return pb.RemoveDataDestinationResponse(success=False,error_message='No bare UDP destinations registered')
    server=grpc.server(ThreadPoolExecutor(max_workers=2));rpc.add_SquallRfControlServicer_to_server(Control(),server)
    if not server.add_insecure_port(address):raise RuntimeError('Cannot bind SQUALL control endpoint')
    server.start();return server


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--arrays',required=True)
    parser.add_argument('--iq-port',type=int,default=8811);parser.add_argument('--http-port',type=int,default=8812)
    parser.add_argument('--control-address',default='0.0.0.0:8813');args=parser.parse_args()
    skill=Skill(args.arrays);control=start_control(skill,args.control_address)
    threading.Thread(target=skill.serve_stream,args=(args.iq_port,),daemon=True).start()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                if self.path in ('/health','/status'):state=skill.snapshot()
                elif self.path.startswith('/frames/'):state=skill.snapshot(int(self.path.removeprefix('/frames/')))
                elif self.path.startswith('/epochs/'):state=skill.epoch_status(int(self.path.removeprefix('/epochs/')))
                else:self.send_error(404);return
            except (KeyError,ValueError):self.send_error(404,'No diagnostics for that simulation epoch');return
            except RuntimeError as error:self.send_error(503,str(error));return
            data=json.dumps(state,allow_nan=False).encode();self.send_response(503 if self.path=='/health' and not skill.healthy() else 200)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def log_message(self,*args):pass
    try:ThreadingHTTPServer(('0.0.0.0',args.http_port),Handler).serve_forever()
    finally:control.stop(2)


if __name__=='__main__':main()
