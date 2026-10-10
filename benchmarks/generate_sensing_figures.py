"""Publication-style RF observables from recorded P100 datasets, without retracing."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
from scipy.signal import welch

from airsim_rf.sensing_analysis import power_db, cross_ambiguity, align_known_receiver_clocks, received_waterfall

C = 299792458.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('docs/figures'))
    parser.add_argument('--output-dir', type=Path, default=Path('docs/figures'))
    parser.add_argument('--backend', choices=('numpy', 'cuda'), default='numpy')
    args = parser.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Serif', 'font.size':9, 'axes.titlesize':10,
        'axes.labelsize':9, 'legend.fontsize':8, 'xtick.labelsize':8, 'ytick.labelsize':8,
        'axes.spines.top':False, 'axes.spines.right':False, 'svg.hashsalt':'airsim-rf-sensing'})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    radar = np.load(args.data_dir/'terrain_scan_iq.npz', allow_pickle=False)
    sdr = np.load(args.data_dir/'pluto_esm_iq.npz', allow_pickle=False)
    terrain = json.loads((args.data_dir/'terrain_signature_data.json').read_text())
    radio = json.loads((args.data_dir/'pluto_esm_report.json').read_text())
    data, figures = {}, []
    def save(fig, name):
        for suffix in ('png','svg'):
            fig.savefig(args.output_dir/f'{name}.{suffix}', dpi=180, bbox_inches='tight', metadata={'Date':None} if suffix=='svg' else None)
        plt.close(fig)
        figures.append(name)
    def panel(ax,title):
        ax.set_title(title,loc='left')
        ax.grid(alpha=.2)
    gate = (radar['path_length_m']>=10)&(radar['path_length_m']<=100)
    length = radar['path_length_m'][gate]
    distance = radar['distance_m']
    pflat, pdem = np.abs(radar['compressed_flat'])**2, np.abs(radar['compressed_dem'])**2
    reference = max(pflat.max(),pdem.max())
    data.update(path_length_m=length, distance_m=distance, range_time_flat=power_db(pflat,reference), range_time_dem=power_db(pdem,reference))

    fig, axes=plt.subplots(1,3,figsize=(7.6,2.6),layout='constrained',sharey=True)
    for ax,feature,letter in zip(axes,terrain['features'],'abc'):
        i=feature['index']
        high=np.abs(radar['compressed_dem'][i])**2
        low=np.abs(radar['compressed_dem_20mhz'][i])**2
        ref=max(high.max(),low.max())
        ax.plot(length,power_db(high,ref),label='200 MHz')
        ax.plot(length,power_db(low,ref),ls='--',label='20 MHz')
        ax.axvline(feature['midpoint_expected_path_length_m'],color='k',ls=':',lw=.8,label='Midpoint reference')
        ax.set(xlabel=r'$c\tau$ (m)',ylim=(-45,1),xlim=(10,100))
        panel(ax,f'({letter}) '+feature['label'].split(': ')[1])
    axes[0].set_ylabel('Matched-filter power / site peak (dB)')
    axes[-1].legend(loc='lower right')
    data['profiles_200mhz']=np.abs(radar['compressed_dem'][radar['feature_indices']])**2
    data['profiles_20mhz']=np.abs(radar['compressed_dem_20mhz'][radar['feature_indices']])**2
    save(fig,'sensing_radar_delay_profiles')

    truth=np.asarray(terrain['dem_height_reference_m']);estimate=np.asarray(terrain['iq_peak_height_dem_m'])
    error=estimate-truth;ecdf=np.arange(1,len(error)+1)/len(error)
    fig,axes=plt.subplots(1,2,figsize=(7.2,2.8),layout='constrained')
    axes[0].scatter(truth,estimate,s=10,alpha=.7,label='91 scan positions')
    axes[0].plot([-1,31],[-1,31],'k--',lw=.8,label='Identity')
    axes[0].set(xlabel='DEM midpoint height (m)',ylabel='I/Q peak equivalent height (m)')
    panel(axes[0],'(a) Estimator versus reference');axes[0].legend()
    axes[1].step(np.sort(np.abs(error)),ecdf,where='post')
    axes[1].set(xlabel='Absolute height error (m)',ylabel='Empirical cumulative probability',ylim=(0,1.02))
    panel(axes[1],f'(b) RMSE = {np.sqrt(np.mean(error**2)):.3f} m')
    data.update(height_error_m=error,abs_error_sorted_m=np.sort(np.abs(error)),error_ecdf=ecdf)
    save(fig,'sensing_radar_error')

    fs=float(sdr['sample_rate_hz']);impedance=radio['profile']['impedance_ohm']
    signals={'Analog':sdr['input_iq_volts'],'12-bit':sdr['adc_iq_volts'],'8-bit control':sdr['adc8_control_iq_volts']}
    spectra={}
    for key,values in signals.items():
        f,p=welch(values,fs=fs,nperseg=1024,noverlap=512,nfft=1024,window='hann',return_onesided=False,detrend=False,scaling='density',axis=-1)
        spectra[key]=np.fft.fftshift(p,axes=-1)/impedance
    freq=np.fft.fftshift(f);expected=np.asarray(radio['expected_tone_hz_excluding_doppler'])
    data['spectrum_frequency_hz']=freq
    fig,axes=plt.subplots(1,2,figsize=(7.2,2.8),layout='constrained',sharey=True)
    for ri,ax in enumerate(axes):
        for key,psd in spectra.items():
            ax.plot(freq/1e3,10*np.log10(np.maximum(psd[-1,ri],1e-30)/1e-3),label=key,lw=.9)
            data['psd_'+key.replace(' ','_')]=psd
        for index,tone in enumerate(expected[ri]):
            ax.axvline(tone/1e3,color='k',ls=':',lw=.7)
            ax.text(tone/1e3,-91,' A' if index==0 else ' B',fontsize=8)
        ax.set(xlabel='Baseband frequency (kHz)',xlim=(-400,400),ylim=(-180,-88))
        panel(ax,f'({"ab"[ri]}) Receiver {ri+1}, final capture')
    axes[0].set_ylabel('Input-referred PSD (dBm/Hz)');fig.legend(*axes[0].get_legend_handles_labels(),loc='outside upper center',ncol=3)
    save(fig,'sensing_esm_spectrum')

    fig,axes=plt.subplots(1,2,figsize=(7.2,3),layout='constrained')
    waterfall_metadata=[]
    for ri,ax in enumerate(axes):
        actual_rate=radio['records'][-1]['receivers'][ri]['actual_sample_rate_hz']
        wf_frequency,wf_time,wf_psd=received_waterfall(sdr['adc_iq_volts'][-1,ri],
            sample_rate_hz=actual_rate,impedance_ohm=impedance)
        dbm_hz=10*np.log10(np.maximum(wf_psd,1e-30)/1e-3)
        im=ax.pcolormesh(wf_frequency/1e3,wf_time*1000,dbm_hz.T,
            vmin=-175,vmax=-90,cmap='viridis',shading='nearest',rasterized=True)
        ax.set(xlabel='Baseband frequency (kHz)',ylabel='Time from capture start (ms)',xlim=(-400,400))
        panel(ax,f'({"ab"[ri]}) Receiver {ri+1} waterfall')
        data[f'waterfall_frequency_hz_{ri}']=wf_frequency
        data[f'waterfall_time_seconds_{ri}']=wf_time
        data[f'waterfall_psd_w_per_hz_{ri}']=wf_psd
        waterfall_metadata.append({'receiver':ri+1,'actual_sample_rate_hz':actual_rate,
            'capture_start_ns':int(sdr['sim_time_ns'][-1]),'capture_samples':4096,
            'capture_seconds':4096/actual_rate,'frame_count':len(wf_time),
            'window_samples':512,'hop_samples':128,'fft_samples':512,
            'bin_spacing_hz':actual_rate/512,'hann_enbw_hz':1.5*actual_rate/512,
            'window':'Hann','units':'dBm/Hz','time_order':'newest at top',
            'source':'final contiguous 12-bit ADC I/Q capture; no interpolation between snapshots'})
    axes[1].set_ylabel('')
    fig.colorbar(im,ax=axes,label='Input-referred PSD (dBm/Hz)')
    save(fig,'sensing_esm_waterfall')


    fig,axes=plt.subplots(1,2,figsize=(7.2,2.8),layout='constrained',sharey=True)
    for ri,ax in enumerate(axes):
        target=expected[ri,1]
        near=np.abs(freq-target)<5000
        collar=(np.abs(freq-target)>15000)&(np.abs(freq-target)<60000)
        for key,psd in spectra.items():
            prominence=10*np.log10(psd[:,ri,near].max(axis=-1)/np.median(psd[:,ri,collar],axis=-1))
            data[f'weak_line_prominence_{ri}_'+key.replace(' ','_')]=prominence
            ax.plot(radio['epochs_s'],prominence,'o-',ms=3,lw=.8,label=key)
        ax.set(xlabel='Snapshot epoch (s)')
        panel(ax,f'({"ab"[ri]}) Receiver {ri+1}')
    axes[0].set_ylabel('Peak / local PSD floor (dB)');axes[1].legend()
    save(fig,'sensing_esm_line_prominence')

    pair=sdr['adc_iq_volts'][-1]
    rates=[r['actual_sample_rate_hz'] for r in radio['records'][-1]['receivers']]
    corrected=align_known_receiver_clocks(pair,actual_rates_hz=rates,receiver_clocks=radio['clocks'][2:],carrier_hz=radio['profile']['carrier_hz'],nominal_rate_hz=fs)
    lags,freqcaf,raw=cross_ambiguity(*pair,sample_rate_hz=fs,backend=args.backend)
    _,_,aligned=cross_ambiguity(*corrected,sample_rate_hz=fs,backend=args.backend)
    bias=radio['profile']['carrier_hz']*(radio['clocks'][2]['error_ppm']-radio['clocks'][3]['error_ppm'])*1e-6
    raw_band=np.abs(freqcaf-bias)<2500
    corrected_band=np.abs(freqcaf)<2500
    data.update(caf_lag_seconds=lags,caf_raw_frequency_hz=freqcaf[raw_band],caf_raw_power=raw[:,raw_band],caf_corrected_frequency_hz=freqcaf[corrected_band],caf_corrected_power=aligned[:,corrected_band])

    fig,axes=plt.subplots(1,2,figsize=(7.2,2.8),layout='constrained')
    for power,center,label in ((raw,bias,'Recorded clocks'),(aligned,0,'Oracle corrected')):
        band=np.abs(freqcaf-center)<2500
        slab=power[:,band]
        peak_lag,peak_bin=np.unravel_index(np.argmax(slab),slab.shape)
        axes[0].plot(lags*1e6,power_db(slab[:,peak_bin]),label=label)
        axes[1].plot((freqcaf[band]-center)/1e3,power_db(slab[peak_lag]),label=label)
    axes[0].set(xlabel='Relative lag (µs)',ylabel='CAF power / cut peak (dB)',ylim=(-5,.1))
    axes[1].set(xlabel='Frequency about respective center (kHz)',ylabel='CAF power / cut peak (dB)',ylim=(-50,1))
    panel(axes[0],'(a) Delay cuts at peak frequency');panel(axes[1],'(b) Frequency cuts at peak lag');axes[1].legend()
    save(fig,'sensing_passive_cuts')

    # Recorded geometry: conditional loci only, never an I/Q-derived location fix.
    positions=np.asarray(radio['positions_at_start_m']);velocities=np.asarray(radio['velocities_m_s'])
    grid=np.linspace(-100,100,301);xx,yy=np.meshgrid(grid,grid)
    candidates=np.stack([xx,yy,np.full_like(xx,positions[0,2])],axis=-1)
    def observables(source):
        vectors=positions[2:]-source[...,None,:]
        ranges=np.linalg.norm(vectors,axis=-1)
        unit=vectors/ranges[...,None]
        fd=-radio['profile']['carrier_hz']/C*np.sum(unit*(velocities[2:]-velocities[0]),axis=-1)
        return (ranges[...,1]-ranges[...,0])/C,fd[...,1]-fd[...,0]
    delay,doppler=observables(candidates);truth_delay,truth_fd=observables(positions[0])
    fig,ax=plt.subplots(figsize=(4.8,3.8),layout='constrained')
    ax.contour(xx,yy,delay*1e9,levels=[truth_delay*1e9],colors=['#0072B2'],linewidths=1.2)
    ax.contour(xx,yy,doppler,levels=[truth_fd],colors=['#D55E00'],linestyles='--',linewidths=1.2)
    ax.plot([],[],color='#0072B2',label=f'Truth TDOA locus: {truth_delay*1e9:.1f} ns')
    ax.plot([],[],'--',color='#D55E00',label=f'Truth FDOA locus: {truth_fd:.2f} Hz')
    ax.plot(*positions[0,:2],'*',ms=10,color='k',label='Emitter truth')
    ax.scatter(positions[2:,0],positions[2:,1],marker='^',s=35,color='k',label='Receivers')
    for i,p in enumerate(positions[2:]):ax.annotate(f' R{i+1}',p[:2])
    ax.set(xlabel='RF x (m)',ylabel='RF y (m)',aspect='equal',xlim=(-100,100),ylim=(-100,100))
    panel(ax,'Conditional geometry at epoch 0');ax.legend(loc='upper center',bbox_to_anchor=(.5,-.20))
    data.update(geometry_grid_x_m=grid,geometry_grid_y_m=grid,geometry_tdoa_seconds=delay,geometry_fdoa_hz=doppler)
    save(fig,'sensing_passive_geometry')

    np.savez_compressed(args.output_dir/'sensing_products.npz',**data)
    manifest={'scope':'Postprocessing recorded P100 data; no new propagation, detection trial ensemble or live geolocation',
        'source_sha256':{n:sha256((args.data_dir/n).read_bytes()).hexdigest() for n in ('terrain_scan_iq.npz','terrain_signature_data.json','pluto_esm_iq.npz','pluto_esm_report.json')},
        'figures':figures,'waterfalls':waterfall_metadata,'color_map_policy':'Frequency-time PSD waterfall only; no range-Doppler map without a qualified coherent pulse train','caf_backend':args.backend,'caf_definition':'sum Hann[n] s2[n] conj(s1[n-lag]) exp(-j2pi f n/fs), energy-normalized power',
        'caf_capture_seconds':len(pair[0])/fs,'caf_common_support_seconds':(len(pair[0])-40)/fs,'caf_native_frequency_scale_hz':fs/(len(pair[0])-40),
        'caf_fft_interpolated_spacing_hz':float(freqcaf[1]-freqcaf[0]),'caf_lag_spacing_seconds':1/fs,'caf_raw_frequency_center_hz':bias,
        'oracle_clock_correction':'Recorded actual sample rates and receiver LO/phase truth; 32-tap Lanczos resampling. Not an estimated calibration.',
        'welch':{'segment_samples':1024,'overlap_samples':512,'fft_samples':1024,'window':'Hann','bin_spacing_hz':fs/1024,'units':'dBm/Hz via |voltage|^2/50 ohm'},
        'line_prominence':'Maximum PSD within 5 kHz of known weak tone / median PSD 15–60 kHz away. Not total-band SNR, blind detection or Pd.',
        'geometry':{'truth_tdoa_ns':float(truth_delay*1e9),'truth_fdoa_hz':float(truth_fd),'assumptions':'Known emitter altitude and velocity, receiver pose/velocity and calibrated clocks; loci from recorded geometry, not measured estimates.'},
        'unsupported_claims':['Coherent pulse-train range-Doppler from gapped snapshots','ROC/Pd-Pfa without labeled H0/H1 trials','Modulation classification from CW beacons','Geolocation error ellipse/CRLB without identified observations and noise covariance']}
    (args.output_dir/'sensing_products.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'figures':figures,'caf_backend':args.backend,'geometry':manifest['geometry']},indent=2))


if __name__=='__main__':
    main()
