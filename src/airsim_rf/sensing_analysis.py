"""Compatibility analysis API. Oracle correction is observer-only."""
from .processing.sensing import power_db,cross_ambiguity,received_waterfall


def align_known_receiver_clocks(*args,**kwargs):
    """Legacy oracle-evaluation entry point; never used by receiver skills."""
    from .evaluation.clocks import align_known_receiver_clocks as correct
    return correct(*args,**kwargs)
