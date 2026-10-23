"""Legacy recording adapter and compatibility exports for offline tracking.

Algorithms live in processing/ and accept neutral sample blocks. Project-specific
recording metadata is translated here; evaluation is loaded only on request.
"""
from .processing.music import C,PhysicalULA,estimate_bearing,read_arrays
from .processing.tracking import intersect_bearings,_position_covariance,track_windows
from .recording import iter_sample_blocks


def consume(recording,arrays_path,*,reverse_first_array=False):
    config=read_arrays(arrays_path)
    names=[name for site in config['sites'] for name in site['channels']]
    windows=zip(*(iter_sample_blocks(recording,name) for name in names),strict=True)
    result=track_windows(windows,config,reverse_first_array=reverse_first_array)
    result['truth_or_paths_used']=False
    # Preserve the historical offline JSON schema at this adapter boundary.
    for row in result['rows']:row['sim_time_ns']=row.pop('timestamp_ns')
    return result


def score(result,truth_path):
    """Deprecated evaluation entry point; processing never calls this wrapper."""
    from .evaluation.tracking import score as evaluate
    return evaluate(result,truth_path)
