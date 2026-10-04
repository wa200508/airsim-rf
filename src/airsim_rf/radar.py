"""Simple reciprocal monostatic point-target radar with a pulsed LFM waveform."""
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from scipy.signal import correlate

from .receiver import IQBlock, ReceiverConfig, synthesize_voltage

C = 299792458.0


@dataclass(frozen=True)
class RadarConfig:
    carrier_hz: float = 10e9
    bandwidth_hz: float = 20e6
    sample_rate_hz: float = 50e6
    pulse_width_s: float = 1e-6
    pri_s: float = 100e-6
    peak_power_w: float = 100.0
    impedance_ohm: float = 50.0
    noise_enabled: bool = False
    temperature_k: float = 290.0
    noise_figure_db: float = 4.0
    transmit_blanking: bool = True

    def __post_init__(self):
        for name in ("bandwidth_hz", "pulse_width_s", "pri_s"):
            value = getattr(self, name)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        self.receiver_config()  # Validate shared RF parameters.
        if self.bandwidth_hz >= self.sample_rate_hz:
            raise ValueError("LFM bandwidth must be less than the complex sample rate")
        if self.pulse_width_s >= self.pri_s:
            raise ValueError("pulse width must be shorter than PRI")
        if self.pulse_width_s * self.sample_rate_hz < 2:
            raise ValueError("LFM pulse requires at least two samples")
        for duration in (self.pulse_width_s, self.pri_s):
            samples = duration * self.sample_rate_hz
            if not np.isclose(samples, round(samples), rtol=0, atol=1e-7):
                raise ValueError("pulse width and PRI must span integer sample counts")

    @property
    def num_samples(self):
        return round(self.pri_s * self.sample_rate_hz)

    @property
    def range_resolution_m(self):
        return C / (2 * self.bandwidth_hz)

    def receiver_config(self):
        return ReceiverConfig(carrier_hz=self.carrier_hz, sample_rate_hz=self.sample_rate_hz,
                              num_samples=self.num_samples, transmit_power_w=self.peak_power_w,
                              impedance_ohm=self.impedance_ohm, noise_enabled=self.noise_enabled,
                              temperature_k=self.temperature_k, noise_figure_db=self.noise_figure_db)

    def chirp(self, relative_time_s):
        """Single unit-amplitude pulse: -B/2 to +B/2; zero outside [0,T)."""
        t = np.asarray(relative_time_s, dtype=np.float64)
        inside = (t >= 0) & (t < self.pulse_width_s)
        # Reduce out-of-pulse arguments before exponentiation.
        u = np.where(inside, t, 0)
        phase = np.pi * (self.bandwidth_hz / self.pulse_width_s) * u**2 - np.pi * self.bandwidth_hz * u
        return np.where(inside, np.exp(1j * phase), 0j)

    def template(self):
        return self.chirp(np.arange(round(self.pulse_width_s * self.sample_rate_hz)) / self.sample_rate_hz)


@dataclass(frozen=True)
class PointTarget:
    name: str
    position_m: tuple[float, float, float]
    rcs_m2: float = 1.0
    velocity_m_s: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __post_init__(self):
        if not np.isfinite(self.rcs_m2) or self.rcs_m2 < 0:
            raise ValueError("RCS must be finite and nonnegative")
        for vector in (self.position_m, self.velocity_m_s):
            if np.asarray(vector).shape != (3,) or not np.all(np.isfinite(vector)):
                raise ValueError("Target position and velocity must be finite 3-vectors")


@dataclass(frozen=True)
class RadarCapture:
    block: IQBlock
    config: RadarConfig
    target_names: tuple[str, ...]
    target_ranges_m: np.ndarray
    target_rcs_m2: np.ndarray
    target_doppler_hz: np.ndarray

    def save(self, filename: str | Path):
        range_m, compressed = range_compress(self.block.iq_volts, self.config)
        np.savez_compressed(
            filename, iq_volts=self.block.iq_volts, sim_time_ns=np.int64(self.block.sim_time_ns),
            sample_rate_hz=self.config.sample_rate_hz, carrier_hz=self.config.carrier_hz,
            impedance_ohm=self.config.impedance_ohm, bandwidth_hz=self.config.bandwidth_hz,
            pulse_width_s=self.config.pulse_width_s, pri_s=self.config.pri_s,
            peak_power_w=self.config.peak_power_w, noise_enabled=self.config.noise_enabled,
            temperature_k=self.config.temperature_k, noise_figure_db=self.config.noise_figure_db,
            transmit_blanking=self.config.transmit_blanking, tx_template=self.config.template(),
            path_delays_s=self.block.path_delays_s, range_m=range_m,
            range_profile_volts=compressed, target_names=np.asarray(self.target_names, dtype=str),
            target_ranges_m=self.target_ranges_m, target_rcs_m2=self.target_rcs_m2,
            target_doppler_hz=self.target_doppler_hz,
        )


def range_compress(iq_volts, config: RadarConfig):
    """Complex matched filter, normalized by pulse energy; zero lag is 0 m."""
    iq = np.asarray(iq_volts)
    if iq.ndim != 1 or iq.size != config.num_samples:
        raise ValueError("Expected one receive window with config.num_samples samples")
    template = config.template()
    result = correlate(iq, template, mode="full", method="fft")
    # Full correlation lags start at -(len(template)-1).
    result = result[template.size - 1:] / np.sum(np.abs(template)**2)
    ranges = np.arange(result.size) * C / (2 * config.sample_rate_hz)
    return ranges, result


class PointTargetRadar:
    """LoS/blocked reciprocal paths, scalar coherent point RCS, one antenna.

    Uses a virtual receiver at each target to measure a ONE-WAY Sionna link.
    Squaring that link and scaling sqrt(4*pi*sigma)/lambda calibrates the
    two-way channel to the monostatic radar equation. This virtual radio is
    a computation endpoint, not a physical transmitter in the environment.
    No mesh target scattering or multipath is inferred from the radio solver.
    """

    def __init__(self, config: RadarConfig = RadarConfig(), *, rf_scene=None, seed=42, renderer="numpy"):
        from sionna.rt import PlanarArray, PathSolver, Receiver, Transmitter, load_scene
        self.config = config
        self.renderer = renderer
        self.scene = load_scene(rf_scene)
        self.scene.frequency = config.carrier_hz
        self.scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
        self.scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
        self.tx = Transmitter("radar_platform", position=[0, 0, 0])
        self.probe = Receiver("radar_target_probe", position=[1, 0, 0])
        self.scene.add(self.tx)
        self.scene.add(self.probe)
        self.solver = PathSolver(deterministic=True)
        self.rng = np.random.default_rng(seed)
        self.seed = seed

    def capture(self, targets, *, position_m, velocity_m_s=(0, 0, 0),
                orientation_rad=(0, 0, 0), sim_time_ns=0) -> RadarCapture:
        cfg = self.config
        position, velocity = np.asarray(position_m, dtype=float), np.asarray(velocity_m_s, dtype=float)
        orientation = np.asarray(orientation_rad, dtype=float)
        for vector in (position, velocity, orientation):
            if vector.shape != (3,) or not np.all(np.isfinite(vector)):
                raise ValueError("Platform position, velocity, and orientation must be finite 3-vectors")
        targets = tuple(targets)
        self.tx.position = position.tolist()
        self.tx.velocity = velocity.tolist()
        self.tx.orientation = orientation.tolist()
        coefficients, delays, path_dopplers = [], [], []
        ranges, dopplers = [], []
        wavelength = C / cfg.carrier_hz
        for target in targets:
            delta = np.asarray(target.position_m) - position
            distance = np.linalg.norm(delta)
            if distance <= 0:
                raise ValueError("Point target must not coincide with the radar")
            radial_speed = np.dot(np.asarray(target.velocity_m_s) - velocity, delta / distance)
            ranges.append(distance)
            dopplers.append(-2 * radial_speed / wavelength)
            if target.rcs_m2 == 0:
                continue
            self.probe.position = np.asarray(target.position_m, dtype=float).tolist()
            self.probe.velocity = np.asarray(target.velocity_m_s, dtype=float).tolist()
            paths = self.solver(self.scene, max_depth=0, seed=self.seed)
            a, tau = paths.cir(num_time_steps=1,
                              normalize_delays=False, out_type="numpy")
            if a.shape[:4] != (1, 1, 1, 1):
                raise ValueError("Radar requires exactly one transmitter and virtual receiver")
            tau = tau[0, 0] if tau.ndim == 3 else tau[0, 0, 0, 0]
            valid = np.flatnonzero(np.isfinite(tau) & (tau >= 0))
            if valid.size > 1:
                raise ValueError("Point-target model supports one direct path per target")
            for p in valid:
                coefficients.append(a[0, 0, 0, 0, p, 0]**2 * np.sqrt(4 * np.pi * target.rcs_m2) / wavelength)
                delays.append(2 * float(tau[p]))
                path_dopplers.append(2*float(paths.doppler.numpy().reshape(-1)[p]))
        channel = np.asarray(coefficients, dtype=np.complex128)
        # Pulse-relative time preserves sub-sample precision even when AirSim
        # timestamps are Unix-scale nanoseconds. Geometry supplies RF phase.
        from .rendering import LFMChirpWaveform
        waveform = cfg.chirp if self.renderer == "numpy" else LFMChirpWaveform(cfg.bandwidth_hz, cfg.pulse_width_s)
        block = synthesize_voltage(channel, delays, waveform, sim_time_ns=0,
                                   config=cfg.receiver_config(), rng=self.rng,
                                   doppler_hz=path_dopplers, renderer=self.renderer)
        iq = block.iq_volts.copy()
        if cfg.transmit_blanking:
            iq[:cfg.template().size] = 0
        block = replace(block, iq_volts=iq, sim_time_ns=int(sim_time_ns))
        return RadarCapture(block, cfg, tuple(t.name for t in targets), np.asarray(ranges),
                            np.asarray([t.rcs_m2 for t in targets]), np.asarray(dopplers))
