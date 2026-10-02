"""Distance2GoL-inspired FMCW receiver, with published specs and explicit estimates."""
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path

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

    def filter_response(self, frequency_hz):
        z, poles, gain = butter(2, 2*np.pi*np.array([self.if_low_hz, self.if_high_hz]),
                               btype="bandpass", analog=True, output="zpk")
        return freqs_zpk(z, poles, gain, worN=2*np.pi*np.atleast_1d(frequency_hz))[1]

    def antenna_power_gain(self, direction_world, orientation_rad=(0, 0, 0)):
        direction = Rotation.from_euler("ZYX", orientation_rad).inv().apply(direction_world)
        if direction[0] <= 0:
            return 0.0
        az = np.degrees(np.arctan2(direction[1], direction[0]))
        el = np.degrees(np.arctan2(direction[2], np.hypot(direction[0], direction[1])))
        power = np.exp(-4*np.log(2)*((az/self.azimuth_beamwidth_deg)**2+(el/self.elevation_beamwidth_deg)**2))
        return 10**(self.antenna_gain_dbi/10) * power


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
        ranges, spectrum = range_fft(self.adc_iq_volts, self.profile)
        np.savez_compressed(filename, if_volts=self.if_volts, adc_codes=self.adc_codes,
                            adc_iq_volts=self.adc_iq_volts, sim_time_ns=np.int64(self.sim_time_ns),
                            profile_json=json.dumps(asdict(self.profile)), range_m=ranges,
                            range_spectrum=spectrum, target_names=np.asarray(self.target_names, dtype=str),
                            target_ranges_m=self.target_ranges_m, target_doppler_hz=self.target_doppler_hz,
                            target_beat_hz=self.target_beat_hz, target_delays_s=self.target_delays_s,
                            clipped_components=self.clipped_components)


def range_fft(iq, profile: Distance2GoLProfile, *, zero_padding=4):
    """Positive beat range FFT, Hann window; range-Doppler coupling retained."""
    iq = np.asarray(iq)
    if iq.shape != (profile.num_samples,):
        raise ValueError("Expected one ADC chirp")
    if not isinstance(zero_padding, int) or isinstance(zero_padding, bool) or zero_padding < 1:
        raise ValueError("zero_padding must be a positive integer")
    nfft = profile.num_samples*zero_padding
    window = np.hanning(profile.num_samples)
    spectrum = np.fft.fft(iq*window, n=nfft)[:nfft//2]/window.sum()
    frequencies = np.arange(spectrum.size)*profile.sample_rate_hz/nfft
    return frequencies*C/(2*profile.slope_hz_s), spectrum


class FMCWRadar:
    """One ramp per capture, Sionna LoS/blocked paths, scalar reciprocal RCS.

    IF convention is TX * conjugate(RX): f_beat = slope*tau - Doppler.
    Mixing is calculated directly at IF; a 200 MHz waveform is not sampled at
    the 100 kS/s ADC rate. Filter response assumes steady-state ramp tones.
    """

    def __init__(self, profile: Distance2GoLProfile = Distance2GoLProfile(), *, rf_scene=None, seed=42):
        from sionna.rt import PlanarArray, PathSolver, Receiver, Transmitter, load_scene
        self.profile = profile
        self.scene = load_scene(rf_scene)
        self.scene.frequency = profile.carrier_hz
        self.scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
        self.scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
        self.tx = Transmitter("fmcw_platform", position=[0, 0, 0])
        self.scene.add(self.tx)
        self.probes = []
        self.receiver_type = Receiver
        self.solver = PathSolver(deterministic=True)
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        self._noise_sos = profile.filter_sos()

    def capture(self, targets, *, position_m, velocity_m_s=(0, 0, 0), orientation_rad=(0, 0, 0), sim_time_ns=0):
        p = self.profile
        position = np.asarray(position_m, dtype=float)
        velocity = np.asarray(velocity_m_s, dtype=float)
        orientation = np.asarray(orientation_rad, dtype=float)
        for vector in (position, velocity, orientation):
            if vector.shape != (3,) or not np.all(np.isfinite(vector)):
                raise ValueError("Platform pose/velocity must be finite 3-vectors")
        targets = tuple(targets)
        self.tx.position, self.tx.velocity, self.tx.orientation = position.tolist(), velocity.tolist(), orientation.tolist()
        t = p.adc_start_s + np.arange(p.num_samples)/p.sample_rate_hz
        wavelength = C/p.carrier_hz
        voltage = np.zeros(p.num_samples, dtype=np.complex128)
        ranges, dopplers, beats, delays = [], [], [], []
        conversion = 10**((p.if_gain_db+p.mixer_voltage_gain_db)/20)
        active = []
        for target in targets:
            delta = np.asarray(target.position_m)-position
            distance = np.linalg.norm(delta)
            if distance <= 0:
                raise ValueError("Point target must not coincide with radar")
            direction = delta/distance
            doppler = -2*np.dot(np.asarray(target.velocity_m_s)-velocity, direction)/wavelength
            delay = 2*distance/C
            beat = p.slope_hz_s*delay-doppler
            ranges.append(distance); dopplers.append(doppler); beats.append(beat); delays.append(delay)
            gain = p.antenna_power_gain(direction, orientation)
            if target.rcs_m2 == 0 or gain == 0:
                continue
            active.append((target, delay, beat, gain))
        # One solver launch for all targets. Reuse receiver objects as long as
        # the target count is unchanged; NumPy outputs synchronize evaluation.
        while len(self.probes) > len(active):
            self.scene.remove(self.probes.pop().name)
        while len(self.probes) < len(active):
            probe = self.receiver_type(f"fmcw_target_probe_{len(self.probes)}", position=[1, 0, 0])
            self.scene.add(probe)
            self.probes.append(probe)
        for probe, (target, _, _, _) in zip(self.probes, active):
            probe.position = np.asarray(target.position_m, dtype=float).tolist()
            probe.velocity = np.asarray(target.velocity_m_s, dtype=float).tolist()
        if active:
            paths = self.solver(self.scene, max_depth=0, seed=self.seed)
            a, tau = paths.cir(num_time_steps=1, normalize_delays=False, out_type="numpy")
            if a.shape[:4] != (len(active), 1, 1, 1):
                raise ValueError("FMCW model requires one transmitter and one receive antenna per target")
            for rx_index, (target, delay, beat, gain) in enumerate(active):
                link_tau = tau[rx_index, 0] if tau.ndim == 3 else tau[rx_index, 0, 0, 0]
                valid = np.flatnonzero(np.isfinite(link_tau) & (link_tau >= 0))
                if valid.size > 1:
                    raise ValueError("FMCW point target model supports a single direct path")
                if not valid.size:
                    continue
                index = valid[0]
                # Sionna's carrier phase is included in this reciprocal echo.
                echo = complex(a[rx_index, 0, 0, 0, index, 0])**2 * np.sqrt(4*np.pi*target.rcs_m2)/wavelength * gain
                phase = 2*np.pi*beat*t - np.pi*p.slope_hz_s*delay**2 - np.pi*p.bandwidth_hz*delay
                response = p.filter_response(beat)[0]
                voltage += (np.sqrt(p.reference_impedance_ohm*p.tx_power_w)*np.conj(echo)
                            * np.exp(1j*phase) * response * conversion * (t >= delay))
        if p.noise_enabled:
            variance = p.reference_impedance_ohm*BOLTZMANN*p.temperature_k*p.sample_rate_hz*10**(p.noise_figure_db/10)
            # Warm up the IF filter using prior random samples to avoid start-up bias.
            noise = np.sqrt(variance/2)*(self.rng.standard_normal(p.num_samples+1024)
                                       + 1j*self.rng.standard_normal(p.num_samples+1024))
            voltage += sosfilt(self._noise_sos, noise)[-p.num_samples:]*conversion
        codes, adc_iq, clipped = quantize_iq(voltage, p)
        return FMCWCapture(voltage.astype(np.complex64), codes, adc_iq, int(sim_time_ns), p,
                           tuple(t.name for t in targets), np.asarray(ranges), np.asarray(dopplers),
                           np.asarray(beats), np.asarray(delays), clipped)

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
