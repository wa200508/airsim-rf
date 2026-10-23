"""FMCW radio adapter control plane; no receiver skill or detector dependency.

Settings are accepted by the adapter and applied on the acquisition thread at
the next window boundary. An unconfigured radio never transmits or acquires.
"""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import threading


class RadarTransceiverControl:
    def __init__(self, profile, arrays):
        self.profile=profile;self.arrays=arrays;self.lock=threading.Lock();self.ready=threading.Event()
        self.configuration=None;self.identifier=None;self.transmit=False;self.receive=False
        self.applied_configuration_id=None;self.applied_timestamp_ns=None;self.applied_transmit=False

    def configure(self, configuration):
        c=deepcopy(configuration)
        if set(c)!={'schema_version','waveform','receiver'} or type(c['schema_version']) is not int or c['schema_version']!=1:
            raise ValueError('Transceiver configuration schema v1 required')
        tx=c['waveform'];rx=c['receiver']
        if set(tx)!={'type','carrier_hz','bandwidth_hz','chirp_duration_s','pri_s','power_dbm'} or tx['type']!='fmcw-linear-up':
            raise ValueError('Unsupported transmit waveform')
        if set(rx)!={'channel','sample_rate_hz','num_samples','adc_start_s','gain_db'}:raise ValueError('Unsupported receive configuration')
        for parameters in (tx,rx):
            for key,value in parameters.items():
                if key in ('type','channel'):continue
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Invalid numeric radio parameter: '+key)
        if not -60<=tx['power_dbm']<=12 or not 0<=rx['gain_db']<=100:raise ValueError('TX power or receiver gain exceeds adapter limits')
        if [rx['channel']]!=[n for s in self.arrays['sites'] for n in s['channels']]:raise ValueError('Unknown receiver channel')
        if (tx['carrier_hz'],rx['sample_rate_hz'])!=(self.arrays['carrier_hz'],self.arrays['sample_rate_hz']):raise ValueError('Changing carrier/sample rate requires a new stream session')
        for key in ('bandwidth_hz','chirp_duration_s','pri_s'):
            if tx[key]!=self.arrays['acquisition'][key]:raise ValueError('Waveform disagrees with stream metadata: '+key)
        for key in ('num_samples','adc_start_s'):
            if rx[key]!=self.arrays['acquisition'][key]:raise ValueError('ADC gate disagrees with stream metadata: '+key)
        p=replace(self.profile,carrier_hz=tx['carrier_hz'],bandwidth_hz=tx['bandwidth_hz'],
            chirp_duration_s=tx['chirp_duration_s'],pri_s=tx['pri_s'],mmic_power_dbm=tx['power_dbm'],
            sample_rate_hz=rx['sample_rate_hz'],num_samples=rx['num_samples'],adc_start_s=rx['adc_start_s'],if_gain_db=rx['gain_db'])
        for count in (p.pri_s*p.sample_rate_hz,p.adc_start_s*p.sample_rate_hz):
            if abs(count-round(count))>1e-6:raise ValueError('PRI/gate must align to ADC samples')
        identifier=sha256(json.dumps(c,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        with self.lock:
            if self.applied_configuration_id is not None and self.configuration!=c:
                raise ValueError('Reconfiguration requires a new stream session')
            self.profile=p;self.configuration=c;self.identifier=identifier
            return self._snapshot()

    def set_state(self, state):
        if set(state)!={'transmit','receive'} or any(type(v) is not bool for v in state.values()):raise ValueError('Boolean transmit and receive states required')
        with self.lock:
            if (state['transmit'] or state['receive']) and self.configuration is None:raise ValueError('Configure the radio before enabling TX/RX')
            self.transmit=state['transmit'];self.receive=state['receive']
            if self.receive:self.ready.set()
            else:self.ready.clear()
            return self._snapshot()

    def _snapshot(self):
        return {'schema_version':1,'configuration_id':self.identifier,'transmit':self.transmit,'receive':self.receive,
                'applied_configuration_id':self.applied_configuration_id,'applied_timestamp_ns':self.applied_timestamp_ns,
                'applied_transmit':self.applied_transmit,'application_boundary':'next acquisition window'}

    def snapshot(self):
        with self.lock:return self._snapshot()

    def begin_window(self, timestamp_ns):
        with self.lock:
            if self.configuration is None or not self.receive:raise RuntimeError('Radar receive acquisition is disabled')
            self.applied_configuration_id=self.identifier;self.applied_timestamp_ns=timestamp_ns;self.applied_transmit=self.transmit
            return self.profile,self.transmit


def serve_transceiver(control, address=('0.0.0.0',8814)):
    """Serve the neutral radio contract, shared by physical adapter implementations."""
    class Handler(BaseHTTPRequestHandler):
        def respond(self, result, status=200):
            payload=json.dumps(result,allow_nan=False).encode();self.send_response(status)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)))
            self.end_headers();self.wfile.write(payload)
        def do_GET(self):
            if self.path=='/v1/status':self.respond(control.snapshot())
            else:self.send_error(404)
        def mutate(self, operation):
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384:raise ValueError('Radio request must contain 1..16384 bytes')
                self.connection.settimeout(5)
                self.respond(operation(json.loads(self.rfile.read(length))))
            except (ValueError,KeyError,TypeError) as error:self.respond({'error':str(error)},400)
        def do_PUT(self):
            if self.path=='/v1/configuration':self.mutate(control.configure)
            else:self.send_error(404)
        def do_POST(self):
            if self.path=='/v1/state':self.mutate(control.set_state)
            else:self.send_error(404)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(address,Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server
