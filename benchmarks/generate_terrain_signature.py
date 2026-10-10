"""Make terrain relief visible in pulse-compressed I/Q, with physical controls."""
import argparse
import json
from pathlib import Path

import numpy as np

from terrain_scan import TerrainScan, scan_scene, total_length_to_height, C
from airsim_rf.terrain import demo_terrain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--pascal-compat', action='store_true', help='Explicit pinned P100 CUDA compatibility adapter')
    parser.add_argument('--scan-points', type=int, default=91)
    parser.add_argument('--samples-per-link', type=int, default=1028)
    parser.add_argument('--beamwidth-deg', type=float, default=12)
    parser.add_argument('--output-dir', type=Path, default=Path('docs/figures'))
    args = parser.parse_args()
    if args.scan_points < 3 or args.samples_per_link < 2:
        parser.error('>=3 scan points and >=2 attempts/link required')
    import drjit as dr
    import mitsuba as mi
    dr.set_thread_count(2)
    if args.backend == 'cuda' and not dr.has_backend(dr.JitBackend.CUDA):
        parser.error('CUDA unavailable; no CPU fallback')
    mi.set_variant('cuda_ad_mono_polarized' if args.backend == 'cuda' else 'llvm_ad_mono_polarized')
    if args.pascal_compat:
        from airsim_rf.p100_compat import enable_pascal_compat
        enable_pascal_compat()
    import sionna.rt as rt
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle
    matplotlib.rcParams['svg.hashsalt'] = 'airsim-rf-terrain-signature'
    args.output_dir.mkdir(parents=True, exist_ok=True)
    route_start, route_end = np.array([-75., -50.]), np.array([75., 50.])
    route_length = np.linalg.norm(route_end-route_start)
    distance = np.linspace(0, route_length, args.scan_points)
    direction = (route_end-route_start)/route_length
    xy = route_start+distance[:, None]*direction
    positions = np.column_stack((xy, np.full(args.scan_points, 40.)))
    # Select actual pulse epochs on a 200 Hz clock; pose corresponds to that
    # epoch on a 10 m/s route. Exact endpoint rounding is below 2.5 cm.
    pulse_indices = np.round(distance/10*200).astype(int)
    epochs = pulse_indices/200
    distance = epochs*10
    xy = route_start+distance[:, None]*direction
    positions[:, :2] = xy
    midpoint_xy = xy+[1., 0]
    terrain = demo_terrain()
    truth = terrain.elevation_at(midpoint_xy[:, 0], midpoint_xy[:, 1])
    series, records = {}, {}
    for name in ('ground', 'terrain'):
        scene, peak_gain = scan_scene(name, beamwidth_deg=args.beamwidth_deg)
        scan = TerrainScan(scene, samples_per_link=args.samples_per_link, renderer='direct-cuda' if args.backend == 'cuda' else 'numpy')
        low = TerrainScan(scene, bandwidth_hz=20e6, samples_per_link=args.samples_per_link, renderer='direct-cuda' if args.backend == 'cuda' else 'numpy') if name == 'terrain' else None
        gate = (scan.length_m >= 10) & (scan.length_m <= 100)
        length = scan.length_m[gate]
        iq_rows, compressed_rows, low_iq_rows, low_compressed_rows, counts = [], [], [], [], []
        for i, (position, epoch) in enumerate(zip(positions, epochs)):
            iq, compressed, count = scan.capture(position, velocity=np.r_[direction*10, 0], epoch_s=float(epoch))
            iq_rows.append(iq)
            compressed_rows.append(compressed[gate])
            counts.append(count)
            if low is not None:
                low_iq, low_compressed = low.voltage_from_channel(*scan.last_channel, epoch_s=float(epoch))
                low_iq_rows.append(low_iq)
                low_compressed_rows.append(low_compressed[gate])
            if i % 15 == 0:
                print(f'{name}: {i+1}/{args.scan_points}, {count} retained paths', flush=True)
        series[name] = {'iq': np.asarray(iq_rows), 'compressed': np.asarray(compressed_rows)}
        records[name] = counts
        if low is not None:
            series['terrain_20mhz'] = {'iq': np.asarray(low_iq_rows), 'compressed': np.asarray(low_compressed_rows)}
    heights = total_length_to_height(length)
    power = {name: np.abs(values['compressed'])**2 for name, values in series.items()}
    maximum = max(values.max() for values in power.values())
    relative = {name: 10*np.log10(np.maximum(values/maximum, 1e-8)) for name, values in power.items()}
    # Peak comes only from received I/Q and a fixed 10–100 m delay gate.
    # Neither terrain elevations nor predicted delay enter this estimator.
    measured = {name: heights[np.argmax(values, axis=1)] for name, values in power.items()}
    feature_ranges = ((0, 75), (75, 130), (130, route_length+1))
    feature_indices = []
    for feature, (lo, hi) in enumerate(feature_ranges):
        allowed = np.flatnonzero((distance >= lo) & (distance < hi))
        if not allowed.size:
            allowed = np.array([int(np.argmin(np.abs(distance-(lo+hi)/2)))])
        offset = np.argmin(truth[allowed]) if feature == 1 else np.argmax(truth[allowed])
        feature_indices.append(int(allowed[offset]))
    labels, colors = ('A: first hill', 'B: swale', 'C: second hill'), ('#e45756', '#247ba0', '#5c9632')

    def save(fig, name):
        fig.savefig(args.output_dir/f'{name}.png', dpi=150, bbox_inches='tight')
        fig.savefig(args.output_dir/f'{name}.svg', dpi=150, bbox_inches='tight', metadata={'Date': None})
        plt.close(fig)

    def guides(ax):
        for index, label, color in zip(feature_indices, labels, colors):
            ax.axvline(distance[index], color=color, lw=1, alpha=.65)

    dx, dh = distance[1]-distance[0], C/500e6
    xedges = np.r_[distance-dx/2, distance[-1]+dx/2]
    yedges = total_length_to_height(np.r_[length-dh/2, length[-1]+dh/2])
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout='constrained', sharex=True)
    axes[0].fill_between(distance, truth, -3, color='#d3e6bb')
    axes[0].plot(distance, truth, color='#355c2a', lw=2, label='DEM height under beam midpoint')
    axes[0].axhline(0, color='gray', ls='--', label='Flat-ground control')
    for index, label, color in zip(feature_indices, labels, colors):
        axes[0].plot(distance[index], truth[index], 'o', color=color)
        axes[0].annotate(label, (distance[index], truth[index]), xytext=(0, 13), textcoords='offset points', ha='center', color=color)
    axes[0].set(ylabel='Terrain elevation (m)', ylim=(-3, 33), title='Same DEM: flight line crosses both hills and the drainage swale')
    axes[0].legend(loc='upper right', fontsize=8)
    for ax, name, title in zip(axes[1:], ('ground', 'terrain'), ('Flat ground: received I/Q gives a flat delay ridge', 'DEM: shorter delay over hills, longer delay over the swale')):
        im = ax.pcolormesh(xedges, yedges, relative[name].T, cmap='magma', vmin=-40, vmax=0, rasterized=True)
        ax.plot(distance, measured[name], color='white', lw=1, alpha=.8, label='Peak extracted from I/Q')
        ax.set(ylabel='Equivalent surface height (m)', ylim=(-3, 33), title=title)
        guides(ax)
        ax.legend(loc='upper right', fontsize=8)
    axes[-1].set_xlabel('Distance along flight line (m)')
    fig.colorbar(im, ax=axes[1:], label='Pulse-compressed voltage power (dB, one shared reference)')
    fig.suptitle('Terrain structure in actual complex I/Q after LFM pulse compression\n'
                 f'One TX/RX pair, 40 m altitude, 2 m baseline, {args.beamwidth_deg:g}° beam, 200 MHz chirp')
    save(fig, 'terrain_signature')

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout='constrained')
    mesh_x, mesh_y = np.meshgrid(terrain.x_m, terrain.y_m)
    im = axes[0].pcolormesh(mesh_x, mesh_y, terrain.heights_m, cmap='terrain', shading='auto', rasterized=True)
    axes[0].plot(midpoint_xy[:, 0], midpoint_xy[:, 1], 'k-', lw=1, label='Beam midpoint route')
    for index, label, color in zip(feature_indices, labels, colors):
        point = midpoint_xy[index]
        radius = (40-truth[index])*np.tan(np.deg2rad(args.beamwidth_deg)/2)
        axes[0].add_patch(Circle(point-[1, 0], radius, edgecolor=color, facecolor='none', lw=2))
        axes[0].add_patch(Circle(point+[1, 0], radius, edgecolor=color, facecolor='none', lw=1, ls='--'))
        axes[0].annotate(label, point, xytext=(8, 8), textcoords='offset points', color=color, fontsize=9)
    axes[0].set(xlabel='x (m)', ylabel='y (m)', aspect='equal', title='Route and approximate individual-antenna half-power footprints')
    fig.colorbar(im, ax=axes[0], label='Elevation (m)')
    axes[1].plot(distance, truth, 'k-', lw=2, label='DEM under beam midpoint (reference)')
    axes[1].plot(distance, measured['terrain'], color='#2266bb', marker='.', markersize=3, label='Height coordinate of I/Q peak')
    axes[1].plot(distance, measured['ground'], color='gray', ls='--', label='Flat-control I/Q peak')
    guides(axes[1])
    axes[1].set(xlabel='Distance along flight line (m)', ylabel='Elevation / equivalent height (m)', ylim=(-3, 33), title='Independent comparison: DEM reference versus received-data peak')
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=.2)
    save(fig, 'terrain_scan_geometry')

    fig, ax = plt.subplots(figsize=(11, 5), layout='constrained')
    ax.plot(length, relative['ground'][feature_indices[1]], color='gray', lw=2, label='Flat ground')
    expected_lengths = 2*np.sqrt((40-truth)**2+1)
    for index, label, color in zip(feature_indices, labels, colors):
        ax.plot(length, relative['terrain'][index], color=color, lw=1.8, label=f'{label}, h={truth[index]:.1f} m')
        ax.axvline(expected_lengths[index], color=color, ls=':', alpha=.8)
    ax.set(xlabel='Total TX–surface–RX path length cτ (m)', ylabel='Compressed voltage power (dB, shared reference)',
           ylim=(-45, 3), xlim=(10, 100), title='I/Q delay cuts: raised ground arrives earlier\nDotted lines are geometric midpoint references; they do not generate the I/Q')
    ax.legend(fontsize=9)
    ax.grid(alpha=.2)
    save(fig, 'terrain_delay_cuts')

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, sharey=True, layout='constrained')
    for ax, name, bandwidth in zip(axes, ('terrain_20mhz', 'terrain'), (20, 200)):
        im = ax.pcolormesh(xedges, yedges, relative[name].T, cmap='magma', vmin=-40, vmax=0, rasterized=True)
        ax.set(ylabel='Equivalent height (m)', ylim=(-3, 33), title=f'{bandwidth} MHz chirp; total path-length resolution {C/(bandwidth*1e6):.1f} m')
        guides(ax)
    axes[-1].set_xlabel('Distance along flight line (m)')
    fig.colorbar(im, ax=axes, label='Pulse-compressed voltage power (dB, shared reference)')
    fig.suptitle('Bandwidth control: identical traced paths, beam and pulse energy\nOnly the transmitted chirp bandwidth changes')
    save(fig, 'terrain_bandwidth_comparison')

    np.savez_compressed(args.output_dir/'terrain_scan_iq.npz',
        iq_flat=series['ground']['iq'], iq_dem=series['terrain']['iq'], iq_dem_20mhz=series['terrain_20mhz']['iq'],
        compressed_flat=series['ground']['compressed'], compressed_dem=series['terrain']['compressed'],
        compressed_dem_20mhz=series['terrain_20mhz']['compressed'],
        distance_m=distance, epoch_s=epochs, pulse_indices=pulse_indices, tx_positions_m=positions,
        rx_positions_m=positions+[2, 0, 0], sample_rate_hz=500e6, carrier_hz=24.125e9,
        bandwidth_hz=200e6, pulse_width_s=2e-6, pri_s=.005, impedance_ohm=50., transmit_power_w=1.,
        path_length_m=length, equivalent_height_m=heights, dem_midpoint_height_reference_m=truth,
        feature_indices=feature_indices, noise_enabled=False)
    error = measured['terrain']-truth
    summary = {'scope': 'Focused one-TX/one-RX terrain demonstration, not the 100-TX throughput benchmark',
         'arguments': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
         'versions': {'sionna_rt': rt.__version__, 'mitsuba': mi.__version__, 'drjit': dr.__version__, 'backend': mi.variant()},
         'execution': {'propagation': mi.variant(), 'iq_renderer': 'direct-cuda' if args.backend == 'cuda' else 'numpy', 'analysis_and_plotting': 'host SciPy/Matplotlib', 'pascal_compat': args.pascal_compat},
         'geometry': {'altitude_m': 40, 'baseline_m': 2, 'speed_m_s': 10, 'distance_m': distance.tolist(),
                      'epoch_s': epochs.tolist(), 'beamwidth_deg': args.beamwidth_deg, 'peak_gain_dbi': peak_gain},
         'waveform': {'bandwidth_hz': 200e6, 'control_bandwidth_hz': 20e6, 'sample_rate_hz': 500e6,
                      'pulse_width_s': 2e-6, 'receive_window_s': 3e-6, 'pulse_hz': 200, 'noise': False},
         'features': [{'label': label, 'index': index, 'distance_m': float(distance[index]),
                       'dem_height_m': float(truth[index]), 'iq_peak_height_m': float(measured['terrain'][index]),
                       'midpoint_expected_path_length_m': float(expected_lengths[index])}
                      for index, label in zip(feature_indices, labels)],
         'dem_height_reference_m': truth.tolist(), 'iq_peak_height_dem_m': measured['terrain'].tolist(),
         'iq_peak_height_flat_m': measured['ground'].tolist(),
         'comparison': {'dem_vs_iq_peak_correlation': float(np.corrcoef(truth, measured['terrain'])[0, 1]),
                        'rmse_m': float(np.sqrt(np.mean(error**2))), 'median_absolute_error_m': float(np.median(np.abs(error)))},
         'retained_paths': records,
         'processing': 'Complex voltage from all Sionna LoS/specular/diffuse paths, linear matched filter / pulse energy; no DEM values enter IQ or peak estimator',
         'height_coordinate': '40 - sqrt((c*tau/2)^2 - (baseline/2)^2); assumes midpoint scattering, not a unique inversion for off-nadir returns',
         'limitations': ['Synthetic narrow antenna, not the previous hardware profile', 'Same DEM and homogeneous material as original fixture',
                        'No persistent calibrated terrain speckle or SAR processing', 'No GPU performance or VRAM inference']}
    (args.output_dir/'terrain_signature_data.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary['comparison']), flush=True)
    print(f'Saved terrain signature figures and raw complex I/Q to {args.output_dir}', flush=True)


if __name__ == '__main__':
    main()
