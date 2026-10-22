"""Recorded-I/Q frequency diagnostics and the actual MUSIC spatial spectrum."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.signal import spectrogram

from .aoa_tracking import PhysicalULA, read_arrays
from .recording import iter_iq_blocks


def frequency_psd(samples, sample_rate_hz):
    """Two-sided complex-voltage PSD; 4096-sample Hann, 50% overlap, no padding."""
    frequency, time, density = spectrogram(
        samples, fs=sample_rate_hz, window='hann', nperseg=4096,
        noverlap=2048, nfft=4096, detrend=False, return_onesided=False,
        scaling='density', mode='psd')
    return np.fft.fftshift(frequency), time, np.fft.fftshift(density, axes=0)


def spatial_spectrum(samples, offsets, carrier_hz, grid):
    from doa_py.algorithm import music
    spectrum=np.asarray(music(samples,num_signal=1,array=PhysicalULA(offsets),
                              signal_fre=carrier_hz,angle_grids=grid),float)
    if not np.isfinite(spectrum).all() or np.max(spectrum)<=0:
        raise ValueError('Expected finite positive MUSIC pseudospectrum')
    return 10*np.log10(np.maximum(spectrum/np.max(spectrum),1e-12))


def plot_recording(recording, arrays_path, output):
    """Generate frequency/algorithm figures from ADC data and receiver metadata only."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .aoa_tracking import consume
    from .geometry import file_digest

    recording=Path(recording);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    arrays=read_arrays(arrays_path)
    # Run the ordinary consumer first to enforce channel/time/geometry consistency.
    estimates=consume(recording,arrays_path)
    fs=arrays['sample_rate_hz'];carrier=arrays['carrier_hz']
    count=len(estimates['rows']);selected=sorted(set((0,count//2,count-1)))
    grid=np.linspace(-70,70,2801)
    values={};spectra=[];eigenvalues=[];phase_data=None
    for site_index,site in enumerate(arrays['sites']):
        gain=np.asarray(site['calibration_complex'])
        gain=gain[:,0]+1j*gain[:,1]
        channels=[];snapshots=[]
        for channel_index,name in enumerate(site['channels']):
            blocks=list(iter_iq_blocks(recording,name))
            if site_index==0:
                channels.append(np.concatenate([b.samples for b in blocks])/gain[channel_index])
            snapshots.append([blocks[index].samples/gain[channel_index] for index in selected])
        snapshots=np.asarray(snapshots).transpose(1,0,2)
        site_spectra=[]
        for slot,index in enumerate(selected):
            db=spatial_spectrum(snapshots[slot],site['element_offsets_m'],carrier,grid)
            observed=estimates['rows'][index]['bearings'][site_index]['angle_deg']
            if not np.isclose(grid[np.argmax(db)],observed):
                raise ValueError('Displayed MUSIC peak differs from the ordinary consumer')
            site_spectra.append(db)
        spectra.append(site_spectra)
        middle=selected.index(count//2)
        covariance=np.cov(snapshots[middle])
        eigenvalues.append(np.linalg.eigvalsh(covariance)[::-1])
        if site_index==0:
            densities=[]
            for channel in channels:
                frequency,time,density=frequency_psd(channel,fs)
                densities.append(np.mean(density,axis=1))
                if len(densities)==1: waterfall=density
            values.update(frequency_hz=frequency,stft_time_s=time,
                          psd_v2_per_hz=np.asarray(densities),waterfall_v2_per_hz=waterfall)
            cross=np.mean(snapshots[middle]*snapshots[middle,0].conj(),axis=1)
            measured=np.unwrap(np.angle(cross))
            offsets=np.asarray(site['element_offsets_m'])
            angle=estimates['rows'][count//2]['bearings'][0]['angle_deg']
            fitted=2*np.pi*carrier/299792458.*(offsets-offsets[0])*np.sin(np.deg2rad(angle))
            phase_data=(offsets,measured,fitted)
    spectra=np.asarray(spectra);eigenvalues=np.asarray(eigenvalues)
    epochs=np.asarray([estimates['rows'][i]['sim_time_ns'] for i in selected])*1e-9
    values.update(angle_grid_deg=grid,music_relative_db=spectra,selected_midpoint_s=epochs,
                  covariance_eigenvalues_v2=eigenvalues,element_offsets_m=phase_data[0],
                  measured_relative_phase_rad=phase_data[1],music_fitted_phase_rad=phase_data[2])
    db=lambda x:10*np.log10(np.maximum(x,1e-30))
    plt.rcParams.update({'font.size':11,'axes.titlesize':13,'axes.labelsize':11})
    fig,axes=plt.subplots(2,1,figsize=(11,8),layout='constrained')
    fig.suptitle('Generated I/Q → received QPSK in frequency space',fontsize=18)
    mask=abs(frequency)<=100000
    for i,density in enumerate(values['psd_v2_per_hz']):
        axes[0].plot(frequency[mask]/1000,db(density[mask]),label=f'Element {i}',alpha=.85,lw=1.2)
    axes[0].set(title='Site 0: spectra of four calibrated ADC channels',
                xlabel='Baseband frequency offset from 915 MHz (kHz)',ylabel='PSD (dB re 1 V²/Hz)')
    axes[0].legend(ncol=4);axes[0].grid(alpha=.2)
    shown=db(waterfall[mask]);vmax=float(np.percentile(shown,99.5));vmin=vmax-65
    mesh=axes[1].pcolormesh(frequency[mask]/1000,time,shown.T,shading='nearest',
                           cmap='viridis',vmin=vmin,vmax=vmax,rasterized=True)
    axes[1].set(title='Element 0: measured spectrum over the continuous recording',
                xlabel='Baseband frequency offset from 915 MHz (kHz)',ylabel='Acquisition time (s)')
    fig.colorbar(mesh,ax=axes[1],label='PSD (dB re 1 V²/Hz)',pad=.015)
    fig.supxlabel(f'Complex I/Q • {fs/1e6:g} MS/s • Hann 4096 • hop 2048 • Δf = {fs/4096:.2f} Hz\n'
                  'Frequency reveals the occupied signal band; inter-element phase supplies direction.',fontsize=10)
    for suffix in ('png','svg'):fig.savefig(output/f'iq-frequency.{suffix}',dpi=170)
    plt.close(fig)

    fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    fig.suptitle('What MUSIC extracts from the array I/Q',fontsize=19)
    colors=['#1976b9','#d58000','#267d45']
    for site_index in range(2):
        ax=axes[0,site_index]
        for j,index in enumerate(selected):
            peak=grid[np.argmax(spectra[site_index,j])]
            ax.plot(grid,spectra[site_index,j],color=colors[j],lw=1.5,
                    label=f'{epochs[j]:.3f} s: peak {peak:.2f}°')
            ax.plot(peak,0,'o',color=colors[j],ms=4)
        ax.set(title=f'Site {site_index}: MUSIC spatial pseudospectrum',xlabel='Arrival angle from array broadside (degrees)',
               ylabel='Relative pseudospectrum (dB)',ylim=(-65,3),xlim=(-70,70))
        ax.legend(fontsize=9,loc='lower center');ax.grid(alpha=.2)
    for site_index in range(2):
        relative=db(eigenvalues[site_index]/eigenvalues[site_index,0])
        axes[1,0].plot(np.arange(1,len(relative)+1),relative,'o-',label=f'Site {site_index}')
    axes[1,0].set(title=f'Covariance eigenvalues at {epochs[selected.index(count//2)]:.3f} s',
                  xlabel='Eigenvalue rank (largest first)',ylabel='Relative eigenvalue power (dB)',xticks=[1,2,3,4])
    axes[1,0].axvspan(1.5,4.3,color='#777777',alpha=.08,label='MUSIC noise subspace (ranks 2–4)')
    axes[1,0].legend(fontsize=9);axes[1,0].grid(alpha=.2)
    offset,measured,fitted=phase_data
    axes[1,1].plot(offset,measured,'o',ms=7,label='Measured channel cross-phase')
    axes[1,1].plot(offset,fitted,'--',label='Phase slope from MUSIC angle')
    axes[1,1].set(title='Site 0: spatial phase retained in complex I/Q',xlabel='Element offset along array (m)',
                  ylabel='Unwrapped phase relative to element 0 (rad)')
    axes[1,1].legend(fontsize=9);axes[1,1].grid(alpha=.2)
    fig.supxlabel('Same recorded ADC samples → spatial covariance → signal/noise subspaces → angular peaks\n'
                  'Each pseudospectrum is normalized to its own peak; it is not RF power or a probability.',fontsize=10)
    for suffix in ('png','svg'):fig.savefig(output/f'music-processing.{suffix}',dpi=170)
    plt.close(fig)
    np.savez_compressed(output/'music-plot-values.npz',**values)
    details={'source':'completed ADC I/Q and receiver geometry/calibration only; no emitter truth or source waveform',
        'sample_rate_hz':fs,'carrier_hz':carrier,'windows':count,
        'fft':{'window':'Hann','samples':4096,'hop_samples':2048,'nfft':4096,'bin_spacing_hz':fs/4096,
               'scaling':'two-sided PSD, V²/Hz; dB relative to 1 V²/Hz','zero_padding':False},
        'music':{'implementation':estimates['doa_py'],'num_sources':1,'angle_step_deg':.05,
                 'snapshots':'all samples in selected 12 ms windows','normalization':'10 log10(P / max(P)) per curve',
                 'selected_midpoint_s':epochs.tolist(),'peaks_match_consumer':True},
        'array_metadata_sha256':file_digest(arrays_path),
        'iq_sha256':{name:file_digest(recording/f'{name}.sigmf-data') for site in arrays['sites'] for name in site['channels']},
        'figures':['iq-frequency.png','music-processing.png'],'values':'music-plot-values.npz'}
    (output/'music-plots.json').write_text(json.dumps(details,indent=2)+'\n')
    return details


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording',type=Path)
    parser.add_argument('--arrays',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(plot_recording(args.recording,args.arrays,args.output),indent=2))
