"""Work-count model calibrated on CPU results, with explicit untested GPU scenarios."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    cases = []
    for name in ('2tx_1rx', '2tx_2rx', '100tx_1rx'):
        result = json.loads((ROOT/'benchmarks/results'/f'sdr_cpu_{name}.json').read_text())
        args, samples = result['arguments'], result['samples']
        tx, rx, rays = args['tx'], args['rx'], args['samples_per_link']
        planes = result['gpu_workload_per_receiver']['candidate_paths_per_gpu_upper_bound']//tx-rays-1
        n = args['samples']+result['filter_warmup_samples']
        p = sum(s['retained_paths'] for s in samples)/len(samples)
        work = p*n
        cases.append(dict(case=name, tx=tx, rx=rx, attempts_per_link=rays, planes=planes,
            processed_samples=n, mean_retained_paths=p, contributions=work,
            candidate_count=tx*rx*(1+planes+rays), visibility_queries_upper_bound=tx*rx*(1+2*planes+2*rays),
            cpu_ns_per_contribution=result['cpu_iq_receiver']['mean_ms']*1e6/work,
            measured_mean_iq_ms=result['cpu_iq_receiver']['mean_ms'],
            measured_mean_channel_ms=result['channel']['mean_ms'],
            measured_mean_service_ms=result['service']['mean_ms'],
            measured_sustained_hz=result['sustained_updates_hz']))
    coefficient = cases[0]['cpu_ns_per_contribution']
    for case in cases:
        predicted_iq = coefficient*case['contributions']/1e6
        # CPU IQ model is held out for later cases; channel is measured, not predicted.
        predicted_service = predicted_iq+case['measured_mean_channel_ms']
        case.update(predicted_iq_ms_from_small_case=predicted_iq,
            predicted_service_ms_using_measured_channel=predicted_service,
            iq_prediction_error_percent=100*(predicted_iq/case['measured_mean_iq_ms']-1))

    gpu = []
    # These engineering assumptions describe resident, tiled FP32 kernels on
    # a 4090-class device. No rate or complete GPU pipeline is measured.
    implementations = {
        'literal_three_phase_evaluations': (.25e9, .75e9),
        'fused_analytic_phase': (.75e9, 2.5e9),
        'tiled_tone_or_lfm_recurrence': (30e9, 100e9),
    }
    for case in (cases[0], cases[-1]):
        # Combined channel allowance includes GPU proposals, rays, native
        # field evaluation and packing; overhead includes launch/sync, receiver
        # filtering/noise/ADC and output delivery to host. It excludes RPC/network.
        channel_range = (.7, 2.) if case['tx']==2 else (2., 8.)
        other_range = (.3, .8) if case['tx']==2 else (.5, 2.)
        for name, (slow_rate, fast_rate) in implementations.items():
            low = sum((channel_range[0], other_range[0], case['contributions']/fast_rate*1000))
            high = sum((channel_range[1], other_range[1], case['contributions']/slow_rate*1000))
            gpu.append(dict(case=case['case'], proposed_implementation=name,
                assumed_contributions_per_second=[slow_rate, fast_rate],
                assumed_channel_ms=list(channel_range), assumed_other_ms=list(other_range),
                estimated_service_latency_ms=[low, high],
                estimated_serial_capacity_hz=[1000/high,1000/low],
                note='Untested engineering envelope; endpoint sums, not probabilistic quantiles or hardware guarantees'))
    result=dict(cpu_calibration_case=cases[0]['case'], cpu_ns_per_contribution=coefficient,
        cpu=cases, gpu_estimates=gpu,
        gpu_reference_device='RTX 4090 class, resident static DEM and tiled FP32 synthesis; not tested',
        gpu_central_planning_point=dict(case=cases[-1]['case'], assumed_channel_ms=4.,
            assumed_other_ms=1., assumed_contributions_per_second=60e9,
            service_ms=5.+cases[-1]['contributions']/60e9*1000,
            serial_capacity_hz=1000/(5.+cases[-1]['contributions']/60e9*1000)),
        gpu_math_note='GPU work remains O(P*N). Throughput and phase recurrence change constants and parallel execution span.',
        exclusions=['AirSim RPC/physics', 'dispatch/network/queueing', 'RF skill processing', 'cold JIT/startup'],
        gpu_measurements_available=False)
    output=ROOT/'benchmarks/results/sdr_scaling_analysis.json'
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
