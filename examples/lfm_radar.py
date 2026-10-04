"""Moving-drone monostatic LFM radar: raw I/Q and a range-compression example."""
import argparse
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks

from airsim_rf.radar import PointTarget, PointTargetRadar, RadarConfig, range_compress


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("lfm_radar.npz"))
    parser.add_argument("--noise", action="store_true", help="Enable thermal noise, 4 dB noise figure")
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--renderer", choices=("numpy", "direct-llvm", "direct-cuda"), default="numpy")
    args = parser.parse_args()
    import drjit as dr
    import mitsuba as mi
    if args.backend == "cuda" and not dr.has_backend(dr.JitBackend.CUDA):
        parser.error("CUDA unavailable; no implicit CPU fallback")
    mi.set_variant("cuda_ad_mono_polarized" if args.backend == "cuda" else "llvm_ad_mono_polarized")
    config = replace(RadarConfig(), noise_enabled=args.noise)
    radar = PointTargetRadar(config, renderer=args.renderer)
    targets = [PointTarget("target_300m", (300, 0, 50), rcs_m2=1),
               PointTarget("target_600m", (600, 0, 50), rcs_m2=16)]
    capture = radar.capture(targets, position_m=[0, 0, 50], velocity_m_s=[20, 0, 0])
    capture.save(args.output)
    ranges, profile = range_compress(capture.block.iq_volts, config)
    peaks, _ = find_peaks(np.abs(profile), height=np.max(np.abs(profile)) * 0.5,
                         distance=round(config.range_resolution_m / (ranges[1] - ranges[0])) * 2)
    print(f"Saved {capture.block.iq_volts.size} raw complex voltage samples to {args.output}")
    print(f"Compressed range peaks: {np.round(ranges[peaks], 2).tolist()} m")
    print(f"Target Doppler: {np.round(capture.target_doppler_hz, 2).tolist()} Hz")
    print(f"Nominal resolution {config.range_resolution_m:.2f} m; range sample spacing {ranges[1]:.2f} m")
    times_us = np.arange(config.num_samples) / config.sample_rate_hz * 1e6
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), constrained_layout=True)
    axes[0].plot(times_us, capture.block.iq_volts.real * 1e6, label="I")
    axes[0].plot(times_us, capture.block.iq_volts.imag * 1e6, label="Q", alpha=0.75)
    axes[0].set(xlim=(0, 8), xlabel="Time after transmit trigger (µs)", ylabel="Voltage (µV)",
                title="Drone LFM radar: raw received I/Q")
    axes[0].legend()
    level = 20 * np.log10(np.maximum(np.abs(profile) / np.max(np.abs(profile)), 1e-6))
    axes[1].plot(ranges, level)
    for target in targets:
        axes[1].axvline(target.position_m[0], color="gray", linestyle="--", alpha=0.5)
    axes[1].set(xlim=(0, 800), ylim=(-60, 3), xlabel="Slant range (m)", ylabel="Relative amplitude (dB)",
                title="Matched-filter range profile; dashed lines mark true target ranges")
    for ax in axes:
        ax.grid(alpha=0.25)
    plot_path = args.output.with_suffix(".png")
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"Saved range plot to {plot_path}")


if __name__ == "__main__":
    main()
