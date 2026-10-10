"""Independent sign, normalization and clock-correction checks for RF figures."""
import numpy as np
import pytest
from airsim_rf.sensing_analysis import cross_ambiguity, power_db, align_known_receiver_clocks


@pytest.mark.parametrize('backend',['numpy','cuda'])
@pytest.mark.parametrize('delay,frequency',[(3,16.),(-4,-24.)])
def test_cross_ambiguity_recovers_signed_delay_and_frequency(backend,delay,frequency):
    if backend=='cuda':
        try:
            import cupy as cp
            if cp.cuda.runtime.getDeviceCount()<1:pytest.skip('No CUDA device')
        except (ImportError, RuntimeError):
            pytest.skip('CuPy/CUDA unavailable')
    rng=np.random.default_rng(731)
    reference=rng.normal(size=1024)+1j*rng.normal(size=1024)
    n=np.arange(1024)
    source=np.clip(n-delay,0,1023)
    surveillance=reference[source]*np.exp(2j*np.pi*frequency*n/2048)
    surveillance[(n-delay<0)|(n-delay>=1024)]=0
    lags,f,p=cross_ambiguity(reference,surveillance,sample_rate_hz=2048,max_lag=8,backend=backend)
    i,j=np.unravel_index(np.argmax(p),p.shape)
    assert lags[i]*2048==delay
    assert f[j]==frequency
    assert p.max()==pytest.approx(1.,abs=1e-12)
    assert np.isfinite(p).all() and np.all(p<=1+1e-12)


def test_caf_scale_invariant_and_pure_tone_delay_ambiguous():
    n=np.arange(1024)
    tone=np.exp(2j*np.pi*32*n/2048)
    lag,f,p=cross_ambiguity(tone,7j*tone,sample_rate_hz=2048,max_lag=8)
    np.testing.assert_allclose(p[:,f==0],1,atol=1e-12)
    _,_,other=cross_ambiguity(2*tone,11*tone,sample_rate_hz=2048,max_lag=8)
    np.testing.assert_allclose(other,p,atol=1e-12)


def test_clock_correction_aligns_same_tone_with_distinct_rate_and_lo_errors():
    fs,fc,f=2e6,915e6,150e3
    clocks=[{'error_ppm':5.,'phase_rad':.2},{'error_ppm':-10.,'phase_rad':-.4}]
    rates=[fs*(1+c['error_ppm']*1e-6) for c in clocks]
    signals=np.asarray([np.exp(1j*(2*np.pi*(f-fc*c['error_ppm']*1e-6)*np.arange(4096)/rate-c['phase_rad'])) for c,rate in zip(clocks,rates)])
    corrected=align_known_receiver_clocks(signals,actual_rates_hz=rates,receiver_clocks=clocks,carrier_hz=fc,nominal_rate_hz=fs)
    expected=np.exp(2j*np.pi*f*np.arange(4096)/fs)
    np.testing.assert_allclose(corrected[:,20:-20],np.tile(expected[20:-20],(2,1)),atol=.002)


def test_power_db_uses_explicit_power_reference_and_floor():
    np.testing.assert_equal(power_db([1.,.1,0.],reference=1.,floor_db=-40.),[0.,-10.,-40.])
    with pytest.raises(ValueError):power_db([-1.])
    with pytest.raises(ValueError):cross_ambiguity(np.zeros(20),np.zeros(20),sample_rate_hz=100,max_lag=1)


def test_waterfall_axes_frame_times_and_absolute_power():
    from airsim_rf.sensing_analysis import received_waterfall
    fs=2e6
    samples=np.exp(2j*np.pi*125000*np.arange(4096)/fs)
    frequency,time,power=received_waterfall(samples,sample_rate_hz=fs)
    assert power.shape==(512,29)
    np.testing.assert_allclose(time, (256+128*np.arange(29))/fs)
    np.testing.assert_equal(frequency[np.argmax(power,axis=0)],125000)
    # Parseval power: 1 V complex envelope into 50 ohms = 0.02 W.
    np.testing.assert_allclose(power.sum(axis=0)*(fs/512),.02,rtol=1e-12)


def test_waterfall_tracks_chirp_frequency_in_time_without_filling_gaps():
    from airsim_rf.sensing_analysis import received_waterfall
    fs=2e6;count=4096;t=np.arange(count)/fs
    slope=400000/(count/fs)
    samples=np.exp(2j*np.pi*(-200000*t+.5*slope*t*t))
    frequency,time,power=received_waterfall(samples,sample_rate_hz=fs)
    observed=frequency[np.argmax(power,axis=0)]
    np.testing.assert_allclose(observed,-200000+slope*time,atol=fs/512)
    assert np.all(np.diff(observed)>0)
