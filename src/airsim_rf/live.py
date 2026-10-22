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
    from .scenario import propagation_options, antenna_options
    from .geometry import read_bundle
    from .sdr import PlutoSDRProfile
    import re
    path=Path(config_path).resolve();config=json.loads(path.read_text())
    required={'address','scene','sim_config','rf_scene','receiver_profile','radios'}
    allowed=required|{'antennas','propagation','samples_per_link','geometry_bundle','geometry_placement'}
    if not isinstance(config,dict) or required-set(config) or set(config)-allowed:
        raise ValueError(f'Live configuration requires {sorted(required)}; missing/unknown keys: '
                         f'{sorted(required-set(config)) if isinstance(config,dict) else "not an object"} / '
                         f'{sorted(set(config)-allowed) if isinstance(config,dict) else "not an object"}')
    for key in ('address','scene','sim_config','rf_scene'):
        if not isinstance(config[key],str) or not config[key].strip():
            raise ValueError(f'{key} must be a nonempty string')
    local=lambda name: (path.parent/name).resolve()
    options=propagation_options(config);antennas=antenna_options(config)
    profile=config['receiver_profile']
    if not isinstance(profile,dict):
        raise ValueError('receiver_profile must be an object of PlutoSDRProfile settings')
    try:
        rate=PlutoSDRProfile(**profile).sample_rate_hz
    except TypeError as error:
        raise ValueError(f'Invalid receiver_profile settings: {error}') from error
    if not np.isfinite(rate) or rate <= 0:
        raise ValueError('Positive finite sample rate required')
    config_dir=local(config['sim_config'])
    scene=(config_dir/config['scene']).resolve()
    if not scene.is_file():
        raise ValueError(f'Missing ProjectAirSim scene configuration: {scene}')
    from .preflight import read_sim_config
    simulator=read_sim_config(scene)
    actors=simulator.get('actors',[])
    if not isinstance(actors,list) or any(not isinstance(actor,dict) for actor in actors):
        raise ValueError('Simulator scene actors must be a list of objects')
    names=[actor.get('name') for actor in actors if actor.get('type')=='robot']
    if any(not isinstance(name,str) or not name for name in names) or len(names)!=len(set(names)):
        raise ValueError('Simulator robot names must be nonempty and unique')
    for actor in actors:
        if actor.get('type')=='robot':
            robot_config=actor.get('robot-config')
            if not isinstance(robot_config,str) or not (config_dir/robot_config).is_file():
                raise ValueError(f'{actor.get("name")}: missing robot-config file relative to sim_config: {robot_config!r}')
    geometry = None
    placement_mode = config.get('geometry_placement', 'existing')
    if placement_mode not in ('existing', 'spawn'):
        raise ValueError('geometry_placement must be existing or spawn')
    if 'geometry_placement' in config and 'geometry_bundle' not in config:
        raise ValueError('geometry_placement requires geometry_bundle')
    if 'geometry_bundle' in config:
        bundle = local(config['geometry_bundle'])
        document, manifest, bindings = read_bundle(bundle)
        if local(config['rf_scene']) != bundle/'scene.xml':
            raise ValueError('rf_scene must point to geometry_bundle/scene.xml')
        if bindings is None:
            raise ValueError('Live geometry bundle requires simulator bindings')
        from .geometry_sync import AirSimGeometryBinding
        AirSimGeometryBinding(document, bindings)
        geometry = {'manifest': manifest, 'bindings': bindings,
                    'placement': placement_mode,
                    'policy': 'static bound objects; pose/scale checked at interval start and end'}
    radios=config['radios'];sources={}
    if not isinstance(radios,dict) or not radios:
        raise ValueError('radios must be a nonempty object mapping radio IDs to settings')
    for name,radio in radios.items():
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',name):
            raise ValueError('Radio IDs must use letters, digits, underscores or hyphens')
        if not isinstance(radio,dict) or set(radio)-{'robot','mount_body_m','waveform_npy','transmit_power_w','baseband_frequency_bounds_hz'}:
            raise ValueError(f'{name}: radio settings contain unknown keys or are not an object')
        if not isinstance(radio.get('robot'),str) or not radio['robot'].strip():
            raise ValueError(f'{name}: robot name is required')
        if radio['robot'] not in names:
            raise ValueError(f'{name}: robot {radio["robot"]!r} is absent from simulator scene {scene.name}')
        mount=np.asarray(radio.get('mount_body_m',[0,0,0]),dtype=float)
        if mount.shape!=(3,) or not np.isfinite(mount).all():
            raise ValueError(f'{name}: mount_body_m must contain three finite coordinates')
        if 'waveform_npy' not in radio:
            if set(radio)&{'transmit_power_w','baseband_frequency_bounds_hz'}:
                raise ValueError(f'{name}: transmitter settings require waveform_npy')
            continue
        if not {'transmit_power_w','baseband_frequency_bounds_hz'} <= set(radio):
            raise ValueError(f'{name}: waveform_npy requires transmit_power_w and baseband_frequency_bounds_hz')
        if not isinstance(radio['waveform_npy'],str) or not radio['waveform_npy']:
            raise ValueError(f'{name}: waveform_npy must be a file path string')
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
    return {'propagation_options':options, 'antenna_options':antennas, 'configuration_sha256':sha256(path.read_bytes()).hexdigest(),
        'rf_scene':scene_provenance(local(config['rf_scene'])), 'geometry_bundle': geometry,
        'sim_config_sha256':{str(p.relative_to(config_dir)):sha256(p.read_bytes()).hexdigest() for p in config_dir.rglob('*.json*')},
        'waveforms':sources}


def record(world, robots, receiver, output, *, updates, advance_ns, max_samples,
           mounts_body_m=None, provenance=None, on_capture=None, geometry_binding=None):
    """Write contiguous ci16_le captures; checkpoint metadata after every update."""
    from .sdr_bridge import AirSimSDRBridge
    if not receiver.continuous:
        raise ValueError('Live recording requires a continuous receiver')
    if min(updates, advance_ns, max_samples) < 1:
        raise ValueError('Counts and interval must be positive')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    bridge = AirSimSDRBridge(world, robots, receiver, mounts_body_m=mounts_body_m,
        geometry_guard=geometry_binding.require_static_match if geometry_binding is not None else None)
    rows, offsets = [], {name: 0 for name in receiver.scene.receivers}
    metadata = {name: {'global': {'core:datatype': 'ci16_le',
        'core:version': '1.2.6', 'core:sample_rate': receiver.profile.sample_rate_hz,
        'core:extensions': [{'name':'airsim_rf','version':'0.1.0','optional':True}],
        'core:description': 'Simulated signed 12-bit SDR I/Q in int16 containers; uncalibrated'},
        'captures': [], 'annotations': []} for name in offsets}
    manifest = {'status': 'running', 'scope': 'live_airsim_rf_recording',
        'sample_rate_hz': receiver.profile.sample_rate_hz,
        'timing_includes': 'physics advance/RPC, snapshot, RF capture, data and metadata writes, synchronous on_capture callback; no fsync',
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
            if geometry_binding is not None:
                row['geometry'] = bridge.geometry_report
            rows.append(row)
            checkpoint()
            if on_capture is not None:
                for name, capture in captures.items():
                    on_capture(name, capture)
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
    parser.add_argument('--output', type=Path)
    parser.add_argument('--updates', type=int, default=10)
    parser.add_argument('--advance-ns', type=int, default=10_000_000)
    parser.add_argument('--max-samples', type=int, default=2_000_000)
    parser.add_argument('--pascal-compat', action='store_true')
    parser.add_argument('--check-config', action='store_true', help='Validate files/provenance without a server or GPU')
    args = parser.parse_args()
    if min(args.updates, args.advance_ns, args.max_samples) < 1:
        parser.error('Counts and interval must be positive')
    if not args.check_config and args.output is None:
        parser.error('--output is required when recording')
    try:
        if args.check_config:
            input_provenance=validate_inputs(args.config)
            print(json.dumps(input_provenance,indent=2))
            return
        result = run(args.config, args.output, updates=args.updates, advance_ns=args.advance_ns,
            max_samples=args.max_samples, pascal_compat=args.pascal_compat)
        print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,ImportError) as error:
        parser.exit(2,f'airsim-rf-live: {error}\nRun airsim-rf preflight with the same configuration and capture counts to diagnose setup.\n')


def run(config_path, output, *, updates=10, advance_ns=10_000_000,
        max_samples=2_000_000, pascal_compat=False, on_capture=None):
    """Load a scenario, connect/step ProjectAirSim, record and optionally process I/Q.

    on_capture(receiver_id, SDRCapture) runs synchronously after each window is
    written. Exceptions stop the run and mark the manifest failed. The simulator
    is left paused. This owns the simulator's stepping; do not run another client
    that advances or reloads this world concurrently.
    """
    from types import SimpleNamespace
    if min(updates, advance_ns, max_samples) < 1:
        raise ValueError('Counts and interval must be positive')
    if on_capture is not None and not callable(on_capture):
        raise ValueError('on_capture must be callable')
    args=SimpleNamespace(config=Path(config_path), output=Path(output), updates=updates,
        advance_ns=advance_ns, max_samples=max_samples, pascal_compat=pascal_compat)
    if args.output.exists():
        raise ValueError(f'Output already exists; choose a new recording directory: {args.output}')
    from .preflight import check
    preflight_report=check(args.config,output=args.output,updates=updates,advance_ns=advance_ns,max_samples=max_samples)
    input_provenance=preflight_report['inputs']
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
    geometry_binding = None
    if 'geometry_bundle' in config:
        from .geometry import read_bundle
        from .geometry_sync import AirSimGeometryBinding
        document, manifest, bindings = read_bundle(local(config['geometry_bundle']))
        geometry_binding = AirSimGeometryBinding(document, bindings)
        scene = rt.load_scene(str(local(config['rf_scene'])), merge_shapes=False)
        if set(scene.objects) != set(manifest['object_map'].values()):
            raise RuntimeError('Sionna object identities differ from the geometry bundle; adapter qualification required')
    else:
        scene = rt.load_scene(str(local(config['rf_scene'])))
    scene.tx_array = rt.PlanarArray(**input_provenance['antenna_options']['tx'])
    scene.rx_array = rt.PlanarArray(**input_provenance['antenna_options']['rx'])
    profile = PlutoSDRProfile(**config.get('receiver_profile', {}))
    scene.frequency = profile.carrier_hz
    client = ProjectAirSimClient(address=config['address'])
    client.connect()
    try:
        world = World(client, config['scene'], sim_config_path=str(local(config['sim_config'])))
        world.pause()
        if geometry_binding is not None:
            if config.get('geometry_placement', 'existing') == 'spawn':
                from .geometry_sync import spawn_placements
                spawn_placements(world, geometry_binding.plan)
            # Existing mode only reads actors; spawning requires explicit config.
            geometry_binding.require_static_match(world, int(world.get_sim_time()))
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
            continuous=True, **input_provenance['propagation_options'])
        mounts = {n: r.get('mount_body_m', [0, 0, 0]) for n, r in config['radios'].items()}
        result = record(world, robots, receiver, args.output, updates=args.updates,
            advance_ns=args.advance_ns, max_samples=args.max_samples, mounts_body_m=mounts, on_capture=on_capture,
            geometry_binding=geometry_binding,
            provenance={'inputs':input_provenance, 'preflight_plan':preflight_report['plan'], 'configuration': config, 'propagation_backend': mi.variant(),
                'renderer': 'basis-cuda', 'pascal_compat': args.pascal_compat,
                'sionna_rt': rt.__version__, 'mitsuba': mi.__version__,
                'drjit': dr.__version__, 'cupy': cp.__version__})
        return result
    finally:
        client.disconnect()


if __name__ == '__main__':
    main()
