"""Independent bearings, geometry observability and calibration negative cases."""
import numpy as np
import pytest

from airsim_rf.aoa_tracking import C,estimate_bearing,intersect_bearings


@pytest.mark.parametrize('angle',[-42.,-12.3,0.,23.45,51.])
def test_external_music_recovers_unknown_modulated_source(angle):
    pytest.importorskip('doa_py')
    rng=np.random.default_rng(413)
    carrier=915e6;offsets=(np.arange(4)-1.5)*C/carrier/2
    qpsk=(2*rng.integers(0,2,4096)-1)+1j*(2*rng.integers(0,2,4096)-1)
    # Independent geometric path lengths, not the consumer's steering adapter.
    direction=np.array([np.cos(np.deg2rad(angle)),np.sin(np.deg2rad(angle))])
    source=1e6*direction
    lengths=np.sqrt(source[0]**2+(source[1]-offsets)**2)
    phases=np.exp(-2j*np.pi*carrier/C*(lengths-lengths[0]))
    samples=phases[:,None]*qpsk+.01*(rng.normal(size=(4,4096))+1j*rng.normal(size=(4,4096)))
    result=estimate_bearing(samples,offsets,carrier)
    assert result['detected'] and abs(result['angle_deg']-angle)<.06
    mirrored=estimate_bearing(samples[::-1],offsets,carrier)
    assert abs(mirrored['angle_deg']+angle)<.06


def test_noise_only_does_not_become_a_track_measurement():
    pytest.importorskip('doa_py')
    rng=np.random.default_rng(91)
    noise=rng.normal(size=(4,4096))+1j*rng.normal(size=(4,4096))
    assert not estimate_bearing(noise,np.arange(4)*C/915e6/2,915e6)['detected']


def test_fusion_intersects_forward_bearings_and_rejects_unobservable_geometry():
    centers=np.array([[0,-10],[0,10]])
    emitter=np.array([20,3.])
    angles=np.arctan2(emitter[1]-centers[:,1],emitter[0]-centers[:,0])
    np.testing.assert_allclose(intersect_bearings(centers,angles),emitter,atol=1e-12)
    assert intersect_bearings(centers,[0.,0.]) is None
    assert intersect_bearings(centers,angles+np.pi) is None


def test_grating_lobe_geometry_rejected():
    pytest.importorskip('doa_py')
    with pytest.raises(ValueError,match='half-wavelength'):
        estimate_bearing(np.ones((4,100),complex),np.arange(4)*C/915e6,915e6)


def test_consumer_uses_per_channel_phase_amplitude_calibration_and_checks_sync(tmp_path):
    import json
    from airsim_rf.aoa_tracking import consume
    pytest.importorskip('doa_py');pytest.importorskip('filterpy')
    directory=tmp_path/'capture';directory.mkdir()
    carrier=915e6;fs=2_000_000;count=1024;windows=3
    offsets=(np.arange(4)-1.5)*C/carrier/2
    gains=np.array([.8,1.2,1.1,.9])*np.exp(1j*np.array([.2,.5,.8,1.1]))
    sites=[];rng=np.random.default_rng(55)
    source=(2*rng.integers(0,2,(windows,count))-1+1j*(2*rng.integers(0,2,(windows,count))-1))/np.sqrt(2)
    expected=[]
    for i,y in enumerate((-10.,10.)):
        angle=np.arctan2(3-y,20);expected.append(angle)
        names=[f's{i}e{j}' for j in range(4)]
        sites.append({'id':str(i),'channels':names,'center_rf_m':[0,y,120.],
            'yaw_rad':0.,'element_offsets_m':offsets.tolist(),
            'calibration_complex':np.column_stack((gains.real,gains.imag)).tolist()})
        for j,name in enumerate(names):
            distance=np.sqrt(20**2+(3-y-offsets[j])**2)
            signal=1000*gains[j]*np.exp(-2j*np.pi*carrier/C*distance)*source
            codes=np.column_stack((np.rint(signal.real.reshape(-1)),np.rint(signal.imag.reshape(-1)))).astype('<i2')
            codes.tofile(directory/(name+'.sigmf-data'))
            captures=[{'core:sample_start':k*count,'core:frequency':carrier,'airsim_rf:sim_time_ns':k*512000,
                       'airsim_rf:volts_per_count':.001,'airsim_rf:clipped_component_fraction':0.} for k in range(windows)]
            (directory/(name+'.sigmf-meta')).write_text(json.dumps({'global':{'core:datatype':'ci16_le','core:sample_rate':fs},'captures':captures}))
    manifest={'status':'complete','sample_rate_hz':fs,'rows':[{'sim_time_ns':k*512000,'samples_per_receiver':count} for k in range(windows)]}
    (directory/'manifest.json').write_text(json.dumps(manifest))
    config={'schema_version':1,'carrier_hz':carrier,'sample_rate_hz':fs,'sites':sites}
    path=tmp_path/'arrays.json';path.write_text(json.dumps(config))
    result=consume(directory,path)
    angles=[b['global_angle_rad'] for b in result['rows'][0]['bearings']]
    np.testing.assert_allclose(angles,expected,atol=np.deg2rad(.15))
    for site in config['sites']:site['calibration_complex']=[[1,0]]*4
    path.write_text(json.dumps(config))
    uncalibrated=consume(directory,path)
    assert min(abs(np.rad2deg(b['global_angle_rad']-angle)) for b,angle in zip(uncalibrated['rows'][0]['bearings'],expected))>3.
    metadata_path=directory/'s1e3.sigmf-meta'
    value=json.loads(metadata_path.read_text());value['captures'][0]['core:frequency']+=1e6
    metadata_path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='share epochs'):
        consume(directory,path)
