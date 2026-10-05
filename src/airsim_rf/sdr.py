"""PlutoSDR-class one-way network I/Q, with explicit calibration assumptions.

Hardware limits are from ADI's published Pluto specifications. Noise figure,
input-referred ADC full scale and the filter response are configurable estimates,
not measurements of a particular board. No monostatic radar model is used.
"""
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

import numpy as np
from scipy.signal import butter, sosfilt, sosfreqz

from .receiver import BOLTZMANN, ReceiverConfig, synthesize_voltage
from .profiling import profile_range


@dataclass(frozen=True)
class PlutoSDRProfile:
    carrier_hz: float = 915e6
    sample_rate_hz: float = 2e6
    rf_bandwidth_hz: float = 1e6
    noise_figure_db: float = 10.0
    input_full_scale_dbm: float = -30.0
    temperature_k: float = 290.0
    impedance_ohm: float = 50.0
    noise_enabled: bool = True

    def __post_init__(self):
        for name, low, high in (("carrier_hz", 325e6, 3.8e9),
                                ("sample_rate_hz", 65100., 61.44e6),
                                ("rf_bandwidth_hz", 200e3, 20e6)):
            value = getattr(self, name)
            if not np.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} outside published Pluto range [{low}, {high}]")
        if self.rf_bandwidth_hz >= self.sample_rate_hz:
            raise ValueError("This filter model requires RF bandwidth below sample rate")
        for name in ("noise_figure_db", "temperature_k"):
            if not np.isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not np.isfinite(self.input_full_scale_dbm):
            raise ValueError("input_full_scale_dbm must be finite")
        if not np.isfinite(self.impedance_ohm) or self.impedance_ohm <= 0:
            raise ValueError("impedance_ohm must be positive")
        if not isinstance(self.noise_enabled, bool):
            raise ValueError("noise_enabled must be a boolean")

    @property
    def adc_bits(self):
        return 12


@dataclass(frozen=True)
class RadioClock:
    """One reference error drives both LO and sample clock; phase is independent.

    Errors are chosen per radio, not inferred from an ideal shared sim clock.
    Constant error/phase omits phase-noise spectra, thermal drift and start jitter.
    """
    error_ppm: float = 0.0
    phase_rad: float = 0.0

    def __post_init__(self):
        if not np.isfinite(self.error_ppm) or abs(self.error_ppm) > 1000:
            raise ValueError("error_ppm must be finite and within +/-1000")
        if not np.isfinite(self.phase_rad):
            raise ValueError("phase_rad must be finite")

    @property
    def rate_scale(self):
        return 1 + self.error_ppm * 1e-6


@dataclass(frozen=True)
class SDREmitter:
    waveform: Callable[[np.ndarray], np.ndarray]
    transmit_power_w: float = 1e-3
    clock: RadioClock = RadioClock()
    baseband_frequency_bounds_hz: tuple[float, float] = (-250e3, 250e3)

    def __post_init__(self):
        if not callable(self.waveform):
            raise ValueError("waveform must be callable")
        if not np.isfinite(self.transmit_power_w) or self.transmit_power_w < 0:
            raise ValueError("transmit_power_w must be finite and nonnegative")
        bounds = np.asarray(self.baseband_frequency_bounds_hz, dtype=float)
        if bounds.shape != (2,) or not np.isfinite(bounds).all() or bounds[0] > bounds[1]:
            raise ValueError("Declare finite increasing waveform frequency bounds")

    def rf_envelope(self, carrier_hz):
        # Apply DAC timing error to the waveform before the channel delay. The
        # LO offset is also applied before propagation, so its delay phase is kept.
        offset = carrier_hz * self.clock.error_ppm * 1e-6
        def waveform(t):
            return self.waveform(t * self.clock.rate_scale) * np.exp(
                1j * (2*np.pi*offset*t + self.clock.phase_rad))
        return waveform


def quantize_iq(iq_volts, *, full_scale_dbm, impedance_ohm=50., bits=12):
    """Ideal signed ADC I/Q; volts are referred to the RF input, not ADC pins.

    Full scale means a complex sinusoid of magnitude sqrt(R*Pfs). Each real
    component clips independently. Smaller-bit controls do not model another SDR.
    """
    if isinstance(bits, bool) or not isinstance(bits, int) or not 2 <= bits <= 16:
        raise ValueError("ADC bits must be an integer from 2 to 16")
    if not np.isfinite(full_scale_dbm) or not np.isfinite(impedance_ohm) or impedance_ohm <= 0:
        raise ValueError("Finite full scale and positive impedance required")
    iq = np.asarray(iq_volts)
    if iq.ndim != 1 or not np.isfinite(iq).all():
        raise ValueError("I/Q must be a finite one-dimensional array")
    full_scale = np.sqrt(impedance_ohm * 1e-3 * 10**(full_scale_dbm/10))
    if not np.isfinite(full_scale) or full_scale <= 0:
        raise ValueError("Full scale is not representable")
    half_range = 2**(bits-1)
    volts_per_count = full_scale / half_range
    components = np.column_stack((iq.real, iq.imag)) / volts_per_count
    rounded = np.rint(components)
    clipped_fraction = float(np.mean((rounded < -half_range) | (rounded > half_range-1)))
    codes = np.clip(rounded, -half_range, half_range-1).astype(np.int16)
    reconstructed = (codes[:, 0].astype(float) + 1j*codes[:, 1]) * volts_per_count
    return codes, reconstructed.astype(np.complex64), volts_per_count, clipped_fraction


@dataclass(frozen=True)
class SDRCapture:
    input_iq_volts: np.ndarray
    adc_iq_volts: np.ndarray
    adc_codes: np.ndarray
    sim_time_ns: int
    sample_rate_hz: float
    actual_sample_rate_hz: float
    volts_per_count: float
    clipped_component_fraction: float
    link_power_w: dict[str, float]
    thermal_noise_power_w: float
    noise_bandwidth_hz: float
    retained_paths: dict[str, int]


class SDRNetworkReceiver:
    """Trace all one-way links once, sum emitters before receiver noise/ADC.

    One antenna per device. Every receiver can observe all emitters. The caller
    updates scene poses at capture epochs; channels are frozen within a block.
    This reusable capture API is not yet a distributed-worker protocol or a
    live hardware driver. Caller waveforms use absolute time and unit power.
    """
    def __init__(self, scene, emitters: dict[str, SDREmitter],
                 profile=PlutoSDRProfile(), *, clocks=None, path_solver="first-order-scattering",
                 max_depth=1, samples_per_link=1028, seed=42, renderer="numpy",
                 path_tile=128, sample_tile=32, accumulation="partial",
                 replay=True, max_render_lanes=1_000_000, link_diagnostics=True,
                 batch_reduction="auto", continuous=False, max_delay_s=100e-6,
                 max_doppler_hz=2500., block_samples=2048, fft_workers=2):
        if not emitters or set(emitters) != set(scene.transmitters):
            raise ValueError("Supply one emitter for every scene transmitter")
        if not scene.receivers:
            raise ValueError("Scene needs at least one receiver")
        if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth not in (0, 1):
            raise ValueError("At most one surface interaction is supported")
        if isinstance(samples_per_link, bool) or not isinstance(samples_per_link, int) or samples_per_link < 2:
            raise ValueError("At least two attempted samples per link required")
        if renderer not in ("numpy", "direct-llvm", "direct-cuda", "batched-llvm", "batched-cuda", "basis-cpu", "basis-cuda"):
            raise ValueError("Unknown renderer")
        if accumulation not in ("partial", "local"):
            raise ValueError("accumulation must be partial or local")
        self.accumulation = accumulation
        if renderer != "numpy":
            from .rendering import ToneWaveform, LFMChirpWaveform
            from .sampled_waveform import SampledWaveform
            if renderer.startswith('basis-'):
                allowed = (SampledWaveform,)
            elif renderer.startswith('batched-'):
                allowed = (ToneWaveform, LFMChirpWaveform, SampledWaveform)
            else:
                allowed = (ToneWaveform, LFMChirpWaveform)
            if any(not isinstance(e.waveform, allowed) for e in emitters.values()):
                raise TypeError("Renderer requires supported waveform descriptors for every emitter")
        for size in (path_tile, sample_tile):
            if isinstance(size, bool) or not isinstance(size, int) or size < 1:
                raise ValueError("Tile sizes must be positive integers")
        self.renderer, self.path_tile, self.sample_tile = renderer, path_tile, sample_tile
        if not isinstance(link_diagnostics, bool):
            raise ValueError("link_diagnostics must be boolean")
        self.link_diagnostics = link_diagnostics
        self.batched_renderer = None
        if renderer.startswith("batched-"):
            from .batched_rendering import BatchedPathRenderer
            self.batched_renderer = BatchedPathRenderer(backend=renderer.removeprefix("batched-"),
                path_tile=path_tile, sample_tile=sample_tile, replay=replay, max_lanes=max_render_lanes,
                reduction=batch_reduction)
        self.basis_renderer = None
        if renderer.startswith("basis-"):
            if any(e.clock.error_ppm != 0 for e in emitters.values()):
                raise ValueError("Basis renderer requires equal nominal source and receiver clocks")
            options = dict(sample_rate_hz=profile.sample_rate_hz, max_delay_s=max_delay_s,
                           max_doppler_hz=max_doppler_hz, block_samples=block_samples)
            if renderer == "basis-cuda":
                from .research.doppler_basis_cuda import CudaDopplerBasisRenderer
                self.basis_renderer = CudaDopplerBasisRenderer(**options, batch_links=len(emitters), projection="warp")
            else:
                from .research.doppler_basis import DopplerBasisRenderer
                self.basis_renderer = DopplerBasisRenderer(**options, fft_workers=fft_workers)
        if not isinstance(continuous, bool):
            raise ValueError("continuous must be boolean")
        self.continuous = continuous
        self._next_time_ns = None
        self.scene, self.profile, self.seed = scene, profile, seed
        self.tx_names, self.rx_names = tuple(scene.transmitters), tuple(scene.receivers)
        self.emitters = dict(emitters)
        self.clocks = {name: RadioClock() for name in self.rx_names} if clocks is None else dict(clocks)
        if set(self.clocks) != set(self.rx_names):
            raise ValueError("Supply one clock for every scene receiver")
        if self.basis_renderer is not None and any(c.error_ppm != 0 for c in self.clocks.values()):
            raise ValueError("Basis renderer requires equal nominal source and receiver clocks")
        if self.continuous and len({c.rate_scale for c in self.clocks.values()}) != 1:
            raise ValueError("Continuous multi-receiver capture requires equal sample rates")
        # The filter approximation is only valid for inputs already inside the
        # ADC Nyquist interval. Do not silently alias an out-of-band blocker.
        for clock in self.clocks.values():
            for emitter in self.emitters.values():
                edges = np.asarray(emitter.baseband_frequency_bounds_hz)*emitter.clock.rate_scale
                edges += profile.carrier_hz*(emitter.clock.error_ppm-clock.error_ppm)*1e-6
                if np.max(np.abs(edges)) >= profile.sample_rate_hz*clock.rate_scale/2:
                    raise ValueError("Waveform plus LO error exceeds receiver Nyquist; oversampling is required")
        scene.frequency = profile.carrier_hz
        self.max_depth, self.samples_per_link = max_depth, samples_per_link
        if path_solver == "first-order-scattering":
            from .scattering import FirstOrderScatteringPathSolver
            self.solver = FirstOrderScatteringPathSolver()
        elif path_solver == "single-bounce":
            from .single_bounce import SingleBouncePathSolver
            self.solver = SingleBouncePathSolver()
        else:
            raise ValueError("Use first-order-scattering or single-bounce")
        self.diffuse = path_solver == "first-order-scattering" and max_depth == 1
        self.planes = self.solver.specular_plane_count(scene) if max_depth else 0
        # This is a chosen receive-chain approximation, not an AD9363 circuit fit.
        self.sos = butter(4, profile.rf_bandwidth_hz/2, fs=profile.sample_rate_hz, output="sos")
        _, response = sosfreqz(self.sos, worN=32768)
        self.noise_bandwidth_fraction = float(np.mean(np.abs(response)**2))
        self.rngs = {name: np.random.default_rng(child) for name, child in
                     zip(self.rx_names, np.random.SeedSequence(seed).spawn(len(self.rx_names)))}
        self.filter_states = {name: np.zeros((len(self.sos), 2), dtype=np.complex128) for name in self.rx_names}
        self.last_receiver_ms = 0.
        self.last_channel_ms = 0.
        self.last_render_ms = 0.
        self.last_render_metrics = []

    def capture(self, sim_time_ns: int, *, num_samples=4096):
        if isinstance(num_samples, bool) or not isinstance(num_samples, int) or num_samples < 1:
            raise ValueError("num_samples must be a positive integer")
        if isinstance(sim_time_ns, bool) or not isinstance(sim_time_ns, int):
            raise ValueError("sim_time_ns must be an integer")
        if tuple(self.scene.transmitters) != self.tx_names or tuple(self.scene.receivers) != self.rx_names:
            raise ValueError("Devices changed after receiver construction")
        if self.continuous and self._next_time_ns is not None and abs(sim_time_ns-self._next_time_ns) > .51:
            raise ValueError("Continuous capture requires consecutive sample-aligned windows")
        start = perf_counter()
        with profile_range("rf.channel"):
            with profile_range("rf.channel.solve"):
                paths = self.solver(self.scene, max_depth=self.max_depth, seed=self.seed,
                          diffuse_reflection=self.diffuse, refraction=False,
                          samples_per_src=self.samples_per_link,
                          max_num_paths_per_src=len(self.rx_names)*(1+self.planes+self.samples_per_link))
            with profile_range("rf.channel.export"):
                a, tau = paths.cir(num_time_steps=1, normalize_delays=False, out_type="numpy")
                if a.shape[:4] != (len(self.rx_names), 1, len(self.tx_names), 1):
                    raise ValueError("One antenna per transmitter and receiver required")
                a = a[:, 0, :, 0, :, 0]
                if tau.ndim == 5:
                    tau = tau[:, 0, :, 0, :]
                doppler = paths.doppler.numpy()
        self.last_channel_ms = 1000*(perf_counter()-start)
        captures = {}
        self.last_render_ms = 0.
        self.last_render_metrics = []
        warmup = 0 if self.continuous else 256
        self.last_receiver_ms = 0.
        for ri, rx_name in enumerate(self.rx_names):
            clock = self.clocks[rx_name]
            actual_rate = self.profile.sample_rate_hz * clock.rate_scale
            warmup_ns = sim_time_ns - round(warmup/actual_rate * 1e9)
            delta_epoch = (warmup_ns-sim_time_ns)*1e-9
            relative_time = np.arange(num_samples+warmup)/actual_rate
            true_time = warmup_ns*1e-9 + relative_time
            lo = np.exp(-1j*(2*np.pi*self.profile.carrier_hz*clock.error_ppm*1e-6*true_time
                             + clock.phase_rad))
            total = np.zeros(num_samples+warmup, dtype=np.complex128)
            link_power, retained = {}, {}
            batched_signals = None
            if self.batched_renderer is not None or self.basis_renderer is not None:
                from .batched_rendering import PathRenderJob
                jobs = [PathRenderJob(a[ri, ti], tau[ri, ti], doppler[ri, ti], emitter.waveform,
                            amplitude_scale=np.sqrt(self.profile.impedance_ohm*emitter.transmit_power_w),
                            time_scale=emitter.clock.rate_scale,
                            frequency_offset_hz=self.profile.carrier_hz*emitter.clock.error_ppm*1e-6,
                            phase_offset_rad=emitter.clock.phase_rad)
                        for ti, emitter in enumerate(self.emitters[name] for name in self.tx_names)]
                if self.basis_renderer is not None:
                    from .sampled_waveform import SampledWaveform
                    # Every directed link pays for a private sampled source allocation.
                    # Sionna pads absent paths with delay -1. Remove only padding;
                    # every physical path, including zero-gain paths, is retained.
                    jobs = [PathRenderJob(j.coefficients[j.delays_s >= 0], j.delays_s[j.delays_s >= 0],
                                j.doppler_hz[j.delays_s >= 0], SampledWaveform(j.waveform.samples, j.waveform.sample_rate_hz,
                                    j.waveform.reference_time_ns, j.waveform.interpolation_taps, j.waveform.boundary),
                                amplitude_scale=j.amplitude_scale, frequency_offset_hz=j.frequency_offset_hz,
                                phase_offset_rad=j.phase_offset_rad) for j in jobs]
                with profile_range("rf.iq.waveforms"):
                    render_start = perf_counter()
                    if self.basis_renderer is not None:
                        if self.renderer == "basis-cuda":
                            batched_signals = self.basis_renderer.render(jobs, num_samples=num_samples+warmup,
                                sim_time_ns=warmup_ns, channel_epoch_ns=sim_time_ns, sum_output=not self.link_diagnostics)
                        else:
                            batched_signals = self.basis_renderer.render(jobs, num_samples=num_samples+warmup,
                                sim_time_ns=warmup_ns, channel_epoch_ns=sim_time_ns)
                            if not self.link_diagnostics:
                                batched_signals = batched_signals.sum(axis=0)
                        self.last_render_metrics.append(dict(self.basis_renderer.last_metrics))
                    else:
                        batched_signals = self.batched_renderer.render(jobs, sample_rate_hz=actual_rate,
                            num_samples=num_samples+warmup, sim_time_ns=warmup_ns,
                            channel_epoch_ns=sim_time_ns, sum_output=not self.link_diagnostics)
                    self.last_render_ms += 1000*(perf_counter()-render_start)
                    if self.batched_renderer is not None:
                        self.last_render_metrics.append(dict(self.batched_renderer.last_metrics))
                if not self.link_diagnostics:
                    total = batched_signals*lo
            for ti, tx_name in enumerate(self.tx_names):
                emitter = self.emitters[tx_name]
                if batched_signals is not None:
                    retained[tx_name] = int(np.sum(tau[ri, ti] >= 0))
                    if not self.link_diagnostics:
                        continue
                    signal = batched_signals[ti]*lo
                    total += signal
                else:
                    config = ReceiverConfig(carrier_hz=self.profile.carrier_hz, sample_rate_hz=actual_rate,
                             num_samples=num_samples+warmup, transmit_power_w=emitter.transmit_power_w,
                             impedance_ohm=self.profile.impedance_ohm, noise_enabled=False)
                    with profile_range("rf.iq.waveforms"):
                        render_start = perf_counter()
                        if self.renderer == "numpy":
                            epoch_gain = a[ri, ti] * np.exp(2j*np.pi*doppler[ri, ti]*delta_epoch)
                            signal = synthesize_voltage(epoch_gain, tau[ri, ti],
                                emitter.rf_envelope(self.profile.carrier_hz), sim_time_ns=warmup_ns,
                                config=config, doppler_hz=doppler[ri, ti]).iq_volts * lo
                        else:
                            from .rendering import render_paths
                            signal = render_paths(a[ri, ti], tau[ri, ti], doppler[ri, ti],
                                emitter.waveform, sim_time_ns=warmup_ns, channel_epoch_ns=sim_time_ns,
                                sample_rate_hz=actual_rate, num_samples=num_samples+warmup,
                                amplitude_scale=np.sqrt(self.profile.impedance_ohm*emitter.transmit_power_w),
                                time_scale=emitter.clock.rate_scale,
                                frequency_offset_hz=self.profile.carrier_hz*emitter.clock.error_ppm*1e-6,
                                phase_offset_rad=emitter.clock.phase_rad,
                                backend=self.renderer.removeprefix("direct-"),
                                path_tile=self.path_tile, sample_tile=self.sample_tile,
                                accumulation=self.accumulation) * lo
                        self.last_render_ms += 1000*(perf_counter()-render_start)
                        total += signal
                retained[tx_name] = int(np.sum(tau[ri, ti] >= 0))
                if not self.link_diagnostics:
                    continue
                with profile_range("rf.iq.link_diagnostics"):
                    filtered_link = sosfilt(self.sos, signal)[warmup:]
                    link_power[tx_name] = float(np.mean(np.abs(filtered_link)**2)/self.profile.impedance_ohm)
            receiver_started = perf_counter()
            with profile_range("rf.receiver.noise_filter_adc"):
                noise_bandwidth = actual_rate * self.noise_bandwidth_fraction
                noise_power = BOLTZMANN * self.profile.temperature_k * noise_bandwidth * 10**(self.profile.noise_figure_db/10)
                if self.profile.noise_enabled:
                    rng = self.rngs[rx_name]
                    variance = self.profile.impedance_ohm * BOLTZMANN * self.profile.temperature_k * actual_rate * 10**(self.profile.noise_figure_db/10)
                    total += np.sqrt(variance/2)*(rng.standard_normal(total.size)+1j*rng.standard_normal(total.size))
                else:
                    noise_power = 0.
                if self.continuous:
                    filtered, self.filter_states[rx_name] = sosfilt(self.sos, total, zi=self.filter_states[rx_name])
                    analog = filtered.astype(np.complex64)
                else:
                    analog = sosfilt(self.sos, total)[warmup:].astype(np.complex64)
                codes, digital, step, clipping = quantize_iq(analog,
                        full_scale_dbm=self.profile.input_full_scale_dbm,
                        impedance_ohm=self.profile.impedance_ohm, bits=self.profile.adc_bits)
                captures[rx_name] = SDRCapture(analog, digital, codes, sim_time_ns,
                        self.profile.sample_rate_hz, actual_rate, step, clipping, link_power,
                        float(noise_power), noise_bandwidth, retained)
            self.last_receiver_ms += 1000*(perf_counter()-receiver_started)
        if self.continuous:
            self._next_time_ns = sim_time_ns+round(num_samples/(self.profile.sample_rate_hz*self.clocks[self.rx_names[0]].rate_scale)*1e9)
        return captures
