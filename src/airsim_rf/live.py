"""Finite live ProjectAirSim-to-SDR recording, with explicit GPU backend selection."""
import argparse
import json
from pathlib import Path
from time import perf_counter


def validate_inputs(config_path):
    """Check finite source files and provenance without CUDA or a simulator."""
    from hashlib import sha256
    import numpy as np
    from .terrain import scene_provenance
    path=Path(config_path).resolve();config=json.loads(path.read_text())
    local=lambda name: (path.parent/name).resolve()
    profile=config['receiver_profile'];rate=float(profile['sample_rate_hz'])
    if not np.isfinite(rate) or rate <= 0:
        raise ValueError('Positive finite sample rate required')
    config_dir=local(config['sim_config'])
    scene=(config_dir/config['scene']).resolve()
    if not scene.is_file():
        raise ValueError(f'Missing ProjectAirSim scene configuration: {scene}')
    radios=config['radios'];sources={}
    for name,radio in radios.items():
        if 'waveform_npy' not in radio:
            continue
        waveform=local(radio['waveform_npy']);values=np.load(waveform,allow_pickle=False)
        if values.ndim!=1 or not np.iscomplexobj(values) or not values.size or not np.isfinite(values).all():
            raise ValueError(f'{name}: nonempty finite 1-D complex waveform required')
        power=float(radio['transmit_power_w']);bounds=np.asarray(radio['baseband_frequency_bounds_hz'],float)
        if not np.isfinite(power) or power<=0 or bounds.shape!=(2,) or not np.isfinite(bounds).all() or bounds[0]>bounds[1] or np.max(abs(bounds))>=rate/2:
            raise ValueError(f'{name}: invalid power or frequency bounds')
        sources[name]={'sha256':sha256(waveform.read_bytes()).hexdigest(),'samples':len(values),
            'signal_seconds':len(values)/rate,'mean_sample_power':float(np.mean(abs(values)**2))}
    if not sources or len(sources)==len(radios):
        raise ValueError('At least one transmitter and receiver required')
    return {'configuration_sha256':sha256(path.read_bytes()).hexdigest(),
        'rf_scene':scene_provenance(local(config['rf_scene'])),
        'sim_config_sha256':{p.name:sha256(p.read_bytes()).hexdigest() for p in config_dir.glob('*.json*')},
        'waveforms':sources}


def record(world, robots, receiver, output, *, updates, advance_ns, max_samples,
           mounts_body_m=None, provenance=None):
    """Write contiguous ci16_le captures; checkpoint metadata after every update."""
    from .sdr_bridge import AirSimSDRBridge
    if not receiver.continuous:
        raise ValueError('Live recording requires a continuous receiver')
    if min(updates, advance_ns, max_samples) < 1:
        raise ValueError('Counts and interval must be positive')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    bridge = AirSimSDRBridge(world, robots, receiver, mounts_body_m=mounts_body_m)
    rows, offsets = [], {name: 0 for name in receiver.scene.receivers}
    metadata = {name: {'global': {'core:datatype': 'ci16_le',
        'core:version': '1.2.6', 'core:sample_rate': receiver.profile.sample_rate_hz,
        'core:description': 'Simulated signed 12-bit SDR I/Q in int16 containers; uncalibrated'},
        'captures': [], 'annotations': []} for name in offsets}
    manifest = {'status': 'running', 'scope': 'live_airsim_rf_recording',
        'sample_rate_hz': receiver.profile.sample_rate_hz,
        'timing_includes': 'physics advance/RPC, snapshot, RF capture, data and metadata writes; no fsync',
        'rows': rows, 'provenance': provenance or {}}
    def checkpoint():
        for name, value in metadata.items():
            (output/f'{name}.sigmf-meta').write_text(json.dumps(value, indent=2)+'\n')
        (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    checkpoint()
    try:
        for _ in range(updates):
            tick = perf_counter()
            captures = bridge.capture_elapsed(advance_ns=advance_ns, max_samples=max_samples)
            if set(captures) != set(offsets):
                raise RuntimeError('Capture receiver names differ from the configured scene')
            counts = set()
            for name, capture in captures.items():
                count = len(capture.adc_codes)
                counts.add(count)
                with (output/f'{name}.sigmf-data').open('ab') as stream:
                    capture.adc_codes.astype('<i2').tofile(stream)
                metadata[name]['captures'].append({'core:sample_start': offsets[name],
                    'core:frequency': receiver.profile.carrier_hz,
                    'airsim_rf:sim_time_ns': capture.sim_time_ns,
                    'airsim_rf:volts_per_count': capture.volts_per_count,
                    'airsim_rf:clipped_component_fraction': capture.clipped_component_fraction})
                offsets[name] += count
            if len(counts) != 1:
                raise RuntimeError('Receiver sample counts differ')
            row = {'sim_time_ns': next(iter(captures.values())).sim_time_ns,
                   'samples_per_receiver': counts.pop()}
            rows.append(row)
            checkpoint()
            row['wall_ms'] = (perf_counter()-tick)*1000
        manifest['status'] = 'complete'
    except BaseException as error:
        manifest['status'] = 'failed'
        manifest['error'] = str(error)
        raise
    finally:
        signal_s = sum(r['samples_per_receiver'] for r in rows)/receiver.profile.sample_rate_hz
        manifest['signal_seconds_per_receiver'] = signal_s
        manifest['wall_seconds_per_signal_second'] = (sum(r.get('wall_ms', 0) for r in rows)/1000/signal_s if signal_s else None)
        checkpoint()
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--updates', type=int, default=10)
    parser.add_argument('--advance-ns', type=int, default=10_000_000)
    parser.add_argument('--max-samples', type=int, default=2_000_000)
    parser.add_argument('--pascal-compat', action='store_true')
    parser.add_argument('--check-config', action='store_true', help='Validate files/provenance without a server or GPU')
    args = parser.parse_args()
    if min(args.updates, args.advance_ns, args.max_samples) < 1:
        parser.error('Counts and interval must be positive')
    input_provenance=validate_inputs(args.config)
    if args.check_config:
        print(json.dumps(input_provenance,indent=2))
        return
    config = json.loads(args.config.read_text())
    import mitsuba as mi
    mi.set_variant('cuda_ad_mono_polarized')
    if args.pascal_compat:
        from .p100_compat import enable_pascal_compat
        enable_pascal_compat()
    import sionna.rt as rt
    import numpy as np
    import cupy as cp
    import drjit as dr
    cp.cuda.runtime.getDeviceCount()
    cp.zeros(1).sum().get()  # Fail before connecting if CUDA rendering is unavailable.
    from projectairsim import Drone, ProjectAirSimClient, World
    from .sampled_waveform import SampledWaveform
    from .sdr import PlutoSDRProfile, SDREmitter, SDRNetworkReceiver
    def local(name):
        return (args.config.parent/name).resolve()
    scene = rt.load_scene(str(local(config['rf_scene'])))
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='hw_dipole', polarization='V')
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='hw_dipole', polarization='V')
    profile = PlutoSDRProfile(**config.get('receiver_profile', {}))
    scene.frequency = profile.carrier_hz
    client = ProjectAirSimClient(address=config['address'])
    client.connect()
    try:
        world = World(client, config['scene'], sim_config_path=str(local(config['sim_config'])))
        world.pause()
        origin = int(world.get_sim_time())
        emitters, robots = {}, {}
        for name, radio in config['radios'].items():
            is_tx = 'waveform_npy' in radio
            scene.add((rt.Transmitter if is_tx else rt.Receiver)(name, position=[0, 0, 1]))
            robots[name] = Drone(client, world, radio['robot'])
            if is_tx:
                values = np.load(local(radio['waveform_npy']), allow_pickle=False)
                if values.ndim != 1 or not np.iscomplexobj(values):
                    raise ValueError('waveform_npy must contain a one-dimensional complex array')
                emitters[name] = SDREmitter(SampledWaveform(values, profile.sample_rate_hz,
                    origin, boundary='zero'), transmit_power_w=radio['transmit_power_w'],
                    baseband_frequency_bounds_hz=tuple(radio['baseband_frequency_bounds_hz']))
        receiver = SDRNetworkReceiver(scene, emitters, profile, renderer='basis-cuda',
            continuous=True, samples_per_link=config.get('samples_per_link', 1028))
        mounts = {n: r.get('mount_body_m', [0, 0, 0]) for n, r in config['radios'].items()}
        result = record(world, robots, receiver, args.output, updates=args.updates,
            advance_ns=args.advance_ns, max_samples=args.max_samples, mounts_body_m=mounts,
            provenance={'inputs':input_provenance, 'configuration': config, 'propagation_backend': mi.variant(),
                'renderer': 'basis-cuda', 'pascal_compat': args.pascal_compat,
                'sionna_rt': rt.__version__, 'mitsuba': mi.__version__,
                'drjit': dr.__version__, 'cupy': cp.__version__})
        print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))
    finally:
        client.disconnect()


if __name__ == '__main__':
    main()
