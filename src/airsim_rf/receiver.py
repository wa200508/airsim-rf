"""SISO baseband voltage receiver; propagation is supplied by Sionna RT."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

BOLTZMANN = 1.380649e-23
Waveform = Callable[[np.ndarray], np.ndarray]


@dataclass(frozen=True)
class ReceiverConfig:
    carrier_hz: float = 2.4e9
    sample_rate_hz: float = 1e6
    num_samples: int = 4096
    transmit_power_w: float = 1.0
    impedance_ohm: float = 50.0
    temperature_k: float = 290.0
    noise_figure_db: float = 0.0
    noise_enabled: bool = False

    def __post_init__(self):
        for name in ("carrier_hz", "sample_rate_hz", "impedance_ohm"):
            value = getattr(self, name)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("transmit_power_w", "temperature_k", "noise_figure_db"):
            value = getattr(self, name)
            if not np.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if isinstance(self.num_samples, bool) or not isinstance(self.num_samples, int) or self.num_samples <= 0:
            raise ValueError("num_samples must be a positive integer")


@dataclass(frozen=True)
class IQBlock:
    iq_volts: np.ndarray
    sim_time_ns: int
    sample_rate_hz: float
    carrier_hz: float
    impedance_ohm: float
    path_delays_s: np.ndarray

    def save(self, filename: str | Path):
        np.savez_compressed(
            filename, iq_volts=self.iq_volts, sim_time_ns=np.int64(self.sim_time_ns),
            sample_rate_hz=self.sample_rate_hz, carrier_hz=self.carrier_hz,
            impedance_ohm=self.impedance_ohm, path_delays_s=self.path_delays_s,
        )


def synthesize_voltage(coefficients, delays_s, waveform: Waveform, *,
                       sim_time_ns: int, config: ReceiverConfig,
                       rng: np.random.Generator | None = None) -> IQBlock:
    """Apply a CIR to a unit-average-power, continuous complex waveform.

    coefficients[p,n] already include carrier-delay phase and local Doppler.
    waveform(t) is evaluated at ABSOLUTE simulation time minus path delay.
    Invalid Sionna padding paths have delay -1 and contribute nothing.
    """
    a = np.asarray(coefficients, dtype=np.complex128)
    tau = np.asarray(delays_s, dtype=np.float64)
    if a.ndim != 2 or tau.ndim != 1 or a.shape != (tau.size, config.num_samples):
        raise ValueError("Expected coefficients [paths,samples] and delays [paths]")
    valid = np.isfinite(tau) & (tau >= 0)
    a, tau = a[valid], tau[valid]
    if not np.all(np.isfinite(a)):
        raise ValueError("Nonfinite channel coefficients")
    times = sim_time_ns * 1e-9 + np.arange(config.num_samples) / config.sample_rate_hz
    iq = np.zeros(config.num_samples, dtype=np.complex128)
    # Keep memory bounded by summing one path at a time.
    for gain, delay in zip(a, tau):
        x = np.asarray(waveform(times - delay), dtype=np.complex128)
        if x.shape != times.shape or not np.all(np.isfinite(x)):
            raise ValueError("waveform must return finite complex samples with the input shape")
        iq += gain * x
    iq *= np.sqrt(config.impedance_ohm * config.transmit_power_w)
    if config.noise_enabled:
        if rng is None:
            rng = np.random.default_rng()
        # Ideal full complex Nyquist bandwidth B=fs, matched load.
        variance_v2 = (config.impedance_ohm * BOLTZMANN * config.temperature_k
                       * config.sample_rate_hz * 10 ** (config.noise_figure_db / 10))
        iq += np.sqrt(variance_v2 / 2) * (
            rng.standard_normal(iq.size) + 1j * rng.standard_normal(iq.size))
    return IQBlock(iq.astype(np.complex64), int(sim_time_ns), config.sample_rate_hz,
                   config.carrier_hz, config.impedance_ohm, tau)


class RFReceiver:
    """One transmitter, one receive antenna; explicit scene and local CIR epoch."""

    def __init__(self, scene, config: ReceiverConfig, *, max_depth=3, seed=42):
        from sionna.rt import PathSolver
        self.scene = scene
        self.config = config
        self.max_depth = max_depth
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.solver = PathSolver(deterministic=True)
        scene.frequency = config.carrier_hz

    def capture(self, waveform: Waveform, sim_time_ns: int) -> IQBlock:
        paths = self.solver(self.scene, max_depth=self.max_depth,
                            samples_per_src=10000, seed=self.seed)
        a, tau = paths.cir(sampling_frequency=self.config.sample_rate_hz,
                          num_time_steps=self.config.num_samples,
                          normalize_delays=False, out_type="numpy")
        if a.shape[:4] != (1, 1, 1, 1):
            raise ValueError("Initial receiver supports exactly one TX/RX and one antenna each")
        delays = tau[0, 0] if tau.ndim == 3 else tau[0, 0, 0, 0]
        return synthesize_voltage(a[0, 0, 0, 0], delays, waveform,
                                  sim_time_ns=sim_time_ns, config=self.config,
                                  rng=self.rng)
