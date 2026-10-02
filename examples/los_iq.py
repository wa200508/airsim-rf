"""Run without AirSim: Sionna LoS channel -> complex matched-load volts."""
import argparse
from pathlib import Path

import numpy as np
from sionna.rt import PlanarArray, Receiver, Transmitter, load_scene

from airsim_rf import ReceiverConfig, RFReceiver


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("los_iq.npz"))
    args = parser.parse_args()
    scene = load_scene()
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.add(Transmitter("tx", position=[0, 0, 10]))
    scene.add(Receiver("rx", position=[100, 0, 10], velocity=[10, 0, 0]))
    config = ReceiverConfig()
    receiver = RFReceiver(scene, config, max_depth=0)
    block = receiver.capture(lambda t: np.exp(2j * np.pi * 10000 * t), sim_time_ns=0)
    block.save(args.output)
    power_w = np.mean(np.abs(block.iq_volts) ** 2) / config.impedance_ohm
    freq_hz = np.angle(np.mean(block.iq_volts[1:] * block.iq_volts[:-1].conj())) * config.sample_rate_hz / (2 * np.pi)
    print(f"Saved {block.iq_volts.size} complex64 samples to {args.output}")
    print(f"Received power: {10*np.log10(power_w/1e-3):.3f} dBm; tone with Doppler: {freq_hz:.3f} Hz")


if __name__ == "__main__":
    main()
