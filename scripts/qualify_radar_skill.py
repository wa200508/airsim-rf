"""Exercise real radar skill TCP/HTTP/journal while source dependencies are absent."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener,ProxyHandler
import numpy as np
from airsim_rf.sample_stream import SampleStreamWriter


def main():
    for name in ('sionna','projectairsim','mitsuba','cupy','df_skill'):
        assert importlib.util.find_spec(name) is None,'Unexpected application/backend dependency: '+name
    def port():
        with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
    iq,http=port(),port()
    while http==iq:http=port()
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);config={'schema_version':1,'sample_rate_hz':10e6,'carrier_hz':77e9,
            'sites':[{'id':'sensor','channels':['rx0']}],
            'acquisition':{'type':'fmcw-dechirped','pri_s':40e-6,'adc_start_s':3e-6,'num_samples':256,'chirp_duration_s':32e-6,'bandwidth_hz':50e6}}
        (root/'receiver.json').write_text(json.dumps(config))
        process=subprocess.Popen([sys.executable,'-m','airsim_rf.skills.radar','--arrays',str(root/'receiver.json'),
            '--results-dir',str(root/'results'),'--iq-port',str(iq),'--http-port',str(http)])
        client=build_opener(ProxyHandler({}))
        def get(path):
            with client.open(f'http://127.0.0.1:{http}'+path,timeout=2) as response:return json.load(response)
        try:
            deadline=time.monotonic()+15
            while True:
                try:
                    if get('/health')['ingress_ready']:break
                except OSError:pass
                if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Radar service failed to become healthy')
                time.sleep(.02)
            fs=10e6;fc=77e9;c=299792458.;a=config['acquisition'];slope=a['bandwidth_hz']/a['chirp_duration_s'];velocity=-12.;distance=123.
            time_fast=3e-6+np.arange(256)/fs;time_slow=np.arange(100)*a['pri_s'];fd=2*velocity*fc/c
            cube=np.zeros((100,400),np.complex64)
            cube[:,30:286]=.02*np.exp(2j*np.pi*((2*distance*slope/c+fd)*time_fast[None,:]+fd*time_slow[:,None]))
            with socket.create_connection(('127.0.0.1',iq),timeout=10) as connection:
                writer=SampleStreamWriter(connection,carrier_hz=fc)
                for i in range(2):
                    writer.send_samples('rx0',cube.ravel(),timestamp_ns=i*4_000_000,sample_rate_hz=fs)
                    writer.commit_window()
                    frame=get('/frames/'+str(i*4_000_000));d=frame['radar']['detection']
                    assert d['detected'] and abs(d['range_m']-distance)<4 and abs(d['range_rate_m_s']-velocity)<1,d
                    assert frame['complete_windows']==i+1
                    assert (root/'results'/f'{i*4000000}.json').is_file()
                assert writer.finish()=={'rx0':80000}
            print(json.dumps({'status':'passed','windows':2,'actual_tcp_http_journal':True,'source_and_df_dependencies_absent':True,'detection':d}))
        finally:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':main()
