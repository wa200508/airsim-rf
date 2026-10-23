"""Legacy combined diagnostic exports. Never used to generate receiver samples."""
from dataclasses import asdict
import json
import numpy as np
from .processing.radar import range_compress,range_fft

def save_radar(self,filename):
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

def save_fmcw(self,filename):
    ranges, spectrum = range_fft(self.adc_iq_volts, self.profile)
    np.savez_compressed(filename, if_volts=self.if_volts, adc_codes=self.adc_codes,
                        adc_iq_volts=self.adc_iq_volts, sim_time_ns=np.int64(self.sim_time_ns),
                        profile_json=json.dumps(asdict(self.profile)), range_m=ranges,
                        range_spectrum=spectrum, target_names=np.asarray(self.target_names, dtype=str),
                        target_ranges_m=self.target_ranges_m, target_doppler_hz=self.target_doppler_hz,
                        target_beat_hz=self.target_beat_hz, target_delays_s=self.target_delays_s,
                        clipped_components=self.clipped_components)
