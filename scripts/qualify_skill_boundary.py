"""Run inside the standalone skill image: real I/Q ingress with no simulator code."""
import argparse
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import ProxyHandler,build_opener

import numpy as np
import grpc
from airsim_rf.ams import squall_rf_pb2 as pb, squall_rf_pb2_grpc as rpc
from airsim_rf.sample_stream import SampleStreamWriter

FORBIDDEN=('sionna','mitsuba','drjit','cupy','projectairsim','airsim_rf.receiver','airsim_rf.sdr',
    'airsim_rf.dashboard_producer','airsim_rf.source_recording','airsim_rf.dashboard_recording')


def qualify():
    for name in FORBIDDEN:
        if importlib.util.find_spec(name) is not None:raise AssertionError('Skill image contains source dependency '+name)
    request=build_opener(ProxyHandler({})).open
    reservations=[socket.socket() for _ in range(3)]
    for item in reservations:item.bind(('127.0.0.1',0))
    iq,http,control=[item.getsockname()[1] for item in reservations]
    for item in reservations:item.close()
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);carrier=433e6;fs=1e6;count=8192
        offsets=(np.arange(4)-1.5)*299792458./carrier/2
        arrays={'schema_version':1,'carrier_hz':carrier,'sample_rate_hz':fs,'sites':[
            {'id':f'array{i}','channels':[f'hardware{i}_{j}' for j in range(4)],'center_rf_m':[0,i*20,0],
             'yaw_rad':0,'element_offsets_m':offsets.tolist(),'calibration_complex':[[1,0]]*4} for i in range(2)]}
        config=root/'receivers.json';config.write_text(json.dumps(arrays))
        # The app receives ONLY receiver configuration and its own output path.
        with (root/'app.log').open('w+') as log:
            process=subprocess.Popen([sys.executable,'-m','airsim_rf.skills.music','--arrays',str(config),
                '--iq-port',str(iq),'--http-port',str(http),'--control-address',f'127.0.0.1:{control}',
                '--results-dir',str(root/'results')],stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+30
                while True:
                    try:
                        with request(f'http://127.0.0.1:{http}/health',timeout=.5) as response:
                            if json.load(response)['ingress_ready']:break
                    except OSError:pass
                    if process.poll() is not None or time.monotonic()>deadline:
                        log.seek(0);raise AssertionError('Independent skill failed: '+log.read())
                    time.sleep(.05)
                rng=np.random.default_rng(444);angle=20.;phase=np.exp(2j*np.pi*carrier/299792458.*offsets*np.sin(np.deg2rad(angle)))
                with socket.create_connection(('127.0.0.1',iq),timeout=10) as connection:
                    writer=SampleStreamWriter(connection,carrier_hz=carrier)
                    epochs=[1_800_000_000_000_000_000+i*round(count/fs*1e9) for i in range(2)]
                    for epoch in epochs:
                        symbols=(rng.choice([-1.,1.],count)+1j*rng.choice([-1.,1.],count))/np.sqrt(2)
                        for site in arrays['sites']:
                            for index,name in enumerate(site['channels']):
                                values=(.001*phase[index]*symbols+1e-7*(rng.normal(size=count)+1j*rng.normal(size=count))).astype(np.complex64)
                                writer.send_samples(name,values,timestamp_ns=epoch,sample_rate_hz=fs)
                        assert writer.commit_window()==epoch
                        result=json.loads((root/'results'/f'{epoch}.json').read_text())
                        assert result['timestamp_ns']==epoch and 'sim_time_ns' not in result
                        assert all(b['detected'] and abs(b['angle_deg']-angle)<.2 for b in result['bearings'])
                        assert not any(key in result for key in ('paths','position_rf_m','waveform','truth'))
                    totals=writer.finish();assert set(totals.values())=={2*count}
                with grpc.insecure_channel(f'127.0.0.1:{control}') as channel:
                    client=rpc.SquallRfControlStub(channel)
                    status=client.GetStatus(pb.GetStatusRequest(),timeout=5)
                    assert status.rf_status.center_frequency_hz==round(carrier)
                    assert status.rf_status.sample_rate==round(fs)
                    assert status.rf_status.block_size==count
                    assert not client.TuneRf(pb.TuneRfRequest(center_frequency_hz=915_000_000),timeout=5).success
                return {'status':'passed','scope':'standalone CPU receiver image, generic source buffers, real TCP/MUSIC/result journal',
                    'source_dependencies_absent':list(FORBIDDEN),'carrier_hz':carrier,'sample_rate_hz':fs,
                    'channels':8,'windows':2,'samples_per_channel':2*count,'expected_angle_deg':angle,
                    'receiver_control_configuration_checked':True,
                    'simulator_or_truth_available':False,'physical_hardware_tested':False}
            finally:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
    report=qualify();text=json.dumps(report,indent=2)+'\n'
    if args.output:args.output.write_text(text)
    print(text)
