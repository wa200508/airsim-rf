"""Timestamped private I/Q input with explicit interpolation and boundaries."""
from dataclasses import dataclass
from numbers import Integral

import numpy as np

from .rendering import _epoch


@dataclass(frozen=True)
class SampledWaveform:
    """Finite sample buffer; amplitude is preserved without normalization.

    Uses normalized Lanczos-windowed sinc interpolation. ``interpolation_taps``
    is an accuracy/cost parameter, not a physical path cap. This finite kernel
    approximates ideal bandlimited interpolation; it is not exact at all band
    edges. Supply history AND lookahead with boundary="error" (default).
    boundary="zero" explicitly represents zero outside a finite transmission.
    Every descriptor owns a copied, read-only complex128 input allocation.
    """
    samples: np.ndarray
    sample_rate_hz: float
    reference_time_ns: int = 0
    interpolation_taps: int = 32
    boundary: str = "error"

    def __post_init__(self):
        _epoch(self.reference_time_ns)
        if not np.isfinite(self.sample_rate_hz) or self.sample_rate_hz <= 0:
            raise ValueError("Input sample rate must be finite and positive")
        k = self.interpolation_taps
        if isinstance(k, bool) or not isinstance(k, Integral) or k < 4 or k > 128 or k % 2:
            raise ValueError("interpolation_taps must be even and between 4 and 128")
        if self.boundary not in ("error", "zero"):
            raise ValueError("boundary must be error or zero")
        samples = np.array(self.samples, dtype=np.complex128, copy=True)
        if samples.ndim != 1 or samples.size < 1 or not np.isfinite(samples).all():
            raise ValueError("Input samples must be finite and one-dimensional")
        samples.flags.writeable = False
        object.__setattr__(self, 'samples', samples)

    def __call__(self, time_s):
        coordinates = (np.asarray(time_s)-int(self.reference_time_ns)*1e-9)*self.sample_rate_hz
        if not np.isfinite(coordinates).all():
            raise ValueError("Input times must be finite")
        base = np.floor(coordinates).astype(np.int64)
        half = self.interpolation_taps//2
        indices = base[..., None]+np.arange(-half+1, half+1)
        valid = (indices >= 0) & (indices < self.samples.size)
        if self.boundary == "error" and not valid.all():
            raise ValueError("Insufficient waveform history/lookahead")
        d = coordinates[..., None]-indices
        weights = np.sinc(d)*np.sinc(d/half)
        weights /= np.sum(weights, axis=-1, keepdims=True)
        source = np.where(valid, self.samples[np.clip(indices, 0, self.samples.size-1)], 0)
        return np.sum(source*weights, axis=-1)
