"""Read completed airsim-rf recordings as scaled complex sample blocks.

No simulator, CUDA, or Sionna scene is required. This reader handles this
project's SigMF layout; it is not a reader for arbitrary SigMF datasets.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re

import numpy as np


@dataclass(frozen=True)
class RecordedIQBlock:
    samples: np.ndarray
    sample_start: int
    sim_time_ns: int
    sample_rate_hz: float
    carrier_hz: float
    units: str
    clipped_component_fraction: float


def iter_iq_blocks(directory, receiver='rx0', *, units='volts'):
    """Yield one complex64 block per recorded channel window.

    ``volts`` reconstructs quantized input-referred I+jQ using each window's
    scale. ``adc_codes`` returns complex-valued integer codes without scaling.
    Reject incomplete runs, inconsistent offsets/times and truncated files.
    Files must remain unchanged while reading; use live.record's callback for
    in-process streaming rather than tailing an unfinished recording.
    """
    if units not in ('volts', 'adc_codes'):
        raise ValueError('units must be volts or adc_codes')
    if not isinstance(receiver, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', receiver):
        raise ValueError('Use a configured receiver ID, not a path')
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    if manifest.get('status') != 'complete' or not manifest.get('rows'):
        raise ValueError('A completed nonempty recording is required')
    metadata_path = directory/f'{receiver}.sigmf-meta'
    if not metadata_path.exists():
        raise ValueError(f'No recording for receiver {receiver!r}')
    metadata = json.loads(metadata_path.read_text())
    fs = float(manifest['sample_rate_hz'])
    if not np.isfinite(fs) or fs <= 0 or metadata['global']['core:sample_rate'] != fs:
        raise ValueError('Invalid or inconsistent sample rate')
    if metadata['global']['core:datatype'] != 'ci16_le':
        raise ValueError('Expected interleaved little-endian int16 I/Q (ci16_le)')
    rows, captures = manifest['rows'], metadata['captures']
    if len(rows) != len(captures):
        raise ValueError('Capture metadata and manifest window counts differ')
    expected_offset = 0
    previous_time = None
    previous_count = None
    for row, capture in zip(rows, captures):
        count, epoch = row['samples_per_receiver'], row['sim_time_ns']
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError('Invalid sample count')
        if isinstance(epoch, bool) or not isinstance(epoch, int):
            raise ValueError('Simulation timestamps must be integer nanoseconds')
        if capture['core:sample_start'] != expected_offset or capture['airsim_rf:sim_time_ns'] != epoch:
            raise ValueError('Inconsistent sample offsets or timestamps')
        if previous_time is not None and epoch-previous_time != round(previous_count*1e9/fs):
            raise ValueError('Recording timestamps are not contiguous')
        scale = capture['airsim_rf:volts_per_count']
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError('Invalid volts-per-count scale')
        expected_offset += count
        previous_time, previous_count = epoch, count
    data_path = directory/f'{receiver}.sigmf-data'
    if data_path.stat().st_size != expected_offset*4:
        raise ValueError('Recording byte count differs from its sample metadata')
    with data_path.open('rb') as stream:
        for row, capture in zip(rows, captures):
            count = row['samples_per_receiver']
            codes = np.fromfile(stream, dtype='<i2', count=count*2)
            if len(codes) != count*2:
                raise ValueError('Recording changed or was truncated while reading')
            codes = codes.reshape(-1, 2)
            if np.any(codes < -2048) or np.any(codes > 2047):
                raise ValueError('Recording contains codes outside the signed 12-bit range')
            samples = codes[:, 0].astype(np.complex64)
            samples.imag = codes[:, 1]
            if units == 'volts':
                samples *= capture['airsim_rf:volts_per_count']
            yield RecordedIQBlock(samples, capture['core:sample_start'], row['sim_time_ns'],
                fs, capture['core:frequency'], units, capture['airsim_rf:clipped_component_fraction'])
