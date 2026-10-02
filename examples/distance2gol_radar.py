"""Off-the-shelf radar profile: FMCW IF/ADC I/Q cube from a slowly moving drone."""
import argparse
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks

from airsim_rf.fmcw import Distance2GoLProfile, FMCWRadar, range_fft, save_frame
from airsim_rf.radar import PointTarget


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("distance2gol_radar.npz"))
    parser.add_argument("--no-noise", action="store_true")
    parser.add_argument("--speed", type=float, default=0.3, help="Drone forward speed in m/s")
    args = parser.parse_args()
    profile = replace(Distance2GoLProfile(), noise_enabled=not args.no_noise)
    radar = FMCWRadar(profile)
    targets = [PointTarget("target_10m", (10, 0, 2), 0.1),
               PointTarget("target_14m", (14, 0, 2), 0.4)]
    captures = radar.capture_frame(targets, position_m=[0, 0, 2], velocity_m_s=[args.speed, 0, 0])
    save_frame(captures, args.output)
    first = captures[0]
    ranges, _ = range_fft(first.adc_iq_volts, profile)
    spectra = np.stack([range_fft(c.adc_iq_volts, profile)[1] for c in captures])
    power = np.mean(np.abs(spectra)**2, axis=0)
    peaks, _ = find_peaks(power, height=power.max()*0.3, distance=8)
    print(f"Saved {len(captures)} x {profile.num_samples} complex IF and ADC samples to {args.output}")
    print(f"Range FFT peaks: {np.round(ranges[peaks], 2).tolist()} m (includes Doppler coupling)")
    print(f"First-chirp true ranges: {first.target_ranges_m.tolist()} m; beats: {np.round(first.target_beat_hz, 2).tolist()} Hz")
    print(f"EIRP {profile.eirp_dbm:.1f} dBm; nominal full-sweep resolution {profile.nominal_range_resolution_m:.2f} m")
    print(f"ADC clipping: {sum(c.clipped_components for c in captures)} channel samples")
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), constrained_layout=True)
    time_ms = (profile.adc_start_s+np.arange(profile.num_samples)/profile.sample_rate_hz)*1e3
    axes[0].plot(time_ms, first.adc_iq_volts.real*1e3, label="I")
    axes[0].plot(time_ms, first.adc_iq_volts.imag*1e3, label="Q", alpha=0.75)
    axes[0].set(xlabel="Time within FMCW ramp (ms)", ylabel="Reconstructed ADC AC voltage (mV)",
                title="Distance2GoL-inspired radar: simulated ADC I/Q")
    axes[0].legend()
    level = 10*np.log10(np.maximum(power/power.max(), 1e-8))
    axes[1].plot(ranges, level)
    for distance in first.target_ranges_m:
        axes[1].axvline(distance, color="gray", linestyle="--", alpha=0.5)
    axes[1].set(xlim=(0, 25), ylim=(-60, 3), xlabel="Apparent range from FMCW beat (m)",
                ylabel="Relative power (dB)", title="Range FFT averaged over 16 chirps")
    for ax in axes:
        ax.grid(alpha=0.25)
    fig.savefig(args.output.with_suffix(".png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
