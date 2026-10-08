"""Moving terrain scene -> private arbitrary I/Q -> propagation -> ADC -> HTTP consumer.

The default pose source implements the AirSim bridge contract deterministically.
Use --airsim-config for a live ProjectAirSim physics/RPC run; no fallback is used.
"""
import argparse
from dataclasses import replace
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import platform
import subprocess
from pathlib import Path
import statistics
import struct
import threading
from time import perf_counter
import urllib.request

import numpy as np

from airsim_rf.sdr import PlutoSDRProfile, SDREmitter, SDRNetworkReceiver
from airsim_rf.sdr_bridge import AirSimSDRBridge
from airsim_rf.sampled_waveform import SampledWaveform

ROOT = Path(__file__).resolve().parents[1]
FS = 2_000_000


class TrajectoryWorld:
    """Deterministic kinematics, not an AirSim physics engine."""
    def __init__(self):
        self.epoch = 0

    def is_paused(self):
        return True

    def get_sim_time(self):
        return self.epoch

    def continue_until_sim_time(self, requested, **kwargs):
        self.epoch = requested


class TrajectoryRobot:
    def __init__(self, world, position, velocity):
        self.world, self.position, self.velocity = world, np.asarray(position), np.asarray(velocity)

    def get_ground_truth_kinematics(self):
        # A smooth curved trajectory: velocity is the derivative of position.
        t = self.world.epoch*1e-9
        position = self.position+self.velocity*t+np.array([2*np.sin(.7*t), 2*(np.cos(.7*t)-1), 0])
        velocity = self.velocity+np.array([1.4*np.cos(.7*t), -1.4*np.sin(.7*t), 0])
        ned = np.array([1., -1., -1.])
        vector = lambda x: dict(zip(('x', 'y', 'z'), map(float, x*ned)))
        return {'kinematics': {'pose': {'position': vector(position),
            'orientation': {'w': 1., 'x': 0., 'y': 0., 'z': 0.}},
            'twist': {'linear': vector(velocity), 'angular': {'x': 0., 'y': 0., 'z': 0.}}}}


class PrivateSources:
    """Rolling random sample streams with retained history/lookahead, per transmitter.

    No favorable waveform spectrum or repeated waveform is used for rendering.
    The receiver copies each stream into a private allocation per directed link.
    """
    def __init__(self, names, max_delay_s=100e-6, seed=8123):
        self.guard = int(np.ceil(max_delay_s*FS))+64
        self.rng = {name: np.random.default_rng(s) for name, s in zip(names, np.random.SeedSequence(seed).spawn(len(names)))}
        self.buffers = {}
        self.origin = -self.guard

    def window(self, sample_start, count):
        origin = sample_start-self.guard
        end = sample_start+count+self.guard
        result = {}
        for name, rng in self.rng.items():
            previous = self.buffers.get(name, np.empty(0, complex))
            if origin < self.origin or origin > self.origin+len(previous):
                raise ValueError('Source windows must be consecutive')
            keep = previous[origin-self.origin:]
            needed = end-origin-len(keep)
            fresh = (rng.normal(size=needed)+1j*rng.normal(size=needed))/np.sqrt(2)
            values = np.concatenate((keep, fresh))
            self.buffers[name] = values
            result[name] = SampledWaveform(values, FS, origin*500, 32)
        self.origin = origin
        return result


class Consumer:
    """Actual loopback HTTP delivery, SC16 decode and synchronous file write/readback."""
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        self.paths = []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                payload = self.rfile.read(int(self.headers['Content-Length']))
                seq, ri, count = struct.unpack('<III', payload[:12])
                codes = np.frombuffer(payload[12:], dtype='<i2').reshape(count, 2)
                if codes.min() < -2048 or codes.max() > 2047:
                    raise ValueError('Invalid 12-bit ADC payload')
                path = directory/f'{seq:06d}_rx{ri}.sc16'
                path.write_bytes(payload)
                if path.read_bytes() != payload:
                    raise RuntimeError('Consumer storage readback mismatch')
                owner.paths.append(path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(sha256(payload).hexdigest().encode())

            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        # Loopback does not need an external HTTP proxy.
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def deliver(self, sequence, ri, codes):
        payload = struct.pack('<III', sequence, ri, len(codes))+codes.astype('<i2', copy=False).tobytes()
        request = urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}', data=payload, method='POST')
        with self.http.open(request, timeout=60) as response:
            if response.read().decode() != sha256(payload).hexdigest():
                raise RuntimeError('Consumer acknowledgement mismatch')

    def close(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()


def stats(values):
    return dict(median_ms=float(np.median(values)), std_ms=statistics.stdev(values) if len(values)>1 else None,
                p95_ms=float(np.percentile(values, 95)), mean_ms=statistics.mean(values))


def run(*, output, tx=100, rx=10, iterations=30, warmup=3, renderer='basis-cpu',
        samples_per_link=1028, airsim_config=None, profile_rendering=False, optimizations=True, fused_projection=False, threads=2, propagation_backend=None, pascal_compat=False):
    import mitsuba as mi
    if propagation_backend is None:
        propagation_backend = 'cuda' if mi.variant().startswith('cuda') else 'llvm'
    if not mi.variant().startswith(propagation_backend):
        raise RuntimeError('Requested propagation backend was not initialized before importing Sionna')
    if pascal_compat:
        from airsim_rf.p100_compat import enable_pascal_compat
        enable_pascal_compat(stable_shapes=optimizations)
    import sionna.rt as rt
    import drjit as dr
    dr.set_thread_count(threads)
    if profile_rendering and propagation_backend == 'cuda':
        dr.set_flag(dr.JitFlag.KernelHistory, True)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    scene = rt.load_scene(str(ROOT/'benchmarks/scenes/terrain.xml'))
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='hw_dipole', polarization='V')
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='hw_dipole', polarization='V')
    connection = None
    world = TrajectoryWorld()
    robots = {}
    names = [f'tx{i}' for i in range(tx)]+[f'rx{i}' for i in range(rx)]
    rng = np.random.default_rng(619)
    for i, name in enumerate(names):
        position = [rng.uniform(-60, 60), rng.uniform(-60, 60), rng.uniform(20, 40)]
        velocity = rng.uniform(-8, 8, 3)
        robots[name] = TrajectoryRobot(world, position, velocity)
        scene.add((rt.Transmitter if i<tx else rt.Receiver)(name, position=position, velocity=velocity.tolist()))
    if airsim_config:
        from projectairsim import Drone, ProjectAirSimClient, World
        config = json.loads(Path(airsim_config).read_text())
        if set(config['robots']) != set(names):
            raise ValueError('Live configuration must map every tx/rx name to an AirSim robot')
        connection = ProjectAirSimClient(address=config['address'])
        connection.connect()
        world = World(connection, config['scene'], sim_config_path=config['sim_config'])
        world.pause()
        robots = {name: Drone(connection, world, robot) for name, robot in config['robots'].items()}
    origin_ns = int(world.get_sim_time())
    if origin_ns % 500:
        raise ValueError('Initial AirSim epoch must align to the 2 MS/s sample grid')
    sources = PrivateSources([f'tx{i}' for i in range(tx)])
    initial = sources.window(0, 1)
    emitters = {name: SDREmitter(wave, transmit_power_w=1e-4,
                    baseband_frequency_bounds_hz=(-999999., 999999.)) for name, wave in initial.items()}
    receiver = SDRNetworkReceiver(scene, emitters, PlutoSDRProfile(), renderer=renderer,
        continuous=True, samples_per_link=samples_per_link, link_diagnostics=False,
        profile_rendering=profile_rendering, reuse_render_buffers=optimizations,
        cache_scattering_samples=optimizations, fused_projection=fused_projection)
    bridge = AirSimSDRBridge(world, robots, receiver)
    consumer = Consumer(output/'captures')
    rows = []
    first = None
    try:
        sample_start = 0
        for index in range(1+warmup+iterations):
            # Integer sample accounting: 16667, 16666, 16667 ... at 120 Hz.
            sample_end = round((index+1)*FS/120)
            count = sample_end-sample_start
            started = perf_counter()
            world.continue_until_sim_time(origin_ns+sample_start*500, wait_until_complete=True)
            pose_ms = (perf_counter()-started)*1000
            if int(world.get_sim_time()) != origin_ns+sample_start*500:
                raise RuntimeError('Live physics did not pause at the requested contiguous RF epoch; no dropped samples allowed')
            tick = perf_counter()
            for name, wave in sources.window(sample_start, count).items():
                if origin_ns:
                    wave = replace(wave, reference_time_ns=wave.reference_time_ns+origin_ns)
                receiver.emitters[name] = replace(receiver.emitters[name], waveform=wave)
            source_ms = (perf_counter()-tick)*1000
            tick = perf_counter()
            captures = bridge.capture(num_samples=count)
            rf_ms = (perf_counter()-tick)*1000
            tick = perf_counter()
            for ri, (name, cap) in enumerate(captures.items()):
                if cap.adc_codes.shape != (count, 2) or cap.sim_time_ns != origin_ns+sample_start*500:
                    raise RuntimeError('Capture shape/epoch mismatch')
                if not np.isfinite(cap.input_iq_volts).all() or not np.isfinite(cap.adc_iq_volts).all():
                    raise RuntimeError('Nonfinite RF output')
                if not cap.retained_paths or min(cap.retained_paths.values()) < 1:
                    raise RuntimeError('A directed link lost all paths in this terrain scenario')
                consumer.deliver(index, ri, cap.adc_codes)
            delivery_ms = (perf_counter()-tick)*1000
            total_ms = (perf_counter()-started)*1000
            history = dr.kernel_history() if profile_rendering and propagation_backend == 'cuda' else []
            device_history = dict(events=len(history),
                optix_events=sum('optix' in str(v.get('type','')).lower() for v in history),
                execution_ms=sum(float(v.get('execution_time',0)) for v in history))
            row = dict(sequence=index, sim_time_ns=origin_ns+sample_start*500, samples=count,
                advance_ms=pose_ms, source_ms=source_ms, channel_ms=receiver.last_channel_ms,
                rendering_ms=receiver.last_render_ms, receiver_ms=receiver.last_receiver_ms,
                other_rf_ms=rf_ms-receiver.last_channel_ms-receiver.last_render_ms-receiver.last_receiver_ms,
                delivery_storage_ms=delivery_ms, total_ms=total_ms,
                retained_paths={name: cap.retained_paths for name, cap in captures.items()},
                clipped_fraction_max=max(cap.clipped_component_fraction for cap in captures.values()),
                receiver_render_metrics=receiver.last_render_metrics,
                channel_sampling_metrics=getattr(receiver.solver, 'stage_timings', {}),
                channel_sampling=getattr(receiver.solver, 'sampling', {}),
                propagation_device_history=device_history)
            if index == 0:
                first = row
            elif index > warmup:
                rows.append(row)
                print(f'{len(rows)}/{iterations}: {total_ms:.2f} ms, {count} samples/RX', flush=True)
            sample_start = sample_end
    finally:
        consumer.close()
        if connection:
            world.pause()
            connection.disconnect()
    keys = ['advance_ms','source_ms','channel_ms','rendering_ms','receiver_ms','other_rf_ms','delivery_storage_ms','total_ms']
    summary = {key: stats([row[key] for row in rows]) for key in keys}
    simulated_ms = sum(row['samples'] for row in rows)/FS*1000
    wall_ratio = sum(row['total_ms'] for row in rows)/simulated_ms
    # Docker overlays omit .git; use build provenance supplied by the wrapper.
    def git_metadata(*args):
        try:
            return subprocess.check_output(['git',*args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    revision = os.environ.get('RF_PROFILE_SOURCE_REV') or git_metadata('rev-parse','HEAD')
    dirty_env = os.environ.get('RF_PROFILE_SOURCE_DIRTY')
    dirty = (dirty_env.lower() == 'true' if dirty_env.lower() in ('true','false') else None) if dirty_env is not None else (bool(git_metadata('status','--porcelain','--untracked-files=no')) if revision else None)
    gpu = None
    if renderer == 'basis-cuda':
        import cupy as cp
        props = cp.cuda.runtime.getDeviceProperties(cp.cuda.Device().id)
        gpu = dict(name=props['name'].decode() if isinstance(props['name'], bytes) else props['name'],
                   compute_capability=f"{props['major']}.{props['minor']}", total_memory_bytes=props['totalGlobalMem'],
                   cupy_version=cp.__version__)
    result = dict(measurement_mode='instrumented_end_to_end_profile' if profile_rendering else 'unprofiled_end_to_end_benchmark',
        scope='rf_pipeline_end_to_end' if airsim_config is None else 'live_airsim_rf_end_to_end',
        hardware=dict(cpu=next(line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')), cpu_count=os.cpu_count(), cpu_quota=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
                      platform=platform.platform(), sionna_rt=rt.__version__, mitsuba=mi.__version__, drjit=dr.__version__, jit_variant=mi.variant(), gpu=gpu),
        source_revision=revision, source_dirty=dirty,
        pose_source='deterministic AirSim-contract trajectory; physics/RPC not exercised' if airsim_config is None else 'live ProjectAirSim physics/RPC',
        propagation_backend='Sionna RT CUDA/OptiX' if propagation_backend == 'cuda' else 'Sionna RT LLVM CPU', rendering_backend=renderer,
        arguments=dict(tx=tx,rx=rx,iterations=iterations,warmup=warmup,samples_per_link=samples_per_link,profile_rendering=profile_rendering, reuse_render_buffers=optimizations,
        cache_scattering_samples=optimizations, fused_projection=fused_projection, threads=threads, propagation_backend=propagation_backend, pascal_compat=pascal_compat),
        timing_includes=['physics advance (live only)', 'snapshot/mount mapping', 'private waveform generation/copies',
            'scene multipath tracing/export', 'all-path I/Q rendering', 'persistent receive filter/noise/ADC',
            'SC16 serialization', 'loopback HTTP delivery/acknowledgement', 'consumer file write/readback (no fsync)'],
        timing_excludes=['scene/import/receiver/server initialization', 'first-use JIT and warmup from steady-state summary',
            'WAN/distributed worker fleet', 'AMS-GRA skill processing'],
        path_budget_note='1028 attempted diffuse samples/link, not a guarantee of 1028 valid physical paths; no synthetic padding or path pruning',
        execution='all receivers sequentially on one host/device; no receiver-parallel speedup credited',
        sample_rate_hz=FS, update_hz=120, measured_simulated_duration_ms=simulated_ms, first_capture=first, summary=summary,
        wall_time_per_simulated_time=wall_ratio, deadline_misses=sum(row['total_ms'] > row['samples']/FS*1000 for row in rows),
        captured_files=len(consumer.paths), samples=rows)
    (output/'measurements.json').write_text(json.dumps(result, indent=2)+'\n')
    headings=['Configuration / stage (ms)', *keys]
    label=f'{tx} TX × {rx} RX, {renderer}; '+('live AirSim' if airsim_config else 'trajectory source')
    lines=['# End-to-end RF pipeline result', '', result['pose_source']+'.', '',
        '**All stages are in milliseconds per complete fleet update.**', '',
        f'Measurement mode: {result["measurement_mode"]}. Instrumented runs are separate from throughput results.', '',
        '| '+' | '.join(headings)+' |', '| '+' | '.join(['---']+['---:']*len(keys))+' |',
        '| '+label+' | '+' | '.join(f'{summary[k]["median_ms"]:.2f} ± {summary[k]["std_ms"]:.2f}' if summary[k]['std_ms'] is not None else f'{summary[k]["median_ms"]:.2f} (n=1)' for k in keys)+' |', '',
        '## p95', '', '| '+' | '.join(headings)+' |', '| '+' | '.join(['---']+['---:']*len(keys))+' |',
        '| '+label+' | '+' | '.join(f'{summary[k]["p95_ms"]:.2f}' for k in keys)+' |', '',
        f'Measured windows: {iterations}; simulated duration: {simulated_ms:.4f} ms.', '',
        f'Wall time / simulated time: **{wall_ratio:.2f}×**. Deadline misses: {result["deadline_misses"]}/{iterations}.', '',
        f'Propagation backend: {result["propagation_backend"]}. Paths are physical scene returns, not the synthetic 1028-valid-path stress workload.', '',
        'Initialization is excluded from steady-state tables; the first complete capture is recorded separately in JSON.', '',
        'Receivers execute serially; delivery uses loopback HTTP, not the AMS-GRA native worker protocol. Consumer writes are read back but not fsync-ed.', '',
        '[Raw captures and per-step measurements](measurements.json).']
    (output/'REPORT.md').write_text('\n'.join(lines)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tx', type=int, default=100)
    parser.add_argument('--rx', type=int, default=10)
    parser.add_argument('--iterations', type=int, default=30)
    parser.add_argument('--warmup', type=int, default=3)
    parser.add_argument('--renderer', choices=('basis-cpu','basis-cuda'), default='basis-cpu')
    parser.add_argument('--samples-per-link', type=int, default=1028)
    parser.add_argument('--airsim-config', type=Path)
    parser.add_argument('--pascal-compat', action='store_true')
    parser.add_argument('--propagation-backend', choices=('llvm','cuda'), default='llvm')
    parser.add_argument('--threads', type=int, default=2, help='LLVM propagation worker threads')
    parser.add_argument('--no-optimizations', dest='optimizations', action='store_false')
    parser.add_argument('--fused-projection', action='store_true')
    parser.add_argument('--profile-rendering', action='store_true', help='Separate instrumented GPU-event run; never enters unprofiled throughput')
    args = parser.parse_args()
    if min(args.tx,args.rx,args.iterations,args.samples_per_link,args.threads)<1 or args.warmup<0:
        parser.error('Positive counts and nonnegative warmup required')
    import drjit as dr
    import mitsuba as mi
    dr.set_thread_count(args.threads)
    mi.set_variant(args.propagation_backend+'_ad_mono_polarized')
    result = run(**vars(args))
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
