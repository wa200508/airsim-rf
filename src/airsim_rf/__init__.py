"""RF simulation package; receiver applications can import without loading it.

Legacy top-level simulation exports are lazy so a sample-processing skill does
not import a simulator, propagation backend or CUDA when importing this package.
"""
__all__ = ["IQBlock", "RFReceiver", "ReceiverConfig", "synthesize_voltage"]


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(name)
    from . import receiver
    value = getattr(receiver, name)
    globals()[name] = value
    return value
