"""Distance2GoL-inspired FMCW receiver, with published specs and explicit estimates."""
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
from functools import cached_property
from numbers import Integral

import numpy as np
from scipy.signal import butter, freqs_zpk, sosfilt
from scipy.spatial.transform import Rotation

from .radar import C, PointTarget
from .receiver import BOLTZMANN


@dataclass(frozen=True)
class Distance2GoLProfile:
    # AN615 rev 1.10 Tables 1/4 and Figure 11.
    carrier_hz: float = 24.125e9
    bandwidth_hz: float = 200e6
    chirp_duration_s: float = 1.5e-3
    mmic_power_dbm: float = 6.0
    tx_feed_loss_db: float = 2.0
    antenna_gain_dbi: float = 10.0
    azimuth_beamwidth_deg: float = 80.0
    elevation_beamwidth_deg: float = 29.0
    if_gain_db: float = 57.0
    if_low_hz: float = 7000.0
    if_high_hz: float = 15000.0
    adc_bias_v: float = 1.65
    # Modeling choices, not claimed vendor firmware defaults/calibration.
    sample_rate_hz: float = 100e3
    num_samples: int = 128
    adc_start_s: float = 100e-6
    pri_s: float = 5e-3  # A timing example in AN615 Table 6, not a firmware default.
    adc_bits: int = 12
    adc_full_scale_v: float = 3.3
    mixer_voltage_gain_db: float = 0.0
    reference_impedance_ohm: float = 50.0
    noise_figure_db: float = 12.0
    temperature_k: float = 290.0
    noise_enabled: bool = True
    noise_power_offset_db: float = 0.0  # Demonstration control: 0 retains modeled kTB*F power.

    def __post_init__(self):
        positive = ("carrier_hz", "bandwidth_hz", "chirp_duration_s", "sample_rate_hz", "pri_s",
                    "azimuth_beamwidth_deg", "elevation_beamwidth_deg", "adc_full_scale_v",
                    "reference_impedance_ohm", "if_low_hz", "if_high_hz")
        for name in positive:
            if not np.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("mmic_power_dbm", "tx_feed_loss_db", "antenna_gain_dbi", "if_gain_db",
                     "mixer_voltage_gain_db", "adc_bias_v", "adc_start_s", "noise_figure_db", "temperature_k"):
            if not np.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        if not isinstance(self.num_samples, int) or isinstance(self.num_samples, bool) or self.num_samples < 2:
            raise ValueError("num_samples must be an integer >= 2")
        if not isinstance(self.adc_bits, int) or isinstance(self.adc_bits, bool) or not 2 <= self.adc_bits <= 16:
            raise ValueError("adc_bits must be an integer from 2 to 16")
        if self.adc_start_s < 0 or self.adc_start_s + self.num_samples/self.sample_rate_hz > self.chirp_duration_s:
            raise ValueError("ADC window must fit within the FMCW ramp")
        if self.pri_s < self.chirp_duration_s:
            raise ValueError("PRI cannot be shorter than the ramp")
        if not 0 < self.if_low_hz < self.if_high_hz < self.sample_rate_hz/2:
            raise ValueError("IF passband must be below the ADC Nyquist frequency")
        if not 0 <= self.adc_bias_v <= self.adc_full_scale_v:
            raise ValueError("ADC bias must be within full scale")
        if not np.isfinite(self.noise_power_offset_db) or not -120<=self.noise_power_offset_db<=60:
            raise ValueError('noise_power_offset_db must be finite and in [-120, 60] dB')
        if self.temperature_k < 0 or self.noise_figure_db < 0:
            raise ValueError("Temperature and noise figure must be nonnegative")

    @property
    def slope_hz_s(self):
        return self.bandwidth_hz / self.chirp_duration_s

    @property
    def tx_power_w(self):
        return 1e-3 * 10**((self.mmic_power_dbm-self.tx_feed_loss_db)/10)

    @property
    def eirp_dbm(self):
        return self.mmic_power_dbm - self.tx_feed_loss_db + self.antenna_gain_dbi

    @property
    def nominal_range_resolution_m(self):
        return C/(2*self.bandwidth_hz)

    @property
    def sampled_range_resolution_m(self):
        return C/(2*self.slope_hz_s*(self.num_samples/self.sample_rate_hz))

    def filter_sos(self):
        # Approximation to Fig. 11: a 4th-order bandpass, not the exact circuit.
        return butter(2, [self.if_low_hz, self.if_high_hz], btype="bandpass",
                      fs=self.sample_rate_hz, output="sos")

    @cached_property
    def _analog_filter(self):
        return butter(2,2*np.pi*np.array([self.if_low_hz,self.if_high_hz]),btype="bandpass",analog=True,output="zpk")

    def filter_response(self, frequency_hz):
        z,poles,gain=self._analog_filter
        return freqs_zpk(z, poles, gain, worN=2*np.pi*np.atleast_1d(frequency_hz))[1]

    def antenna_power_gain(self, direction_world, orientation_rad=(0, 0, 0)):
        direction=Rotation.from_euler("ZYX",orientation_rad).inv().apply(np.asarray(direction_world))
        az=np.degrees(np.arctan2(direction[...,1],direction[...,0]))
        el=np.degrees(np.arctan2(direction[...,2],np.hypot(direction[...,0],direction[...,1])))
        power=np.exp(-4*np.log(2)*((az/self.azimuth_beamwidth_deg)**2+(el/self.elevation_beamwidth_deg)**2))
        return np.where(direction[...,0]>0,10**(self.antenna_gain_dbi/10)*power,0.)


@dataclass(frozen=True)
class IWR1843Profile(Distance2GoLProfile):
    """TI IWR1843BOOST-inspired 77 GHz mode; not a measured board calibration.

    TI publishes 76..81 GHz, 12 dBm TX and up to 25 MS/s ADC. The ramp,
    gain/noise/ADC transfer and Gaussian beam are explicit simulation settings.
    See scenarios/mmwave-radar/README.md for sources and limitations.
    """
    carrier_hz: float = 77e9
    bandwidth_hz: float = 50e6
    chirp_duration_s: float = 32e-6
    sample_rate_hz: float = 10e6
    num_samples: int = 256
    adc_start_s: float = 3e-6
    pri_s: float = 40e-6
    mmic_power_dbm: float = 12.
    tx_feed_loss_db: float = 0.
    antenna_gain_dbi: float = 7.
    azimuth_beamwidth_deg: float = 56.
    elevation_beamwidth_deg: float = 28.
    if_gain_db: float = 60.
    if_low_hz: float = 30000.
    if_high_hz: float = 4.5e6
    adc_full_scale_v: float = 1.
    adc_bias_v: float = .5
    noise_figure_db: float = 15.

    def __post_init__(self):
        super().__post_init__()
        if not 76e9<=self.carrier_hz<=81e9 or self.sample_rate_hz>25e6 or self.bandwidth_hz>4e9:
            raise ValueError('Profile exceeds published IWR1843 carrier, ADC or sweep limits')


def quantize_iq(if_volts, profile):
    """Two unsigned ADC channels with a common DC bias and hard clipping."""
    signal = np.asarray(if_volts)
    analog = np.stack([signal.real, signal.imag], axis=-1) + profile.adc_bias_v
    clipped = (analog < 0) | (analog > profile.adc_full_scale_v)
    levels = 2**profile.adc_bits - 1
    codes = np.rint(np.clip(analog/profile.adc_full_scale_v, 0, 1)*levels).astype(np.uint16)
    reconstructed = codes.astype(float)*profile.adc_full_scale_v/levels-profile.adc_bias_v
    iq = (reconstructed[..., 0]+1j*reconstructed[..., 1]).astype(np.complex64)
    return codes, iq, int(np.count_nonzero(clipped))


@dataclass(frozen=True)
class FMCWCapture:
    if_volts: np.ndarray                 # AC complex analog IF, before ADC bias/quantization.
    adc_codes: np.ndarray                # [samples, 2] unsigned I and Q.
    adc_iq_volts: np.ndarray             # Bias-subtracted reconstructed ADC volts.
    sim_time_ns: int
    profile: Distance2GoLProfile
    target_names: tuple[str, ...]
    target_ranges_m: np.ndarray
    target_doppler_hz: np.ndarray
    target_beat_hz: np.ndarray
    target_delays_s: np.ndarray
    clipped_components: int

    def save(self, filename: str | Path):
        """Legacy observer export; acquisition never invokes this method."""
        from .observer_exports import save_fmcw
        return save_fmcw(self,filename)




@dataclass(frozen=True)
class _Transmission:
    """One emitted ramp and its frozen first-order channel, not sampled RF."""
    start_ns: int
    profile: Distance2GoLProfile
    distance: np.ndarray
    doppler: np.ndarray
    rcs: np.ndarray
    gain: np.ndarray
    weights: np.ndarray
    is_target: np.ndarray

    def select(self, mask):
        return replace(self, **{name: getattr(self, name)[mask]
            for name in ('distance', 'doppler', 'rcs', 'gain', 'weights', 'is_target')})


class FMCWRadar:
    """One first-order echo per visible scatterer; no target-leg multipath.

    Point-target RCS and optional area-normalized terrain sigma0 supply echo
    strength. Sionna's shared Mitsuba mesh supplies direct visibility on CPU or
    CUDA. IF convention is TX * conjugate(RX), so positive range rate is receding.
    Timestamped transmissions survive chirp/capture boundaries until their last
    delayed sample has passed. Call reset_history() before an independent run.
    """
    def __init__(self,profile=Distance2GoLProfile(),*,rf_scene=None,seed=42,max_depth=0,
                 max_range_m=float('inf'),clutter=None,samples_per_link=None):
        from sionna.rt import load_scene
        from .radar_scattering import TerrainBackscatter
        if max_depth!=0:raise ValueError('First-order radar does not support target-leg multipath; max_depth must be 0')
        if np.isnan(max_range_m) or max_range_m<=0:raise ValueError('Radar maximum range must be positive')
        self.profile=profile;self.scene=rf_scene if hasattr(rf_scene,'mi_scene') else load_scene(rf_scene)
        self.scene.frequency=profile.carrier_hz;self.max_range_m=max_range_m
        if clutter and clutter['enabled'] and (isinstance(samples_per_link,bool) or not isinstance(samples_per_link,int) or samples_per_link<1):raise ValueError('Enabled surface scattering requires propagation samples_per_link')
        self.clutter=TerrainBackscatter(self.scene,clutter,samples_per_link=samples_per_link) if clutter and clutter['enabled'] else None
        self.last_path_diagnostics={};self.last_clutter_diagnostics={};self.last_render_diagnostics={}
        self.rng=np.random.default_rng(seed);self.seed=seed;self._noise_sos=profile.filter_sos()
        self.reset_history()

    def reset_history(self):
        """Begin an independent transmission timeline; do not reseed noise."""
        self._transmissions=[]
        self._last_capture_ns=None
        self.last_render_diagnostics={}

    def _expire_transmissions(self, timestamp_ns, offset_s):
        retained=[]
        for transmission in self._transmissions:
            elapsed=(timestamp_ns-transmission.start_ns)*1e-9+offset_s
            keep=elapsed < transmission.profile.chirp_duration_s+2*transmission.distance/C
            if np.any(keep):
                retained.append(transmission if np.all(keep) else transmission.select(keep))
        self._transmissions=retained

    def _render_echoes(self,distance,doppler,rcs,gain,weights,*,elapsed_s=0.,transmit_profile=None):
        """Mix an earlier ramp against the current LO; never fold its delay by PRI.

        Equal ramp shapes give an exact analytic dechirped tone on the overlap
        of the old ramp's arrival and this ADC gate. The analog IF response is
        still the existing steady-state tone approximation (no edge ringing).
        """
        p=self.profile;t=p.adc_start_s+np.arange(p.num_samples)/p.sample_rate_hz
        tx=transmit_profile or p
        voltage=np.zeros(p.num_samples,complex);delay=2*distance/C
        relative_delay=delay-elapsed_s
        beat=p.slope_hz_s*relative_delay-doppler
        scale=np.sqrt(p.reference_impedance_ohm*tx.tx_power_w)*(C/tx.carrier_hz)/((4*np.pi)**1.5)
        amplitude=scale*gain*np.sqrt(rcs)/distance**2*np.conj(weights)
        amplitude*=p.filter_response(beat)*10**((p.if_gain_db+p.mixer_voltage_gain_db)/20)
        phase=(2*np.pi*np.remainder(tx.carrier_hz*delay,1)-np.pi*p.slope_hz_s*relative_delay**2
               -np.pi*p.bandwidth_hz*relative_delay-2*np.pi*np.remainder(doppler*elapsed_s,1))
        for start in range(0,len(distance),128):
            end=start+128
            tone=np.exp(1j*(phase[start:end,None]+2*np.pi*beat[start:end,None]*t))
            # Half-open RF support, with the same sub-nanosample roundoff
            # convention as the sampled direct renderer.
            first=np.ceil((relative_delay[start:end]-p.adc_start_s)*p.sample_rate_hz-1e-9)
            last=np.ceil((relative_delay[start:end]+tx.chirp_duration_s-p.adc_start_s)*p.sample_rate_hz-1e-9)
            n=np.arange(p.num_samples)
            gate=(n>=first[:,None])&(n<last[:,None])
            voltage+=np.sum(amplitude[start:end,None]*tone*gate,axis=0)
        return voltage

    def capture(self,targets,*,position_m,velocity_m_s=(0,0,0),orientation_rad=(0,0,0),sim_time_ns=0,transmit_enabled=True):
        from .radar_scattering import segment_visibility
        p=self.profile;position=np.asarray(position_m,float);velocity=np.asarray(velocity_m_s,float);orientation=np.asarray(orientation_rad,float)
        if isinstance(sim_time_ns,bool) or not isinstance(sim_time_ns,Integral):raise ValueError('Capture timestamp must be integer nanoseconds')
        sim_time_ns=int(sim_time_ns)
        if self._last_capture_ns is not None and sim_time_ns<=self._last_capture_ns:
            raise ValueError('Capture timestamps must strictly increase; call reset_history() for an independent run')
        if not isinstance(transmit_enabled,bool):raise ValueError('transmit_enabled must be a boolean')
        for vector in (position,velocity,orientation):
            if vector.shape!=(3,) or not np.isfinite(vector).all():raise ValueError('Platform pose/velocity must be finite 3-vectors')
        targets=tuple(targets);points=np.array([t.position_m for t in targets],float).reshape(-1,3)
        delta=points-position;distance=np.linalg.norm(delta,axis=1)
        if np.any(distance<=0):raise ValueError('Point target must not coincide with radar')
        direction=delta/distance[:,None]
        speeds=np.array([t.velocity_m_s for t in targets],float).reshape(-1,3)-velocity
        doppler=-2*np.sum(speeds*direction,axis=1)*p.carrier_hz/C
        delay=2*distance/C;beat=p.slope_hz_s*delay-doppler
        gain=p.antenna_power_gain(direction,orientation) if len(targets) else np.empty(0)
        rcs=np.array([t.rcs_m2 for t in targets]);gated=distance>self.max_range_m
        eligible=(rcs>0)&(gain>0)&~gated&transmit_enabled;chosen=np.flatnonzero(eligible)
        echo_points=points[chosen];echo_rcs=rcs[chosen];echo_gain=gain[chosen]
        echo_doppler=doppler[chosen];weights=np.ones(len(chosen),complex)
        self.last_path_diagnostics={t.name:{'direct_paths':0,'reflected_paths':0,'range_gated':bool(gated[i]),
            'illuminated':bool(transmit_enabled and rcs[i]>0 and gain[i]>0)} for i,t in enumerate(targets)}
        self.last_clutter_diagnostics={'sample_count':0,'in_range':0,'front_facing':0,'visible':0,'contributing':0}
        if self.clutter and transmit_enabled:
            cp,cr,cw=self.clutter.candidates(position,self.max_range_m)
            cd=cp-position;length=np.linalg.norm(cd,axis=1);cg=p.antenna_power_gain(cd/length[:,None],orientation) if len(cp) else np.empty(0)
            keep=(cg>0)&(cr>0);cp=cp[keep];cr=cr[keep];cw=cw[keep];cg=cg[keep]
            fd=2*np.sum(velocity*(cp-position)/np.linalg.norm(cp-position,axis=1)[:,None],axis=1)*p.carrier_hz/C
            echo_points=np.concatenate((echo_points,cp));echo_rcs=np.r_[echo_rcs,cr];echo_gain=np.r_[echo_gain,cg]
            echo_doppler=np.r_[echo_doppler,fd];weights=np.r_[weights,cw]
            self.last_clutter_diagnostics=dict(self.clutter.diagnostics)
        visible=segment_visibility(self.scene,position,echo_points)
        for index,original in enumerate(chosen):self.last_path_diagnostics[targets[original].name]['direct_paths']=int(visible[index])
        self.last_clutter_diagnostics.update(visible=int(visible[len(chosen):].sum()),contributing=int(visible[len(chosen):].sum()))
        distance_echo=np.linalg.norm(echo_points[visible]-position,axis=1)
        signature=lambda profile:(profile.carrier_hz,profile.bandwidth_hz,profile.chirp_duration_s)
        if any(signature(tx.profile)!=signature(p) and np.any(
                (sim_time_ns-tx.start_ns)*1e-9+p.adc_start_s < tx.profile.chirp_duration_s+2*tx.distance/C)
                for tx in self._transmissions):
            raise ValueError('Changing the ramp/carrier while echoes are pending requires a new stream session')
        self._expire_transmissions(sim_time_ns,p.adc_start_s)
        if np.any(visible):
            self._transmissions.append(_Transmission(sim_time_ns,p,distance_echo.copy(),echo_doppler[visible].copy(),
                echo_rcs[visible].copy(),echo_gain[visible].copy(),weights[visible].copy(),
                (np.arange(len(visible))<len(chosen))[visible]))
        voltage=np.zeros(p.num_samples,complex);target_echoes=clutter_echoes=0
        last_sample=p.adc_start_s+(p.num_samples-1)/p.sample_rate_hz
        for transmission in self._transmissions:
            elapsed=(sim_time_ns-transmission.start_ns)*1e-9
            # Keep future arrivals queued without spending path-by-sample work.
            arrived=2*transmission.distance/C<=elapsed+last_sample
            if not np.any(arrived):continue
            tx=transmission if np.all(arrived) else transmission.select(arrived)
            voltage+=self._render_echoes(tx.distance,tx.doppler,tx.rcs,tx.gain,tx.weights,
                                        elapsed_s=elapsed,transmit_profile=tx.profile)
            target_echoes+=int(tx.is_target.sum());clutter_echoes+=int((~tx.is_target).sum())
        self._expire_transmissions(sim_time_ns,p.adc_start_s+p.num_samples/p.sample_rate_hz)
        self.last_render_diagnostics={'echo_terms':target_echoes+clutter_echoes,'target_echoes':target_echoes,
            'clutter_echoes':clutter_echoes,'echo_model':'first-order',
            'pending_transmissions':len(self._transmissions),
            'pending_echoes':sum(len(tx.distance) for tx in self._transmissions)}
        if p.noise_enabled:
            variance=p.reference_impedance_ohm*BOLTZMANN*p.temperature_k*p.sample_rate_hz*10**((p.noise_figure_db+p.noise_power_offset_db)/10)
            noise=np.sqrt(variance/2)*(self.rng.standard_normal(p.num_samples+1024)+1j*self.rng.standard_normal(p.num_samples+1024))
            voltage+=sosfilt(self._noise_sos,noise)[-p.num_samples:]*10**((p.if_gain_db+p.mixer_voltage_gain_db)/20)
        codes,adc_iq,clipped=quantize_iq(voltage,p)
        self._last_capture_ns=sim_time_ns
        return FMCWCapture(voltage.astype(np.complex64),codes,adc_iq,int(sim_time_ns),p,
                           tuple(t.name for t in targets),distance,doppler,beat,delay,clipped)

    def capture_frame(self, targets, *, position_m, velocity_m_s=(0, 0, 0), orientation_rad=(0, 0, 0),
                      sim_time_ns=0, num_chirps=16):
        """Offline constant-velocity frame; live AirSim stepping is caller-owned."""
        if not isinstance(num_chirps, int) or isinstance(num_chirps, bool) or num_chirps <= 0:
            raise ValueError("num_chirps must be a positive integer")
        targets = tuple(targets)
        captures = []
        for i in range(num_chirps):
            delta_time = i*self.profile.pri_s
            moving_targets = [replace(target, position_m=tuple(np.asarray(target.position_m)+
                              np.asarray(target.velocity_m_s)*delta_time)) for target in targets]
            captures.append(self.capture(moving_targets,
                position_m=np.asarray(position_m)+np.asarray(velocity_m_s)*delta_time,
                velocity_m_s=velocity_m_s, orientation_rad=orientation_rad,
                sim_time_ns=int(sim_time_ns)+round(delta_time*1e9)))
        return captures


def save_frame(captures, filename):
    """Save raw IF/ADC cubes [chirp,sample] and separate target truth metadata."""
    captures = tuple(captures)
    if not captures:
        raise ValueError("Frame must contain at least one chirp")
    p = captures[0].profile
    if any(c.profile != p for c in captures):
        raise ValueError("Frame profiles must agree")
    np.savez_compressed(filename, if_volts=np.stack([c.if_volts for c in captures]),
                        adc_codes=np.stack([c.adc_codes for c in captures]),
                        adc_iq_volts=np.stack([c.adc_iq_volts for c in captures]),
                        sim_time_ns=np.asarray([c.sim_time_ns for c in captures], dtype=np.int64),
                        profile_json=json.dumps(asdict(p)),
                        target_names=np.asarray(captures[0].target_names, dtype=str),
                        target_ranges_m=np.stack([c.target_ranges_m for c in captures]),
                        target_doppler_hz=np.stack([c.target_doppler_hz for c in captures]),
                        target_beat_hz=np.stack([c.target_beat_hz for c in captures]),
                        target_delays_s=np.stack([c.target_delays_s for c in captures]),
                        clipped_components=np.asarray([c.clipped_components for c in captures]))


def __getattr__(name):
    # Compatibility math export; not part of the acquisition path.
    if name=='range_fft':
        from .processing.radar import range_fft
        return range_fft
    raise AttributeError(name)
