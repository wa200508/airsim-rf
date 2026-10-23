"""Acquisition adapter: moving monostatic FMCW radar and passive point targets.

No detection or range/Doppler FFT is performed here. Actual platform readback is
extrapolated at constant velocity only within one short RF update (4 ms).
"""
from dataclasses import replace
import numpy as np
from .fmcw import FMCWRadar,IWR1843Profile
from .radar import PointTarget
from .sdr import SDRCapture
from .bridge import mount_kinematics


class RadarWindowReceiver:
    def __init__(self,scene,radio,arrays):
        self.radio=radio;self.arrays=arrays;c=radio['radar']
        self.radar=FMCWRadar(IWR1843Profile(**c['profile']),rf_scene=scene,seed=c['seed'],max_depth=c['max_depth_per_leg'])
        self.channel=arrays['sites'][0]['channels'][0]
        self.last_path_diagnostics={};self.truth={}

    def update(self,kinematics):
        c=self.radio['radar']
        self.position,self.velocity,self.orientation=mount_kinematics(kinematics[c['platform_actor']],c['mount_body_m'])
        self.targets=[]
        for target in c['targets']:
            pos,vel,_=mount_kinematics(kinematics[target['actor']])
            self.targets.append(PointTarget(target['actor'],tuple(pos),target['rcs_m2'],tuple(vel)))
        if c['pointing']=='track-target':
            delta=np.asarray(self.targets[0].position_m)-self.position
            self.orientation=np.array([np.arctan2(delta[1],delta[0]),-np.arctan2(delta[2],np.linalg.norm(delta[:2])),0.])
        self.arrays['sites'][0]['center_rf_m']=self.position.tolist()

    def capture(self,sim_time_ns,*,num_samples):
        p=self.radar.profile;stride=round(p.pri_s*p.sample_rate_hz);start=round(p.adc_start_s*p.sample_rate_hz)
        if num_samples%stride:raise ValueError('Radar window must contain whole chirps')
        values=np.zeros(num_samples,dtype=np.complex64);analog=values.copy();clipped=0;retained=0
        for i in range(num_samples//stride):
            dt=i*p.pri_s
            targets=[replace(t,position_m=tuple(np.asarray(t.position_m)+np.asarray(t.velocity_m_s)*dt)) for t in self.targets]
            cap=self.radar.capture(targets,position_m=self.position+self.velocity*dt,velocity_m_s=self.velocity,
                                   orientation_rad=self.orientation,sim_time_ns=sim_time_ns+round(dt*1e9))
            a=i*stride+start;b=a+p.num_samples
            values[a:b]=cap.adc_iq_volts;analog[a:b]=cap.if_volts;clipped+=cap.clipped_components
            if i==0:
                self.last_path_diagnostics={self.channel:dict(self.radar.last_path_diagnostics)}
                self.truth={'target_ranges_m':cap.target_ranges_m.tolist(),'target_doppler_hz':cap.target_doppler_hz.tolist(),
                            'target_range_rates_m_s':(-cap.target_doppler_hz*299792458./(2*p.carrier_hz)).tolist()}
                retained=sum((v['direct_paths']+v['reflected_paths'])**2 for v in self.radar.last_path_diagnostics.values())
        return {self.channel:SDRCapture(analog,values,np.empty((0,2),dtype=np.uint16),sim_time_ns,p.sample_rate_hz,p.sample_rate_hz,
                                      p.adc_full_scale_v/(2**p.adc_bits-1),clipped/(2*max(1,num_samples)),{},0.,p.if_high_hz-p.if_low_hz,
                                      {'target_echoes':retained})}
