"""Solve the documented flat/DEM scenarios and plot actual channel and I/Q data."""
import argparse
import json
from pathlib import Path
import time

import numpy as np

from scattering_scenario import load_fixture, update_platforms


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--pascal-compat', action='store_true', help='Explicit pinned P100 CUDA compatibility adapter')
    parser.add_argument('--epochs', type=int, default=32)
    parser.add_argument('--tx', type=int, default=100)
    parser.add_argument('--samples-per-link', type=int, default=1028)
    parser.add_argument('--pulse-hz', type=float, default=200)
    parser.add_argument('--snapshot-stride', type=int, default=20)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--output-dir', type=Path, default=Path('docs/figures'))
    parser.add_argument('--legacy-diagnostics', action='store_true', help='Write explicitly named historical channel diagnostics; not the sensing gallery')
    args = parser.parse_args()
    if min(args.epochs, args.tx, args.snapshot_stride, args.threads) < 1 or args.samples_per_link < 2 or args.pulse_hz <= 0:
        parser.error('Positive counts/rate required; >=2 samples/link')
    import drjit as dr
    import mitsuba as mi
    dr.set_thread_count(args.threads)
    if args.backend == 'cuda' and not dr.has_backend(dr.JitBackend.CUDA):
        parser.error('CUDA unavailable; no CPU fallback')
    mi.set_variant('cuda_ad_mono_polarized' if args.backend == 'cuda' else 'llvm_ad_mono_polarized')
    if args.pascal_compat:
        from airsim_rf.p100_compat import enable_pascal_compat
        enable_pascal_compat()
    import sionna.rt as rt
    from sionna.rt.constants import InteractionType
    from scipy.signal import correlate, spectrogram
    from airsim_rf.receiver import ReceiverConfig, synthesize_voltage
    from airsim_rf.rendering import LFMChirpWaveform
    from airsim_rf.scattering import FirstOrderScatteringPathSolver
    from airsim_rf.terrain import demo_terrain
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    matplotlib.rcParams['svg.hashsalt'] = 'airsim-rf-terrain'

    args.output_dir.mkdir(parents=True, exist_ok=True)
    c = 299792458.
    epochs = np.arange(args.epochs)*args.snapshot_stride/args.pulse_hz
    delay_edges_ns = np.linspace(0, 1200, 97)
    doppler_edges_hz = np.linspace(-200, 200, 97)
    representative = args.tx//2
    pulse_width, bandwidth = 8e-6, 20e6
    cfg = ReceiverConfig(carrier_hz=24.125e9, sample_rate_hz=50e6, num_samples=600,
                         transmit_power_w=1., impedance_ohm=50., noise_enabled=False)

    def chirp(t):
        inside = (t >= 0) & (t < pulse_width)
        u = np.where(inside, t, 0)
        return np.where(inside, np.exp(1j*np.pi*(bandwidth/pulse_width*u*u-bandwidth*u)), 0j)

    template = chirp(np.arange(round(pulse_width*cfg.sample_rate_hz))/cfg.sample_rate_hz)
    length_axis = np.arange(cfg.num_samples)*c/cfg.sample_rate_hz
    show_length = length_axis <= 350
    scenarios = {}
    for name in ('ground', 'terrain'):
        scene = load_fixture(name, args.tx, 1)
        solver = FirstOrderScatteringPathSolver()
        prepare_start = time.perf_counter()
        planes = solver.specular_plane_count(scene)
        prepare_ms = 1000*(time.perf_counter()-prepare_start)
        rows_delay, rows_doppler, rows_iq, records = [], [], [], []
        for index, epoch in enumerate(epochs):
            update_platforms(scene, float(epoch))
            # Shared timing fixtures retain their historic poses. This physical
            # demonstration lifts both controls equally above the 30 m surface.
            for device in list(scene.transmitters.values())+list(scene.receivers.values()):
                p = np.asarray(device.position.numpy()).reshape(3)
                device.position = (p+[0, 0, 25]).tolist()
            start = time.perf_counter()
            paths = solver(scene, samples_per_src=args.samples_per_link,
                           max_num_paths_per_src=args.samples_per_link+1+planes, seed=42)
            a, tau = paths.cir(num_time_steps=1, normalize_delays=False, out_type='numpy')
            doppler = paths.doppler.numpy()[0]
            a, tau = a[0, 0, :, 0, :, 0], tau[0]
            dr.sync_thread()
            channel_ms = 1000*(time.perf_counter()-start)
            if not np.isfinite(a).all() or not np.isfinite(doppler).all():
                raise RuntimeError('Nonfinite terrain channel')
            valid = tau >= 0
            # NumPy's histogram accumulates in the weights' dtype. Float64
            # avoids losing weak-bin power when differencing cumulative sums.
            weights = np.abs(a[valid].astype(np.complex128))**2
            rows_delay.append(np.histogram(tau[valid]*1e9, delay_edges_ns, weights=weights)[0])
            rows_doppler.append(np.histogram(doppler[valid], doppler_edges_hz, weights=weights)[0])
            epoch_ns = round(epoch*1e9)
            block = synthesize_voltage(a[representative], tau[representative],
                    LFMChirpWaveform(bandwidth, pulse_width, epoch_ns), sim_time_ns=epoch_ns, config=cfg,
                    doppler_hz=doppler[representative], renderer='direct-cuda' if args.backend == 'cuda' else 'numpy')
            compressed = correlate(block.iq_volts, template, mode='full', method='fft')[template.size-1:]
            compressed /= np.sum(np.abs(template)**2)
            rows_iq.append(np.abs(compressed[show_length])**2)
            interactions = paths.interactions.numpy()[0, 0]
            diffuse = interactions == int(InteractionType.DIFFUSE)
            specular = interactions == int(InteractionType.SPECULAR)
            records.append({'epoch_s': float(epoch), 'channel_and_export_ms': channel_ms,
                            'valid_paths': int(valid.sum()), 'diffuse_paths': int(diffuse.sum()),
                            'specular_paths': int(specular.sum()),
                            'sum_path_power': float(weights.sum()),
                            'delay_power_outside_plot': float(weights[(tau[valid]*1e9 >= delay_edges_ns[-1])].sum()),
                            'doppler_power_outside_plot': float(weights[(doppler[valid] < doppler_edges_hz[0]) | (doppler[valid] >= doppler_edges_hz[-1])].sum())})
            if index % 8 == 0:
                print(f'{name}: epoch {index+1}/{args.epochs}, {valid.sum()} paths, {channel_ms:.1f} ms channel', flush=True)
        frequencies, fast_time, psd = spectrogram(block.iq_volts, fs=cfg.sample_rate_hz,
                window='hann', nperseg=128, noverlap=112, nfft=256, detrend=False,
                return_onesided=False, scaling='density', mode='psd')
        order = np.argsort(frequencies)
        scenarios[name] = {'delay': np.asarray(rows_delay), 'doppler': np.asarray(rows_doppler),
                           'iq': np.asarray(rows_iq), 'spectrum': psd[order],
                           'frequencies_hz': frequencies[order], 'fast_time_s': fast_time,
                           'records': records, 'planes': planes, 'geometry_prepare_ms': prepare_ms}

    def save(fig, name):
        if not args.legacy_diagnostics:
            plt.close(fig)
            return
        name = name.replace('waterfalls', 'snapshot_channel_diagnostics')
        fig.savefig(args.output_dir/f'{name}.svg', metadata={'Date': None}, dpi=140, bbox_inches='tight')
        fig.savefig(args.output_dir/f'{name}.png', dpi=140, bbox_inches='tight')
        plt.close(fig)

    def level(values):
        return 10*np.log10(np.maximum(values, 1e-30))

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained', sharey=True)
    for column, (key, edges, label) in enumerate((('delay', delay_edges_ns, 'Absolute path delay (ns)'),
                                               ('doppler', doppler_edges_hz, 'Instantaneous path Doppler (Hz)'))):
        maximum = max(level(scenarios[name][key]).max() for name in scenarios)
        for row, name in enumerate(scenarios):
            image = axes[row, column].pcolormesh(edges, np.r_[epochs-.5*args.snapshot_stride/args.pulse_hz,
                epochs[-1]+.5*args.snapshot_stride/args.pulse_hz], level(scenarios[name][key]),
                vmin=maximum-55, vmax=maximum, shading='flat', cmap='magma', rasterized=True)
            axes[row, column].set(xlabel=label, ylabel='Simulation time (s)',
                                  title=f'{"Flat ground" if name == "ground" else "DEM terrain"}: {key}')
            if key == 'delay':
                axes[row, column].set_xlim(0, 400)
        fig.colorbar(image, ax=axes[:, column], label='Sum of path powers per bin (dB, dimensionless)')
    fig.suptitle(f'{args.tx} TX → 1 RX: incoherent channel-power snapshot histograms\n'
                 f'{args.samples_per_link} attempts/link; all direct, specular and diffuse paths; 24.125 GHz')
    save(fig, 'channel_waterfalls')

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), layout='constrained', sharex=True, sharey=True)
    maximum = max(level(scenarios[name]['iq']).max() for name in scenarios)
    dx = c/cfg.sample_rate_hz
    length_edges = np.r_[length_axis[show_length]-.5*dx, length_axis[show_length][-1]+.5*dx]
    for ax, name in zip(axes, scenarios):
        image = ax.pcolormesh(length_edges, np.r_[epochs-.5*args.snapshot_stride/args.pulse_hz,
                   epochs[-1]+.5*args.snapshot_stride/args.pulse_hz], level(scenarios[name]['iq']),
                   vmin=maximum-55, vmax=maximum, cmap='magma', rasterized=True)
        ax.set(xlabel='Equivalent total path length cτ (m)', ylabel='Simulation time (s)',
               title=f'{"Flat ground" if name == "ground" else "DEM terrain"}: coherent LFM pulse compression')
    fig.colorbar(image, ax=axes, label='Matched-filter voltage power (dB re 1 V²)')
    fig.suptitle(f'Representative TX {representative} → RX 0: 20 MHz / 8 µs LFM, 1 W, no noise\n'
                 'Bistatic path length, not monostatic range; sampled terrain has no persistent speckle model')
    save(fig, 'lfm_waterfalls')

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), layout='constrained', sharex=True, sharey=True)
    maximum = max(level(scenarios[name]['spectrum']).max() for name in scenarios)
    for ax, name in zip(axes, scenarios):
        values = scenarios[name]
        image = ax.pcolormesh(values['fast_time_s']*1e6, values['frequencies_hz']/1e6,
                    level(values['spectrum']), shading='auto', vmin=maximum-50,
                    vmax=maximum, cmap='magma', rasterized=True)
        ax.set(xlabel='Time within receive window (µs)', ylabel='Baseband frequency (MHz)', ylim=(-12, 12),
               title=f'{"Flat ground" if name == "ground" else "DEM terrain"}: received I/Q spectrogram')
    fig.colorbar(image, ax=axes, label='PSD (dB re 1 V²/Hz)')
    fig.suptitle(f'Actual complex voltage, TX {representative} → RX 0, epoch {epochs[-1]:.2f} s\n'
                 '50 MS/s; Hann 128 samples, hop 16, FFT 256; narrowband Doppler')
    save(fig, 'iq_spectrograms')

    terrain = demo_terrain()
    x, y = np.meshgrid(terrain.x_m, terrain.y_m)
    fig = plt.figure(figsize=(12, 5), layout='constrained')
    ax = fig.add_subplot(121)
    image = ax.pcolormesh(x, y, terrain.heights_m, shading='auto', cmap='terrain', rasterized=True)
    ax.contour(x, y, terrain.heights_m, levels=10, colors='black', linewidths=.4, alpha=.5)
    ax.plot(np.zeros(args.tx), np.linspace(-25, 25, args.tx), '.', color='navy', label='TX start positions, z=35 m')
    ax.plot([10, 10], [-5, -5+.5*epochs[-1]], color='crimson', marker='o', label='RX route, z=40 m')
    ax.arrow(0, 0, epochs[-1], 0, color='navy', width=.4, length_includes_head=True)
    ax.set(xlabel='East / x (m)', ylabel='North / y (m)', title='Synthetic DEM and platform geometry', aspect='equal')
    ax.legend(fontsize=8, loc='upper left')
    fig.colorbar(image, ax=ax, label='Elevation z (m)')
    ax = fig.add_subplot(122, projection='3d')
    ax.plot_surface(x, y, terrain.heights_m, cmap='terrain', linewidth=.25, edgecolor='#555555', alpha=.9)
    ax.set(xlabel='x (m)', ylabel='y (m)', zlabel='z (m)', title='10 m grid, 800 RF triangles')
    ax.set_box_aspect((1, 1, .25))
    save(fig, 'terrain_overview')

    result = {'scope': 'Actual channel solves and coherent single-TX voltage synthesis; synthetic scene, no live AirSim',
              'arguments': {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
              'versions': {'sionna_rt': rt.__version__, 'mitsuba': mi.__version__, 'drjit': dr.__version__, 'backend': mi.variant()},
              'execution': {'propagation': mi.variant(), 'iq_renderer': 'direct-cuda' if args.backend == 'cuda' else 'numpy', 'analysis_and_plotting': 'host SciPy/Matplotlib', 'pascal_compat': args.pascal_compat},
              'terrain': {'grid_shape': list(terrain.heights_m.shape), 'spacing_m': 10, 'vertices': 441, 'triangles': 800,
                          'elevation_min_m': float(terrain.heights_m.min()), 'elevation_max_m': float(terrain.heights_m.max()),
                          'surveyed': False, 'material': {'relative_permittivity': 5, 'conductivity_s_per_m': .01,
                          'thickness_m': .5, 'scattering_coefficient': .3, 'scattering_pattern': 'Lambertian'}},
              'platforms': {'tx_altitude_m': 35, 'rx_altitude_m': 40, 'rule': 'Fixed datum heights; both flat and terrain controls lifted equally by 25 m'},
              'waveform': {'representative_tx_index': representative, 'carrier_hz': cfg.carrier_hz,
                          'bandwidth_hz': bandwidth, 'pulse_width_s': pulse_width, 'sample_rate_hz': cfg.sample_rate_hz,
                          'receive_samples': cfg.num_samples, 'transmit_power_w': 1, 'impedance_ohm': 50, 'noise': False},
              'waterfalls': {'epochs_s': epochs.tolist(), 'delay_edges_ns': delay_edges_ns.tolist(),
                            'doppler_edges_hz': doppler_edges_hz.tolist(), 'path_length_m': length_axis[show_length].tolist(),
                            'channel_power': 'Incoherent sum |a|² over all TX/paths; no coherent slow-time Doppler FFT',
                            'lfm_power': 'Coherent single-TX matched-filter voltage squared; no persistent scatterer model'},
              'scenarios': {name: {'specular_planes': value['planes'], 'geometry_prepare_ms': value['geometry_prepare_ms'],
                            'records': value['records'], 'delay_bin_power': value['delay'].tolist(),
                            'doppler_bin_power': value['doppler'].tolist(), 'lfm_voltage_power_v2': value['iq'].tolist()}
                            for name, value in scenarios.items()},
              'timing_note': 'Documentation trajectory: compilation/cache state varies; plotting, synthesis and diagnostics excluded from channel timer; not a GPU benchmark'}
    (args.output_dir/'scenario_data.json').write_text(json.dumps(result, indent=2)+'\n')
    print(f'Saved documentation figures and underlying waterfall values in {args.output_dir}', flush=True)


if __name__ == '__main__':
    main()
