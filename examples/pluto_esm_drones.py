"""Four offline drone trajectories: two beacons and two Pluto-class receivers."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter

import numpy as np


def power_dbm(power_w):
    return 10*np.log10(max(float(power_w), 1e-30)/1e-3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('recordings/pluto_esm'))
    parser.add_argument('--epochs', type=int, default=12)
    parser.add_argument('--samples', type=int, default=4096)
    parser.add_argument('--samples-per-link', type=int, default=1028)
    parser.add_argument('--snapshot-stride', type=int, default=100)
    parser.add_argument('--propagation', choices=('diffuse', 'specular', 'los'), default='diffuse')
    parser.add_argument('--noise-figure-db', type=float, default=10.)
    parser.add_argument('--full-scale-dbm', type=float, default=-30.)
    parser.add_argument('--weak-power-dbm', type=float, default=-30.)
    parser.add_argument('--ideal-clocks', action='store_true')
    parser.add_argument('--no-noise', action='store_true')
    parser.add_argument('--backend', choices=('cpu', 'cuda'), default='cpu')
    args = parser.parse_args()
    if min(args.epochs, args.snapshot_stride) < 1 or args.samples < 1024 or args.samples_per_link < 2:
        parser.error('Positive epochs/stride, >=1024 samples and >=2 attempts/link required')
    if args.samples > 10000:
        parser.error('Keep captures within the 5 ms pulse interval (<=10000 samples at 2 MS/s)')
    import drjit as dr
    import mitsuba as mi
    dr.set_thread_count(2)
    if args.backend == 'cuda' and not dr.has_backend(dr.JitBackend.CUDA):
        parser.error('CUDA unavailable; no implicit CPU fallback')
    mi.set_variant('cuda_ad_mono_polarized' if args.backend == 'cuda' else 'llvm_ad_mono_polarized')
    import sionna.rt as rt
    from scipy.signal import welch
    from airsim_rf.sdr import PlutoSDRProfile, RadioClock, SDREmitter, SDRNetworkReceiver, quantize_iq
    from airsim_rf.terrain import demo_terrain
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    root = Path(__file__).resolve().parents[1]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scene = rt.load_scene(str(root/'benchmarks/scenes/terrain.xml'))
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='hw_dipole', polarization='V')
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='hw_dipole', polarization='V')
    starts = np.array([[-60, -30, 12], [45, 45, 18], [-30, -10, 14], [30, -50, 20]], dtype=float)
    velocities = np.array([[2, 0, 0], [-1, 0, 0], [3, 0, 0], [0, 3, 0]], dtype=float)
    names = ('beacon_a', 'beacon_b', 'listener_a', 'listener_b')
    devices = []
    for index, name in enumerate(names):
        cls = rt.Transmitter if index < 2 else rt.Receiver
        device = cls(name, position=starts[index].tolist(), velocity=velocities[index].tolist())
        scene.add(device)
        devices.append(device)
    clocks = [RadioClock()]*4 if args.ideal_clocks else [
        RadioClock(12, .2), RadioClock(-8, 1.1), RadioClock(5, -.7), RadioClock(-10, .4)]
    frequencies = [150e3, -200e3]
    powers_dbm = [0., args.weak_power_dbm]
    emitters = {}
    for i in range(2):
        frequency = frequencies[i]
        emitters[names[i]] = SDREmitter(lambda t, f=frequency: np.exp(2j*np.pi*f*t),
              transmit_power_w=1e-3*10**(powers_dbm[i]/10), clock=clocks[i],
              baseband_frequency_bounds_hz=(frequency, frequency))
    profile = PlutoSDRProfile(noise_figure_db=args.noise_figure_db,
              input_full_scale_dbm=args.full_scale_dbm, noise_enabled=not args.no_noise)
    receiver = SDRNetworkReceiver(scene, emitters, profile,
              clocks=dict(zip(names[2:], clocks[2:])),
              path_solver='first-order-scattering' if args.propagation == 'diffuse' else 'single-bounce',
              max_depth=0 if args.propagation == 'los' else 1, samples_per_link=args.samples_per_link)
    epochs_s = np.arange(args.epochs)*args.snapshot_stride/200.
    arrays = {name: [] for name in ('adc_iq_volts', 'adc_codes', 'input_iq_volts', 'adc8_control_iq_volts')}
    psds, records, link_powers = [], [], []
    for epoch in epochs_s:
        for i, device in enumerate(devices):
            device.position = (starts[i]+velocities[i]*epoch).tolist()
        start = perf_counter()
        captures = receiver.capture(round(float(epoch)*1e9), num_samples=args.samples)
        total_ms = (perf_counter()-start)*1000
        row, row_powers, row_psd = [], [], []
        for rx_name in names[2:]:
            cap = captures[rx_name]
            _, control, _, clipping8 = quantize_iq(cap.input_iq_volts,
                      full_scale_dbm=profile.input_full_scale_dbm, bits=8)
            for key, value in [('adc_iq_volts', cap.adc_iq_volts), ('adc_codes', cap.adc_codes),
                               ('input_iq_volts', cap.input_iq_volts), ('adc8_control_iq_volts', control)]:
                # Collect by epoch first, then receiver (two entries per row).
                arrays[key].append(value)
            freq_axis, psd = welch(cap.adc_iq_volts, fs=profile.sample_rate_hz, nperseg=1024,
                    return_onesided=False, scaling='density', detrend=False)
            row_psd.append(np.fft.fftshift(psd)/profile.impedance_ohm)
            link_dbm = {name: power_dbm(value) for name, value in cap.link_power_w.items()}
            row_powers.append(list(link_dbm.values()))
            row.append(dict(receiver=rx_name, link_power_dbm=link_dbm,
                     thermal_noise_power_dbm=power_dbm(cap.thermal_noise_power_w),
                     noise_bandwidth_hz=cap.noise_bandwidth_hz, retained_paths=cap.retained_paths,
                     volts_per_count=cap.volts_per_count, clipping_fraction=cap.clipped_component_fraction,
                     adc8_control_clipping_fraction=clipping8, actual_sample_rate_hz=cap.actual_sample_rate_hz))
        psds.append(row_psd)
        link_powers.append(row_powers)
        records.append(dict(epoch_s=float(epoch), channel_ms=receiver.last_channel_ms,
                     capture_ms=total_ms, receivers=row))
        print(f'epoch {epoch:.3f}s: '+ '; '.join(
              f'{item["receiver"]} A={item["link_power_dbm"]["beacon_a"]:.1f} B={item["link_power_dbm"]["beacon_b"]:.1f} dBm'
              for item in row), flush=True)

    expected_tones = []
    for rx_clock in clocks[2:]:
        expected_tones.append([(f*tx_clock.rate_scale + profile.carrier_hz*(tx_clock.error_ppm-rx_clock.error_ppm)*1e-6)
                                /rx_clock.rate_scale for f, tx_clock in zip(frequencies, clocks[:2])])
    report = dict(hardware='ADALM-PLUTO specification-based profile; no hardware calibration',
          scope='Offline moving RF mounts, not a live AirSim flight or distributed ESM worker',
          profile=asdict(profile), adc_bits=profile.adc_bits, epochs_s=epochs_s.tolist(),
          nominal_channel_update_hz=200, samples_per_capture=args.samples, antennas='Ideal vertical half-wave dipoles',
          clocks=[asdict(clock) for clock in clocks], devices=list(names),
          positions_at_start_m=starts.tolist(), velocities_m_s=velocities.tolist(),
          emitter_baseband_hz=frequencies, emitter_port_power_dbm=powers_dbm,
          expected_tone_hz_excluding_doppler=expected_tones, propagation=args.propagation,
          attempts_per_link=args.samples_per_link if args.propagation == 'diffuse' else 0,
          records=records, adc8_control='Same analog samples, ideal 8-bit conversion; not a HackRF hardware model',
          published_constraints=dict(rf_tuning_hz=[325e6, 3.8e9], max_rf_bandwidth_hz=20e6,
                      adc_bits=12, exposed_tx_channels=1, exposed_rx_channels=1,
                      source='https://wiki.analog.com/university/tools/pluto/devs/specs'),
          calibration_status=dict(noise_figure='Chosen 10 dB default, configurable; not measured for this frequency/gain',
                      input_full_scale='Chosen -30 dBm default, configurable; input-referred manual-gain surrogate',
                      filter='Fourth-order Butterworth approximation, not AD9363 filter coefficients',
                      antenna='Ideal dipoles, not measured antennas mounted on airframes',
                      terrain='Synthetic uniform material, no calibrated persistent diffuse speckle',
                      transmitter='Chosen port powers and ideal continuous tones, not a DAC/EVM model',
                      clock='Chosen constant errors within published +/-25 ppm initial-accuracy example; no drift/jitter'),
          unmodeled=['AGC dynamics', 'RF compression and intermodulation', 'LO phase noise and spurs',
                      'DC offset and I/Q imbalance', 'USB drops and acquisition start jitter', 'drone airframe scattering'],
          budget=dict(checked_utc='2026-10-03', usd_per_pluto=349.95, radios=4, radio_subtotal_usd=1399.80,
                      source='https://www.nooelec.com/store/adalm-pluto.html', excludes='tax, shipping, antennas, cables, computers, power and drones'),
          versions=dict(sionna=rt.__version__, mitsuba=mi.__version__, drjit=dr.__version__, backend=mi.variant()))
    for key in arrays:
        arrays[key] = np.stack(arrays[key]).reshape((args.epochs, 2)+np.shape(arrays[key][0]))
    np.savez_compressed(args.output_dir/'pluto_esm_iq.npz', **arrays,
          sim_time_ns=np.rint(epochs_s*1e9).astype(np.int64), receiver_names=np.array(names[2:]),
          sample_rate_hz=profile.sample_rate_hz, carrier_hz=profile.carrier_hz,
          impedance_ohm=profile.impedance_ohm, profile_json=json.dumps(report))
    (args.output_dir/'pluto_esm_report.json').write_text(json.dumps(report, indent=2)+'\n')
    # One contiguous final block per receiver, in an SDR interchange format.
    # Earlier epochs stay in NPZ; concatenating them would conceal capture gaps.
    for ri, rx_name in enumerate(names[2:]):
        stem = args.output_dir/rx_name
        arrays['adc_codes'][-1, ri].astype('<i2').tofile(stem.with_suffix('.sigmf-data'))
        metadata = {'global': {'core:datatype': 'ci16_le', 'core:sample_rate': profile.sample_rate_hz,
                    'core:version': '1.2.6', 'core:description': 'Simulated Pluto-class signed 12-bit I/Q in int16 containers; not hardware-calibrated',
                    'airsim_rf:adc_bits': 12, 'airsim_rf:input_full_scale_dbm': profile.input_full_scale_dbm,
                    'airsim_rf:volts_per_count': records[-1]['receivers'][ri]['volts_per_count'],
                    'airsim_rf:actual_sample_rate_hz': records[-1]['receivers'][ri]['actual_sample_rate_hz']},
                    'captures': [{'core:sample_start': 0, 'core:frequency': profile.carrier_hz,
                                  'airsim_rf:sim_time_ns': int(round(float(epochs_s[-1])*1e9))}],
                    'annotations': []}
        stem.with_suffix('.sigmf-meta').write_text(json.dumps(metadata, indent=2)+'\n')

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), layout='constrained')
    terrain = demo_terrain()
    x, y = np.meshgrid(terrain.x_m, terrain.y_m)
    image = axes[0, 0].pcolormesh(x, y, terrain.heights_m, cmap='terrain', shading='auto')
    fig.colorbar(image, ax=axes[0, 0], label='DEM elevation (m)')
    for i, name in enumerate(names):
        route = starts[i]+epochs_s[:, None]*velocities[i]
        axes[0, 0].plot(route[:, 0], route[:, 1], marker='o', markersize=3, label=name)
    axes[0, 0].set(xlabel='RF x (m)', ylabel='RF y (m)', title='Four RF mounts; vertical dipoles', aspect='equal')
    axes[0, 0].legend(fontsize=8)
    link_powers = np.asarray(link_powers)
    for ri, rx_name in enumerate(names[2:]):
        for ti, tx_name in enumerate(names[:2]):
            axes[0, 1].plot(epochs_s, link_powers[:, ri, ti], label=f'{tx_name} → {rx_name}')
    axes[0, 1].set(xlabel='Simulation epoch (s)', ylabel='Input-referred link power (dBm)',
                   title='Filtered signal only; coherent per-link sum')
    axes[0, 1].legend(fontsize=8)
    for ri, rx_name in enumerate(names[2:]):
        for key, label in [('adc_iq_volts', '12-bit Pluto profile'), ('adc8_control_iq_volts', '8-bit numeric control')]:
            f, p = welch(arrays[key][-1, ri], fs=profile.sample_rate_hz, nperseg=1024,
                         return_onesided=False, scaling='density', detrend=False)
            axes[1, ri].plot(np.fft.fftshift(f)/1e3,
                 10*np.log10(np.maximum(np.fft.fftshift(p)/profile.impedance_ohm/1e-3, 1e-30)), label=label)
        for frequency in expected_tones[ri]:
            axes[1, ri].axvline(frequency/1e3, color='#555555', linestyle=':', linewidth=.7)
        axes[1, ri].set(xlabel='Nominal sampled baseband frequency (kHz)', ylabel='PSD (dBm/Hz)',
                       title=f'{rx_name}: final recorded I/Q', xlim=(-500, 500))
        axes[1, ri].legend(fontsize=8)
    fig.suptitle('PlutoSDR-class passive sensing: two simultaneous beacons, two moving receivers\n'
                 '915 MHz; 2 MS/s; 1 MHz receive filter; chosen NF / ADC calibration; no shared radio clock')
    fig.savefig(args.output_dir/'pluto_esm_overview.png', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained', sharey=True)
    psds = np.asarray(psds)
    for ri, ax in enumerate(axes):
        levels = 10*np.log10(np.maximum(psds[:, ri]/1e-3, 1e-30))
        image = ax.imshow(levels, extent=[-profile.sample_rate_hz/2e3, profile.sample_rate_hz/2e3,
                         epochs_s[-1]+args.snapshot_stride/200., epochs_s[0]],
                          aspect='auto', cmap='magma', vmin=-150, vmax=-90)
        ax.set(xlabel='Baseband frequency (kHz)', ylabel='Selected simulation epoch (s)',
               xlim=(-500, 500), title=names[ri+2])
    fig.colorbar(image, ax=axes, label='Recorded 12-bit I/Q PSD (dBm/Hz)')
    fig.suptitle('Received spectrum waterfall; clock offsets differ between listeners')
    fig.savefig(args.output_dir/'pluto_esm_waterfalls.png', dpi=160)
    plt.close(fig)
    print(f'Saved recordings, plots and assumptions to {args.output_dir}', flush=True)


if __name__ == '__main__':
    main()
