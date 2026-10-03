"""Unit/scale checks for receiver-sharded deployment estimates."""
import pytest

from airsim_rf.runtime_metrics import receiver_gpu_workload, conditional_gpu_ray_times


def test_receiver_sharding_preserves_all_transmitters_and_query_budget():
    fleet = receiver_gpu_workload(transmitters=100, receivers=10,
             attempts_per_link=1028, specular_planes=1, pulse_hz=200)
    single = receiver_gpu_workload(transmitters=100, receivers=1,
             attempts_per_link=1028, specular_planes=1, pulse_hz=200)
    assert fleet['visibility_queries_per_gpu_per_pulse_upper_bound'] == 205900
    assert fleet['visibility_queries_per_gpu_per_pulse_upper_bound'] == single['visibility_queries_per_gpu_per_pulse_upper_bound']
    assert fleet['visibility_queries_fleet_per_pulse_upper_bound'] == 2059000
    assert fleet['ray_only_required_queries_per_second_at_pulse_rate'] == 41180000
    assert fleet['pulse_budget_ms'] == 5
    assert fleet['physics_budget_ms'] == pytest.approx(1000/120)
    assert fleet['compact_channel_bytes_per_gpu_per_pulse_upper_bound'] == 1648000
    assert fleet['compact_channel_bytes_per_gpu_per_second_upper_bound'] == 329600000
    row = conditional_gpu_ray_times(fleet, host_sampling_ms=12,
                                    effective_query_rates=[100e6])[0]
    assert row['ray_stage_ms_at_upper_bound_query_count'] == pytest.approx(2.059)
    assert row['unchanged_measured_host_sampling_plus_ray_stage_ms'] == pytest.approx(14.059)
    assert conditional_gpu_ray_times(fleet)[0]['unchanged_measured_host_sampling_plus_ray_stage_ms'] is None


@pytest.mark.parametrize('rates', [[0], [-1], [float('nan')], [float('inf')]])
def test_invalid_throughput_cannot_produce_plausible_estimates(rates):
    workload = receiver_gpu_workload(transmitters=1, receivers=1,
               attempts_per_link=2, specular_planes=0, pulse_hz=120)
    with pytest.raises(ValueError):
        conditional_gpu_ray_times(workload, effective_query_rates=rates)
