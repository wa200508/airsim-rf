"""MUSIC/PSD math using calibrated complex samples and known receiver geometry.

No environment, transmitter truth, simulator, propagation or recording imports.
"""
import json
from pathlib import Path
import numpy as np
from scipy.signal import spectrogram

C = 299792458.


class PhysicalULA:
    """doa_py steering protocol, using actual metre offsets and exact RF c.

    Broadside is local +x, elements lie on local +y, angles increase towards +y.
    A front-hemisphere prior resolves the ULA's front/back ambiguity.
    """
    def __init__(self, offsets_m):
        self.offsets=np.asarray(offsets_m,float)

    def steering_vector(self, signal_fre, angles, unit='deg'):
        angle=np.deg2rad(angles) if unit=='deg' else np.asarray(angles)
        return np.exp(2j*np.pi*signal_fre/C*self.offsets[:,None]*np.sin(angle)[None,:])


def estimate_bearing(samples, offsets_m, carrier_hz, *, grid_deg=None):
    """Use an external MUSIC implementation; return angle and rank-one contrast."""
    try:
        from doa_py.algorithm import music
    except ImportError as error:
        raise RuntimeError('AoA consumer requires the tracking extra: pip install airsim-rf[tracking]') from error
    samples=np.asarray(samples)
    offsets=np.asarray(offsets_m,float)
    if (samples.ndim!=2 or samples.shape[0]<3 or samples.shape[1]<64
            or offsets.shape!=(samples.shape[0],) or not np.isfinite(samples).all()
            or not np.isfinite(offsets).all() or np.any(np.diff(offsets)<=0)):
        raise ValueError('MUSIC needs finite ordered ULA channels and at least 64 simultaneous samples')
    if not np.isfinite(carrier_hz) or carrier_hz<=0 or np.max(np.diff(offsets))>C/carrier_hz/2*(1+1e-10):
        raise ValueError('Positive carrier and at most half-wavelength element spacing required')
    grid=np.linspace(-70,70,2801) if grid_deg is None else np.asarray(grid_deg,float)
    covariance=np.cov(samples)
    eigen=np.linalg.eigvalsh(covariance)
    contrast=float(max(eigen[-1],0)/max(eigen[-2],np.finfo(float).tiny))
    if eigen[-1]<=0 or contrast<5:
        return {'detected':False,'angle_deg':None,'eigenvalue_ratio':contrast}
    spectrum=music(samples,num_signal=1,array=PhysicalULA(offsets),signal_fre=carrier_hz,angle_grids=grid)
    if np.any(np.isnan(spectrum)):
        raise ValueError('MUSIC produced a NaN spectrum')
    index=int(np.argmax(spectrum))
    return {'detected':index not in (0,len(grid)-1),'angle_deg':float(grid[index]),
            'eigenvalue_ratio':contrast}


def read_arrays(path):
    config=json.loads(Path(path).read_text())
    if config.get('schema_version')!=1 or len(config.get('sites',[]))!=2:
        raise ValueError('Array schema v1 requires exactly two sites for this single-emitter 2D example')
    names=[]
    for site in config['sites']:
        offsets=np.asarray(site['element_offsets_m'],float)
        center=np.asarray(site['center_rf_m'],float)
        if (offsets.shape!=(len(site['channels']),) or len(offsets)<3 or not np.isfinite(offsets).all()
                or np.any(np.diff(offsets)<=0) or center.shape!=(3,) or not np.isfinite(center).all()
                or not np.isfinite(site['yaw_rad'])):
            raise ValueError('Each site requires ordered element offsets, finite center and yaw')
        gains=np.asarray(site['calibration_complex'],float)
        if gains.shape!=(len(offsets),2) or not np.isfinite(gains).all() or np.any(np.linalg.norm(gains,axis=1)==0):
            raise ValueError('Each channel requires a finite nonzero complex calibration gain [real,imag]')
        names.extend(site['channels'])
    if len(set(names))!=len(names):
        raise ValueError('Array channel IDs must be unique across sites')
    return config


def frequency_psd(samples, sample_rate_hz):
    """Two-sided complex-voltage PSD; 4096-sample Hann, 50% overlap, no padding."""
    size=min(4096,len(samples))
    frequency, time, density = spectrogram(
        samples, fs=sample_rate_hz, window='hann', nperseg=size,
        noverlap=size//2, nfft=size, detrend=False, return_onesided=False,
        scaling='density', mode='psd')
    return np.fft.fftshift(frequency), time, np.fft.fftshift(density, axes=0)


def spatial_spectrum(samples, offsets, carrier_hz, grid):
    from doa_py.algorithm import music
    spectrum=np.asarray(music(samples,num_signal=1,array=PhysicalULA(offsets),
                              signal_fre=carrier_hz,angle_grids=grid),float)
    if not np.isfinite(spectrum).all() or np.max(spectrum)<=0:
        raise ValueError('Expected finite positive MUSIC pseudospectrum')
    return 10*np.log10(np.maximum(spectrum/np.max(spectrum),1e-12))
