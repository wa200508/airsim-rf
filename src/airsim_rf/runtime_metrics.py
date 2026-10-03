"""Workload arithmetic for one GPU per receiver, not CPU speedup claims."""
import math


def receiver_gpu_workload(*, transmitters, receivers, attempts_per_link,
                          specular_planes, pulse_hz, physics_hz=120):
    """Upper-bound work for the single-element, first-order scattering model.

    Each diffuse attempt uses one first-hit ray and at most one shadow ray.
    LoS uses one visibility query; each specular plane uses at most two.
    Compact storage counts complex64 gain, float32 delay and float32 Doppler.
    This excludes intermediate buffers, BVH, geometry and waveform samples.
    """
    for value in (transmitters, receivers, attempts_per_link, specular_planes):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Counts must be integers")
    if min(transmitters, receivers) < 1 or attempts_per_link < 2 or specular_planes < 0:
        raise ValueError("Positive radio counts, >=2 attempts and >=0 planes required")
    if not all(math.isfinite(rate) and rate > 0 for rate in (pulse_hz, physics_hz)):
        raise ValueError("Update rates must be finite and positive")
    attempts = transmitters*attempts_per_link
    candidates = attempts+transmitters*(1+specular_planes)
    queries = 2*attempts+transmitters*(1+2*specular_planes)
    compact_bytes = 16*candidates
    return {"topology": "one GPU per physical receiver; all transmitters on every receiver worker",
            "gpu_count": receivers, "transmitters_per_gpu": transmitters,
            "receivers_per_gpu": 1, "diffuse_attempts_per_gpu_per_pulse": attempts,
            "visibility_queries_per_gpu_per_pulse_upper_bound": queries,
            "visibility_queries_fleet_per_pulse_upper_bound": queries*receivers,
            "candidate_paths_per_gpu_upper_bound": candidates,
            "compact_channel_bytes_per_gpu_per_pulse_upper_bound": compact_bytes,
            "compact_channel_bytes_per_gpu_per_second_upper_bound": compact_bytes*pulse_hz,
            "pulse_hz": pulse_hz, "pulse_budget_ms": 1000/pulse_hz,
            "physics_hz": physics_hz, "physics_budget_ms": 1000/physics_hz,
            "ray_only_required_queries_per_second_at_pulse_rate": queries*pulse_hz,
            "ray_only_required_queries_per_second_at_physics_rate": queries*physics_hz,
            "vram_requirement": "unmeasured; compact coefficients are not total device memory"}


def conditional_gpu_ray_times(workload, *, host_sampling_ms=None,
                              effective_query_rates=(100e6, 250e6, 1e9)):
    """Hypothetical ray-stage time; rates are assumptions, not GPU benchmarks.

    The host subtotal applies only when sampling was measured on ONE receiver
    worker. It excludes fields, table preparation, compaction, launch/sync,
    transfer, pose updates, IQ, AirSim and transport. No deadline verdict follows.
    """
    if host_sampling_ms is not None and (not math.isfinite(host_sampling_ms) or host_sampling_ms < 0):
        raise ValueError("Host sampling time must be finite and nonnegative")
    rows = []
    for rate in effective_query_rates:
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("Effective query rates must be finite and positive")
        ray_ms = 1000*workload["visibility_queries_per_gpu_per_pulse_upper_bound"]/rate
        rows.append({"assumed_effective_scene_queries_per_second": rate,
                     "ray_stage_ms_at_upper_bound_query_count": ray_ms,
                     "unchanged_measured_host_sampling_plus_ray_stage_ms":
                         None if host_sampling_ms is None else host_sampling_ms+ray_ms})
    return rows
