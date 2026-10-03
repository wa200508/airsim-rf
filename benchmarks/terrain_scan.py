"""Focused bistatic terrain experiment; actual Sionna paths and complex I/Q."""
from pathlib import Path
from math import log

import numpy as np
from scipy.signal import correlate

from airsim_rf.receiver import ReceiverConfig, synthesize_voltage
from airsim_rf.scattering import FirstOrderScatteringPathSolver

C = 299792458.


def register_scan_pattern(beamwidth_deg=12):
    """Synthetic axisymmetric Gaussian element, unit mean spherical gain."""
    import drjit as dr
    import mitsuba as mi
    from sionna.rt.antenna_pattern import PolarizedAntennaPattern, register_antenna_pattern
    if not np.isfinite(beamwidth_deg) or not 1 <= beamwidth_deg <= 90:
        raise ValueError('Beamwidth must be between 1 and 90 degrees')
    width = float(np.deg2rad(beamwidth_deg))
    nodes, weights = np.polynomial.legendre.leggauss(512)
    floor = 1e-6
    raw_gain = np.exp(-4*np.log(2)*(np.arccos(nodes)/width)**2)+floor
    peak_scale = float(4*np.pi/(2*np.pi*np.dot(weights, raw_gain)))

    def vertical(theta, phi):
        angle = dr.acos(dr.clip(dr.sin(theta)*dr.cos(phi), -1, 1))
        gain = peak_scale*(dr.exp(-4*log(2)*dr.square(angle/width))+floor)
        return mi.Complex2f(dr.sqrt(gain), 0)

    def factory(*, polarization, polarization_model='tr38901_2'):
        return PolarizedAntennaPattern(v_pattern=vertical, polarization=polarization,
                                      polarization_model=polarization_model)

    name = f'airsim_rf_scan_{beamwidth_deg:g}'
    register_antenna_pattern(name, factory)
    return name, float(10*np.log10(peak_scale*(1+floor)))


def scan_scene(name, *, beamwidth_deg=12):
    import sionna.rt as rt
    pattern, peak_gain_db = register_scan_pattern(beamwidth_deg)
    scene = rt.load_scene(str(Path(__file__).resolve().parent/'scenes'/f'{name}.xml'))
    scene.frequency = 24.125e9
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern=pattern, polarization='V')
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern=pattern, polarization='V')
    scene.add(rt.Transmitter('tx', position=[0, 0, 40], orientation=[0, np.pi/2, 0]))
    scene.add(rt.Receiver('rx', position=[2, 0, 40], orientation=[0, np.pi/2, 0]))
    return scene, peak_gain_db


def total_length_to_height(length_m, *, altitude_m=40, baseline_m=2):
    """Equivalent height assuming a scatterer below the baseline midpoint.

    Off-nadir paths also map here; this is a diagnostic coordinate, not a DEM
    inversion. The exact symmetric bistatic geometry sets the conversion.
    """
    length = np.asarray(length_m, dtype=float)
    if np.any(length < baseline_m):
        raise ValueError('Path length cannot be shorter than the baseline')
    return altitude_m-np.sqrt((length/2)**2-(baseline_m/2)**2)


class TerrainScan:
    """One moving TX/RX pair; no two-way link squaring or point-target RCS."""
    def __init__(self, scene, *, bandwidth_hz=200e6, samples_per_link=1028):
        if not np.isfinite(bandwidth_hz) or not 0 < bandwidth_hz < 500e6:
            raise ValueError('Bandwidth must be positive and below 500 MS/s')
        self.scene, self.bandwidth_hz, self.samples_per_link = scene, bandwidth_hz, samples_per_link
        self.config = ReceiverConfig(carrier_hz=24.125e9, sample_rate_hz=500e6,
                    num_samples=1500, transmit_power_w=1, impedance_ohm=50, noise_enabled=False)
        self.pulse_width_s = 2e-6
        self.solver = FirstOrderScatteringPathSolver()
        self.planes = self.solver.specular_plane_count(scene)
        self.template = self.chirp(np.arange(1000)/self.config.sample_rate_hz)
        self.length_m = np.arange(self.config.num_samples)*C/self.config.sample_rate_hz

    def chirp(self, t):
        inside = (t >= 0) & (t < self.pulse_width_s)
        u = np.where(inside, t, 0)
        phase = np.pi*self.bandwidth_hz*(u*u/self.pulse_width_s-u)
        return np.where(inside, np.exp(1j*phase), 0j)

    def capture(self, tx_position, *, velocity, epoch_s):
        tx_position = np.asarray(tx_position, dtype=float)
        self.scene.transmitters['tx'].position = tx_position.tolist()
        self.scene.receivers['rx'].position = (tx_position+[2, 0, 0]).tolist()
        velocity = np.asarray(velocity, dtype=float).tolist()
        self.scene.transmitters['tx'].velocity = velocity
        self.scene.receivers['rx'].velocity = velocity
        paths = self.solver(self.scene, samples_per_src=self.samples_per_link,
                           max_num_paths_per_src=self.samples_per_link+1+self.planes, seed=42)
        a, tau = paths.cir(num_time_steps=1, normalize_delays=False, out_type='numpy')
        a, tau, doppler = a[0, 0, 0, 0, :, 0], tau[0, 0], paths.doppler.numpy()[0, 0]
        self.last_channel = (a, tau, doppler)
        iq, compressed = self.voltage_from_channel(a, tau, doppler, epoch_s=epoch_s)
        return iq, compressed, int((tau >= 0).sum())

    def voltage_from_channel(self, a, tau, doppler, *, epoch_s):
        """Permit a bandwidth comparison using exactly the same traced paths."""
        epoch_ns = round(epoch_s*1e9)
        exact_epoch = epoch_ns*1e-9
        block = synthesize_voltage(a, tau, lambda t: self.chirp(t-exact_epoch),
                   sim_time_ns=epoch_ns, config=self.config, doppler_hz=doppler)
        compressed = correlate(block.iq_volts, self.template, mode='full', method='fft')[self.template.size-1:]
        compressed /= np.sum(np.abs(self.template)**2)
        return block.iq_volts, compressed
