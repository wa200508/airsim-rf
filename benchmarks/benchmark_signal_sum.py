"""Time the existing CPU voltage synthesizer with many propagation paths.

Synthetic coefficients and one shared tone exercise the actual implementation;
this is not an implemented multi-transmitter RF simulation or a GPU benchmark.
"""
import argparse
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", type=int, default=1000)
    parser.add_argument("--samples", type=int, default=4096)
    parser.add_argument("--sample-rate", type=float, default=20e6)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--compact", action="store_true", help="One gain/path at the pulse epoch")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.paths, args.samples, args.iterations, args.sample_rate) <= 0:
        parser.error("counts and sample rate must be positive")
    import numpy as np
    from airsim_rf.receiver import ReceiverConfig, synthesize_voltage
    config = ReceiverConfig(sample_rate_hz=args.sample_rate, num_samples=args.samples)
    shape = (args.paths,) if args.compact else (args.paths, args.samples)
    coefficients = np.full(shape, 1e-5+1e-5j, dtype=np.complex128)
    delays = np.linspace(1e-8, 1e-6, args.paths)

    def waveform(t):
        return np.exp(2j*np.pi*(args.sample_rate/10)*t)

    def update():
        return synthesize_voltage(coefficients, delays, waveform, sim_time_ns=0, config=config)

    update()
    elapsed = []
    for _ in range(args.iterations):
        start = time.perf_counter()
        block = update()
        elapsed.append((time.perf_counter()-start)*1000)
    simulated_ms = 1000*args.samples/args.sample_rate
    result = {"scope": "Existing NumPy synthesize_voltage, synthetic coefficients, one tone; no tracing or ADC",
              "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
              "simulated_block_ms": simulated_ms, "coefficient_bytes": coefficients.nbytes,
              "p50_ms": float(np.percentile(elapsed, 50)),
              "p95_ms": float(np.percentile(elapsed, 95)),
              "realtime_slowdown_p50": float(np.percentile(elapsed, 50))/simulated_ms,
              "path_sample_contributions_per_s": args.paths*args.samples/(np.median(elapsed)/1000),
              "samples_ms": elapsed, "finite_output": bool(np.all(np.isfinite(block.iq_volts)))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
