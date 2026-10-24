"""Observer-only matched-noise clutter audit; no truth is supplied to the RF skill.

Generate actual ADC I/Q A/B cases, plus a clearly labeled noise-free pre-ADC
reference. This does not change the maintained scenario's physical parameters.
"""
import argparse
from copy import deepcopy
import json
from hashlib import sha256
from pathlib import Path
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('radar-clutter-audit'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    import numpy as np
    import mitsuba as mi
    mi.set_variant('llvm_ad_mono_polarized')
    import drjit as dr
    dr.set_thread_count(2)
    import sionna.rt as rt
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from airsim_rf.dashboard_scenario import prepare
    from airsim_rf.dashboard_radar import RadarWindowReceiver
    from radar_skill.processing import range_doppler
    def kin(pos,vel):return {'pose':{'position':dict(zip(('x','y','z'),np.asarray(pos)*[1,-1,-1])),'orientation':{'w':1.,'x':0.,'y':0.,'z':0.}},
                             'twist':{'linear':dict(zip(('x','y','z'),np.asarray(vel)*[1,-1,-1])),'angular':{'x':0.,'y':0.,'z':0.}}}
    def power(rd):return np.asarray(rd['power_db'])+rd['median_bin_power_dbv2']
    summary={'scope':'matched receiver-noise A/B audit; pre-ADC reference is explicitly separated from actual ADC output',
             'parameters_unchanged':['waveform','TX power','antenna','sigma0','noise figure','ADC','sampling budget','range cap'],
             'backend':'LLVM CPU','poses':[],'software':{'sionna_rt':rt.__version__,'mitsuba':mi.__version__,'numpy':np.__version__},
             'source_sha256':{name:sha256(Path(module.__file__).read_bytes()).hexdigest() for name,module in [('radar_processing',__import__('radar_skill.processing',fromlist=['x'])),('fmcw',__import__('airsim_rf.fmcw',fromlist=['x'])),('surface',__import__('airsim_rf.radar_scattering',fromlist=['x']))]}}
    with tempfile.TemporaryDirectory(prefix='radar-clutter-audit-') as td:
        run=Path(td);prepare(run,scenario_dir='mmwave-radar',duration_s=.004)
        c=json.loads((run/'runtime.json').read_text());arrays=json.loads((run/'arrays.json').read_text())
        summary['scenario_input_sha256']=c['input_sha256'];summary['radio']=c['radios']
        for name,pos,vel in [('start',[-200,0,210],[20,0,0]),('east',[200,0,210],[20,0,0]),('masked',[-240,-150,210],[20,0,0])]:
            maps={};analog={};diagnostics={}
            for mode in ['full','clutter-noise','noise','targets-noise','clutter-reference']:
                radio=deepcopy(c['radios']);radio['radar']['clutter']['enabled']=mode in ['full','clutter-noise','clutter-reference']
                radio['radar']['profile']['noise_enabled']=mode!='clutter-reference'
                receiver=RadarWindowReceiver(rt.load_scene(str(run/'bundle/scene.xml'),merge_shapes=False),radio,deepcopy(arrays))
                receiver.control.configure(c['skill']['mode_config']);receiver.control.set_state({'transmit':True,'receive':True})
                receiver.update({'RadarDrone':kin(pos,vel)})
                if mode in ['clutter-noise','noise','clutter-reference']:receiver.targets=[]
                capture=receiver.capture(0,num_samples=40000)['radar_rx0']
                rd=range_doppler(capture.adc_iq_volts,arrays['sample_rate_hz'],arrays['carrier_hz'],arrays['acquisition'])
                maps[mode]=rd;analog[mode]=capture.input_iq_volts
                diagnostics[mode]={'retained_echoes_first_chirp':capture.retained_paths,'clipped_fraction':capture.clipped_component_fraction,
                                   'mean_IF_power_v2':float(np.mean(abs(capture.input_iq_volts)**2))}
            # Same thermal-noise seed and timing in each run make this an
            # amplitude/phase superposition check before nonlinear quantization.
            residual=analog['clutter-noise']-analog['noise']-analog['clutter-reference']
            assert float(np.max(abs(residual)))<2e-8
            reference=range_doppler(analog['clutter-reference'],arrays['sample_rate_hz'],arrays['carrier_hz'],arrays['acquisition'])
            signal_db=power(reference);noise_db=maps['noise']['median_bin_power_dbv2']
            row,column=np.unravel_index(signal_db.argmax(),signal_db.shape)
            record={'viewpoint':name,'position_rf_m':pos,'velocity_rf_m_s':vel,'cases':diagnostics,
                    'analog_superposition_max_error_v':float(np.max(abs(residual))),
                    'strongest_analog_clutter_bin_vs_median_ADC_noise_db':float(signal_db.max()-noise_db),
                    'integrated_clutter_to_noise_db':float(10*np.log10(np.mean(abs(analog['clutter-reference'])**2)/np.mean(abs(analog['noise'])**2))),
                    'clutter_peak_range_m':reference['range_m'][row],'clutter_peak_doppler_khz':reference['doppler_khz'][column],
                    'range_axis_extent_m':[min(reference['range_m']),max(reference['range_m'])],
                    'doppler_axis_extent_khz':[min(reference['doppler_khz']),max(reference['doppler_khz'])]}
            summary['poses'].append(record)
            fig,axes=plt.subplots(1,4,figsize=(16,5),sharex=True,sharey=True,layout='constrained')
            titles=['Full scene: actual ADC','Clutter + noise: actual ADC','Noise only: actual ADC','Clutter reference: pre-ADC\nreceiver noise omitted']
            grids=[power(maps['full'])-noise_db,power(maps['clutter-noise'])-noise_db,power(maps['noise'])-noise_db,signal_db-signal_db.max()]
            ranges=[(-5,45),(-5,15),(-5,15),(-60,0)]
            for index,(ax,title,values,(low,high)) in enumerate(zip(axes,titles,grids,ranges)):
                im=ax.pcolormesh(reference['doppler_khz'],reference['range_m'],values,shading='nearest',vmin=low,vmax=high,cmap='viridis',rasterized=True)
                ax.set_title(title,fontsize=10);ax.set_xlabel('Doppler (kHz)');ax.set_xlim(-12.5,12.5);ax.set_ylim(0,480)
                fig.colorbar(im,ax=ax,label='dB relative to noise-only map median' if index<3 else 'dB relative to isolated clutter peak',shrink=.8)
            axes[0].set_ylabel('Apparent range (m), increasing upward')
            fig.suptitle(f'{name}: unchanged COTS-mode assumptions; {record["strongest_analog_clutter_bin_vs_median_ADC_noise_db"]:.1f} dB strongest clutter bin / median noise bin')
            fig.savefig(args.output/(name+'.svg'));plt.close(fig)
            # Data behind the figure and normalized statistics are small enough
            # to retain independently of full mission I/Q archives.
            np.savez_compressed(args.output/(name+'.npz'),range_m=reference['range_m'],doppler_khz=reference['doppler_khz'],
                                full_adc_dbv2=power(maps['full']),clutter_noise_adc_dbv2=power(maps['clutter-noise']),
                                noise_adc_dbv2=power(maps['noise']),clutter_analog_dbv2=signal_db)
            print(json.dumps(record),flush=True)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':main()
