"""Plot recorded CPU update timing against the 120 Hz deadline."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    directory = Path(__file__).resolve().parent
    cases = [
        ("Original: 2 targets", "baseline_cpu_2targets.json"),
        ("Batched: 2 targets", "batched_cpu_2targets_long.json"),
        ("Batched: 8 targets", "batched_cpu_8targets.json"),
        ("Batched: street scene", "batched_cpu_street.json"),
    ]
    results = [json.loads((directory/"results"/file).read_text()) for _,file in cases]
    y = np.arange(len(cases))
    fig, ax = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
    ax.barh(y-0.17, [r["p50_ms"] for r in results], height=0.32, label="Median")
    bars = ax.barh(y+0.17, [r["p95_ms"] for r in results], height=0.32, label="p95")
    ax.bar_label(bars, labels=[f'{r["p95_ms"]:.2f} ms' for r in results], padding=4)
    ax.axvline(1000/120, linestyle="--", color="firebrick", label="120 Hz budget: 8.33 ms")
    ax.set_yticks(y, [label for label,_ in cases])
    ax.invert_yaxis()
    ax.set(xlabel="Warm RF update latency (ms)", xlim=(0, 27),
           title="CPU Sionna → I/Q → ADC → FFT timing\nAirSim physics, rendering and RPC excluded")
    ax.grid(axis="x", alpha=0.2)
    ax.legend(loc="lower right")
    fig.savefig(directory/"cpu_timing.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
