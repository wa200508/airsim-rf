"""Draw physical context from the recorded sensing datasets; no new simulation."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('docs/figures'))
    parser.add_argument('--output-dir', type=Path, default=Path('docs/figures'))
    args = parser.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.hashsalt': 'airsim-rf-scenarios'})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    radio = json.loads((args.data_dir/'pluto_esm_report.json').read_text())
    terrain = json.loads((args.data_dir/'terrain_signature_data.json').read_text())
    radar = np.load(args.data_dir/'terrain_scan_iq.npz', allow_pickle=False)

    def save(fig, name):
        for suffix in ('png', 'svg'):
            fig.savefig(args.output_dir/f'{name}.{suffix}', dpi=180, bbox_inches='tight',
                        metadata={'Date': None} if suffix == 'svg' else None)
        plt.close(fig)

    # Actual RF Cartesian geometry, not an artistic reconstruction of an AirSim flight.
    start = np.asarray(radio['positions_at_start_m'])
    velocity = np.asarray(radio['velocities_m_s'])
    epoch = radio['epochs_s'][-1]
    end = start+epoch*velocity
    colors = ['#c45d00', '#0072b2', '#333333', '#555555']
    fig = plt.figure(figsize=(11, 6.2), layout='constrained')
    grid = fig.add_gridspec(2, 2, width_ratios=[1.3, 1], height_ratios=[1, .3])
    ax = fig.add_subplot(grid[:, 0])
    notes = fig.add_subplot(grid[0, 1]); notes.axis('off')
    timeline = fig.add_subplot(grid[1, 1])
    for tx in range(2):
        for rx in range(2, 4):
            ax.plot(*np.stack([end[tx, :2], end[rx, :2]]).T,
                    color=colors[tx], alpha=.45, lw=1, ls=':')
    offsets = [(0, -32), (-85, 12), (-90, 12), (12, -8)]
    for i, label in enumerate(['Beacon A', 'Beacon B', 'Receiver 1', 'Receiver 2']):
        marker = '*' if i < 2 else '^'
        ax.scatter(*start[i, :2], marker=marker, s=90, facecolors='none',
                   edgecolors=colors[i], zorder=3)
        ax.annotate('', end[i, :2], start[i, :2],
                    arrowprops={'arrowstyle': '->', 'color': colors[i], 'lw': 2})
        ax.scatter(*end[i, :2], marker=marker, s=140, color=colors[i], zorder=4)
        detail = (f"{radio['emitter_baseband_hz'][i]/1e3:+.0f} kHz CW, "
                  f"{radio['emitter_port_power_dbm'][i]:.0f} dBm" if i < 2
                  else 'Passive listening')
        ax.annotate(f'{label}\n{detail}\nz = {end[i,2]:g} m', end[i, :2],
                    xytext=offsets[i], textcoords='offset points', fontsize=9,
                    color=colors[i], bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': .9})
    ax.plot([], [], 'o', mfc='none', mec='k', label='Open symbol: t = 0 s')
    ax.plot([], [], 'o', color='k', label=f'Filled symbol: t = {epoch:g} s')
    ax.plot([], [], ':', color='gray', label='Illustrative emitter-to-receiver links')
    ax.legend(loc='upper left', fontsize=8, framealpha=.95)
    ax.set(xlabel='RF x (m)', ylabel='RF y (m)', xlim=(-80, 70), ylim=(-70, 85), aspect='equal')
    ax.grid(alpha=.15)
    ax.set_title('ESM / passive reception: actual plan-view geometry', loc='left', fontsize=12)
    tones = np.asarray(radio['expected_tone_hz_excluding_doppler'])/1e3
    power_difference = radio['emitter_port_power_dbm'][0]-radio['emitter_port_power_dbm'][1]
    notes.text(0, 1, 'What should appear in the waterfall?', va='top', fontsize=12, weight='bold')
    notes.text(0, .88,
        'Each receiver hears both continuous-wave beacons.\n'
        f'A is transmitted {power_difference:g} dB stronger than B. Received\n'
        'strength also depends on distance and propagation.\n\n'
        'Two narrow, almost vertical frequency bands:\n'
        f'  Receiver 1: A ≈ {tones[0,0]:+.1f}, B ≈ {tones[0,1]:+.1f} kHz\n'
        f'  Receiver 2: A ≈ {tones[1,0]:+.1f}, B ≈ {tones[1,1]:+.1f} kHz\n'
        '(Recorded clock offsets included; path Doppler excluded.)\n\n'
        'Different receiver clocks shift both bands.\n'
        'Terrain reflections / diffuse paths combine with\n'
        'direct reception; these alter amplitude and phase.\n\n'
        'The waterfall spans only ≈2.048 ms at t = 5.5 s.\n'
        'At 3 m/s a receiver moves only ≈6 mm in that time:\n'
        'expect steady tones, not a sweep across the plot.', va='top', fontsize=9.5, linespacing=1.45)
    epochs = np.asarray(radio['epochs_s'])
    timeline.plot(epochs, np.zeros_like(epochs), '|', color='gray', ms=14)
    timeline.plot(epoch, 0, '|', color='#c45d00', ms=19, mew=3)
    timeline.set(xlabel='Simulation epoch (s)', xlim=(-.1, epoch+.15), ylim=(-.4, .4), yticks=[])
    timeline.set_title('12 separate captures; waterfall uses the last one', fontsize=9)
    timeline.text(.5, .22, 'Capture widths exaggerated; gaps are not filled',
                  transform=timeline.transAxes, ha='center', fontsize=8)
    fig.suptitle('Two moving beacons → two passive SDR receivers', fontsize=15, weight='bold')
    save(fig, 'sensing_esm_scenario')

    distance = radar['distance_m']
    height = np.asarray(terrain['dem_height_reference_m'])
    altitude = terrain['geometry']['altitude_m']
    tx, rx = radar['tx_positions_m'], radar['rx_positions_m']
    route_direction = (tx[-1]-tx[0])/np.linalg.norm(tx[-1]-tx[0])
    projected_half_baseline = np.dot(rx[0]-tx[0], route_direction)/2
    fig, (ax, notes) = plt.subplots(2, 1, figsize=(11, 6.5), layout='constrained',
                                  gridspec_kw={'height_ratios': [2.2, 1]})
    ax.fill_between(distance, -2, height, color='#d7ddc9', alpha=.8)
    ax.plot(distance, height, color='#586d3d', lw=2, label='Recorded DEM beneath baseline midpoint')
    ax.axhline(0, color='gray', ls=':', lw=1, label='Flat-ground control: z = 0 m')
    ax.plot([distance[0], distance[-1]], [altitude, altitude], '--', color='gray', lw=1)
    ax.annotate('TX/RX pair moves at 10 m/s; altitude z = 40 m',
                xy=(125, altitude), xytext=(10, altitude+5),
                arrowprops={'arrowstyle': '->', 'color': '#333333'}, fontsize=10)
    for feature, color in zip(terrain['features'], ['#c45d00', '#0072b2', '#7a5195']):
        d, h = feature['distance_m'], feature['dem_height_m']
        ax.plot([d-projected_half_baseline, d, d+projected_half_baseline],
                [altitude, h, altitude], color=color, lw=1.3)
        ax.scatter([d-projected_half_baseline, d+projected_half_baseline],
                   [altitude, altitude], marker='v', s=35, color=color, zorder=4)
        ax.scatter(d, h, s=30, color=color, zorder=4)
        ax.text(d+3, 23, f"{feature['label']}\nheight {h:.2f} m\n"
                f"reference cτ = {feature['midpoint_expected_path_length_m']:.2f} m",
                fontsize=9, color=color)
    ax.set(xlabel='Distance along scan route (m)', ylabel='RF height z (m)',
           xlim=(-5, distance[-1]+5), ylim=(-2, 50))
    ax.set_title('Route elevation view — vertical scale enlarged', loc='left', fontsize=12)
    ax.legend(loc='lower left', fontsize=8)
    ax.grid(alpha=.15)
    notes.axis('off')
    notes.text(0, 1, 'What should appear in the matched-filter profiles?', va='top',
               fontsize=12, weight='bold')
    notes.text(0, .75,
        'TX → ground → RX. A hill shortens the travel path, so its echo peak moves left (smaller cτ).\n'
        'The swale is near z = 0 m, so its echo is closer to the flat-ground path length of ≈80 m.\n'
        'The TX–RX baseline is 2 m in RF x; the separation drawn above is its projection onto the route.\n'
        'Colored V paths are midpoint reference geometry, not extracted traced rays. Actual multipath\n'
        'creates broadened / multiple peaks. 200 MHz gives finer delay separation than 20 MHz.',
        fontsize=10, va='top', linespacing=1.5)
    fig.suptitle('Downward-looking bistatic radar → terrain echoes', fontsize=15, weight='bold')
    save(fig, 'sensing_radar_scenario')
    sources = ('pluto_esm_report.json', 'terrain_signature_data.json', 'terrain_scan_iq.npz')
    manifest = {
        'scope': 'Scenario illustrations from recorded P100 geometry; no new propagation or I/Q',
        'source_sha256': {name: sha256((args.data_dir/name).read_bytes()).hexdigest() for name in sources},
        'figures': ['sensing_esm_scenario', 'sensing_radar_scenario'],
        'esm': {'start_positions_m': start.tolist(), 'final_positions_m': end.tolist(),
                'final_epoch_s': epoch, 'nominal_carrier_hz': radio['profile']['carrier_hz'],
                'link_lines': 'Illustrative device associations, not traced rays'},
        'radar': {'altitude_m': altitude, 'baseline_m': float(np.linalg.norm(rx[0]-tx[0])),
                  'projected_baseline_m': float(2*projected_half_baseline),
                  'reference_paths': 'Illustrative midpoint geometry, not extracted traced rays',
                  'vertical_scale': 'Enlarged relative to horizontal; not equal aspect'},
    }
    (args.output_dir/'sensing_scenarios.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    main()
