"""Regenerate a Markdown report and small JSON summaries from a profiling bundle."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import statistics


def load(path): return json.loads(path.read_text())


def percentile(values, fraction):
    ordered=sorted(values)
    index=(len(ordered)-1)*fraction
    left=int(index);right=min(left+1,len(ordered)-1)
    return ordered[left]+(ordered[right]-ordered[left])*(index-left)


def stats(values):
    return dict(p50_ms=statistics.median(values),p95_ms=percentile(values,.95),
        mean_ms=statistics.mean(values),max_ms=max(values)) if values else None


def event_summary(result):
    profiles=[row['profile'] for row in result['samples'] if 'profile' in row]
    groups=defaultdict(lambda:dict(count=0,event_ms=0.,codegen_ms=0.,backend_compile_ms=0.,cache_hits=0,cache_misses=0))
    host=defaultdict(list)
    for profile in profiles:
        for event in profile['records']:
            key=f"{event.get('backend','unknown')} / {event.get('type','unknown')}"+(' / OptiX' if event.get('uses_optix') else '')
            row=groups[key];row['count']+=1
            for source,target in (('execution_time','event_ms'),('codegen_time','codegen_ms'),('backend_time','backend_compile_ms')):
                row[target]+=float(event.get(source) or 0)
            if 'cache_hit' in event: row['cache_hits' if event['cache_hit'] else 'cache_misses']+=1
        epoch=defaultdict(float)
        for item in profile.get('host_ranges',[]):
            name=item['name']
            if name.startswith('capture.'): name='capture.timed'
            epoch[name]+=item['inclusive_host_ms']
        for name,value in epoch.items(): host[name].append(value)
    return dict(timed_capture_count=len(profiles),
        cuda_event_time_sum=stats([p['cuda_event_time_sum_ms'] for p in profiles]),
        cuda_operations=sum(p['cuda_operation_count'] for p in profiles),
        optix_kernels=sum(p['optix_kernel_count'] for p in profiles),
        nvtx_available=all(p.get('nvtx_available',False) for p in profiles) if profiles else False,
        operations=dict(groups),inclusive_host_ranges={k:stats(v) for k,v in host.items()},
        note='Timed captures only. Device operation sums and nested inclusive host ranges are not additive service latency.')


def telemetry_summary(path):
    devices={}
    if path.exists():
        with path.open() as stream:
            for row in csv.DictReader(stream,skipinitialspace=True):
                uuid=row.get('uuid','unknown')
                device=devices.setdefault(uuid,dict(samples=0,index=row.get('index'),max_sampled_memory_mib=None,
                    max_sampled_utilization_percent=None,max_sampled_power_w=None,max_sampled_temperature_c=None))
                device['samples']+=1
                for field,key in (('memory.used','max_sampled_memory_mib'),('utilization.gpu','max_sampled_utilization_percent'),
                                  ('power.draw','max_sampled_power_w'),('temperature.gpu','max_sampled_temperature_c')):
                    try: value=float(row[field])
                    except (KeyError,ValueError,TypeError): continue
                    device[key]=value if device[key] is None else max(device[key],value)
    return {'devices':devices,'note':'One-second nvidia-smi samples; includes other processes and may miss peaks. Not allocated-byte or guaranteed peak VRAM measurement.'}


def finish_report(root, lines):
    report=root/'REPORT.md';report.write_text('\n'.join(lines)+'\n')
    checksums={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*'))
        if p.is_file() and 'raw' not in p.relative_to(root).parts and p.name!='checksums.json'}
    (root/'checksums.json').write_text(json.dumps(checksums,indent=2)+'\n')
    print(f'Report: {report}')


def basis_report(root, manifest, env):
    measurements=[]
    profiles={}
    for path in sorted((root/'profiles').glob('*.json')):
        data=load(path)
        if data.get('scope')!='doppler_basis_receiver_rendering':continue
        mode=data.get('measurement_mode')
        if mode=='unprofiled_basis_benchmark':measurements.append((path,data))
        elif mode!='instrumented_basis_profile':raise ValueError('Unknown basis measurement mode')
        profiles[path.name]=data.get('profile_receivers',[])
    valid=all(data.get('accuracy',{}).get('passed',False) for _,data in measurements)
    gpu_valid=all(data['backend']!='cuda' or manifest.get('gpu_status')=='verified_cuda_cupy' for _,data in measurements)
    verdict='COMPLETE' if manifest.get('complete') and manifest.get('required_tasks_passed') and valid and gpu_valid else 'FAILED / INCOMPLETE'
    if manifest.get('gpu_status')=='not_requested':verdict+=' — CPU-only harness validation'
    telemetry=telemetry_summary(root/'raw/gpu_telemetry.csv')
    (root/'profile_summary.json').write_text(json.dumps(profiles,indent=2)+'\n')
    (root/'telemetry_summary.json').write_text(json.dumps(telemetry,indent=2)+'\n')
    lines=[f"# Doppler-basis renderer profiling: {manifest['run_id']}",'',f'Status: **{verdict}**.','',
        f"Renderer GPU status: `{manifest.get('gpu_status')}`. Source: `{env.get('source_revision')}`; dirty: `{env.get('source_dirty')}`.",'',
        '**Renderer-only:** synthetic changing channels, equal sample clocks, FP64/complex128, private source data and FFTs. All configured paths are valid. No ray tracing, source generation, clock resampling, noise/filter/ADC, AirSim or network/queueing is included.','',
        f"Propagation: {manifest.get('propagation_status')}. A successful renderer run does not establish current Sionna compatibility or complete RF service at 120 Hz.",'',
        '## Unprofiled renderer-call wall service and serial throughput','',
        '| Backend | TX × RX | Valid paths/link | Samples | Median | p95 | p99 | Max | Windows/s | Wall s / signal s | Signal ms/call | Measured signal s | Measured wall s | Misses 120 Hz | Accuracy |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    pairs={}
    for path,data in measurements:
        a=data['arguments'];s=data['summary'];qualified=data['accuracy']['passed']
        if data['backend']=='cuda' and not gpu_valid:qualified=False
        lines.append(f"| [{data['backend']}](profiles/{path.name}) | {a['tx']} × {a['rx']} | {a['paths']} | {a['samples']} | {s['p50_ms']:.3f} ms | {s['p95_ms']:.3f} ms | {s['p99_ms']:.3f} ms | {s['max_ms']:.3f} ms | {data['captures_per_second']:.3f} | {s['mean_ms']/(a['samples']/a['sample_rate']*1000):.3f} | {a['samples']/a['sample_rate']*1000:.6f} | {len(data['rows'])*a['samples']/a['sample_rate']:.6f} | {sum(r['total_ms'] for r in data['rows'])/1000:.6f} | {data['misses_120hz']}/{len(data['rows'])} | {'PASS' if qualified else 'INVALID'} |")
        key=tuple(a.get(k) for k in ('tx','rx','paths','samples','sample_rate','max_delay_us','max_doppler_hz','taps','block_samples','tolerance'))
        if qualified:pairs.setdefault(key,{})[data['backend']]=data
    if not measurements:lines.append('| No successful measurements | — | — | — | — | — | — | — | — | — | — |')
    lines+=['','Timing includes fresh path-dependent setup, host validation/packing, private input uploads, GPU coefficient construction/projection, private FFTs, receiver summation and synchronized final output export. First-use/JIT time is recorded separately. Instrumented Nsight runs are excluded from this table.','',
        'The scene deadline is 8.333 ms. Default windows contain 16,667 samples at 2 MS/s (8.3335 ms of signal). Live input accumulation, interpolation lookahead and transport add delivery latency. This API exports a complete window; it is not yet a persistent continuous streaming receiver.','',
        '## Paired CPU/GPU renderer measurements','']
    for key,pair in pairs.items():
        if {'cpu','cuda'}<=pair.keys():
            cpu,gpu=pair['cpu'],pair['cuda']
            lines.append(f"* {key[0]} TX × {key[1]} RX: observed CPU/CUDA median ratio **{cpu['summary']['p50_ms']/gpu['summary']['p50_ms']:.2f}×**; CUDA output rate **{gpu['output_samples_per_second_per_receiver']:.0f} samples/s per receiver**; remaining mean-latency factor to 120 Hz **{gpu['required_speedup_to_120hz']:.2f}×**.")
    if not any({'cpu','cuda'}<=p.keys() for p in pairs.values()):lines.append('No qualified CPU/CUDA pair.')
    lines+=['','## Separate GPU stage spans and memory','',
        'One extra instrumented capture supplies CUDA-event spans and NVTX ranges. Event spans can include host submission/idle gaps, especially packing; they are not pure kernel execution times. Do not add these spans to wall latency. Use Nsight kernel/API statistics for execution-level attribution.','']
    for name,receivers in profiles.items():
        for ri,metric in enumerate(receivers):
            groups=defaultdict(float)
            for event in metric.get('events',[]):groups[event['name']]+=event['cuda_ms']
            lines.append(f"* [{name}](profiles/{name}), receiver {ri}: stage spans {dict(groups)}. Pool used/reserved {metric.get('pool_used_bytes')}/{metric.get('pool_reserved_bytes')} bytes; largest sampled pool-use checkpoint {metric.get('max_checkpoint_pool_used_bytes')} bytes. Allocator snapshots include plans/cache and are not exact process peak VRAM.")
    lines+=['','## Accuracy and hardware','',
        'Each case compares its final timed window’s receiver output samples against CPU basis reconstruction, checks all paths of all links in initial/final sample prefixes against direct rendering, and checks complete direct output for the first/last transmitter of each receiver. Tests cover cancellation, changed channels, split captures, finite boundaries and Unix timestamps. Error is relative to the finite interpolation operator; ideal-sinc/noise-floor qualification remains separate.','',
        f"CPU quota: `{env.get('cpu_quota')}`. Hardware, pinned packages and source hashes: [environment.json](environment.json) and [installed_packages.json](installed_packages.json).",'',
        '```text',env.get('gpu',{}).get('stdout','').strip() or 'GPU inventory unavailable','```','',
        telemetry['note'],'',json.dumps(telemetry['devices'],indent=2),'',
        '## Task outcomes','', '| Task | Status | Required | Log |','|---|---|---|---|']
    for task in manifest['tasks']:
        lines.append(f"| {task['name']} | {task['status']} | {task.get('required',False)} | "+(f"[log]({task['log']})" if task.get('log') else task.get('reason','—'))+' |')
    if manifest.get('error'):lines+=['',f"Run error: {manifest['error']}"]
    preflight=root/'profiles/basis_cuda_preflight.json'
    if preflight.is_file() and load(preflight).get('error'):lines+=['','CUDA blocker:','', '```text',load(preflight)['error'],'```']
    lines+=['','One P100 normally tests one receiver with 100 private TX inputs. `--rx 10` measures ten receivers sequentially on this GPU; it is not a ten-GPU fleet measurement. A renderer meeting the deadline still leaves propagation and mandatory receiver processing to qualify.','',
            'Large Nsight traces remain in ignored raw/. Small reports/JSON/logs can be published with scripts/publish_gpu_results.py.','']
    finish_report(root,lines)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle',type=Path)
    args=p.parse_args();root=args.bundle.resolve()
    manifest=load(root/'manifest.json');env=load(root/'environment.json')
    if manifest.get('scope')=='rf_pipeline_end_to_end_collection':
        from aggregate_end_to_end_profile import aggregate
        aggregate(root)
        return
    if manifest.get('scope')=='doppler_basis_renderer':
        basis_report(root,manifest,env)
        return
    metrics=[]
    summaries={}
    sampled=[]
    for path in sorted((root/'metrics').glob('*.json')):
        data=load(path)
        if data.get('measurement_mode')!='unprofiled_benchmark':
            raise ValueError(f'{path.name}: instrumented run cannot enter performance table')
        metrics.append((path,data))
    for path in sorted((root/'profiles').glob('*.json')):
        data=load(path)
        if data.get('measurement_mode')=='instrumented_profile': summaries[path.name]=event_summary(data)
        if data.get('scope')=='standalone_sampled_renderer': sampled.append((path,data))
    (root/'profile_summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    telemetry=telemetry_summary(root/'raw/gpu_telemetry.csv')
    (root/'telemetry_summary.json').write_text(json.dumps(telemetry,indent=2)+'\n')
    verdict='COMPLETE' if manifest.get('complete') and manifest.get('required_tasks_passed') else 'FAILED / INCOMPLETE'
    if manifest.get('gpu_status')=='not_requested': verdict+=' — CPU-only harness validation; no GPU result'
    lines=[f"# RF profiling results: {manifest['run_id']}",'',f"Status: **{verdict}**.",'',
        f"GPU status: `{manifest.get('gpu_status')}`. Source: `{env.get('source_revision') or 'unknown'}`; dirty: `{env.get('source_dirty')}`.",'',
        f"Started: {manifest['started_utc']}. Finished: {manifest.get('finished_utc','interrupted')}.",'',
        'Renderer and propagation backend are selected independently. Direct and batched recurrence use LLVM or CUDA; NumPy is the original renderer. Proposal draws, channel export and receiver filters/ADC remain CPU work. Direct CUDA timing includes per-link transfers and reduction; batched CUDA groups transfers across private jobs.','',
        '## Environment','',f"Host: `{env['hostname']}`. Python: `{env['python'].splitlines()[0]}`.",
        f"CPU quota: `{env.get('cpu_quota')}`; memory limit: `{env.get('memory_limit')}`. Detailed hardware, versions and source-file hashes: [environment.json](environment.json).",'',
        'GPU inventory:','', '```text',env.get('gpu',{}).get('stdout','').strip() or env.get('gpu',{}).get('error','nvidia-smi unavailable'),'```','',
        '## Unprofiled latency and serial throughput','',
        '| Case | Epochs | Median service | p95 service | Max service | Updates/s | Median channel | Median I/Q+receiver | Misses 120/200 Hz |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for path,data in metrics:
        s=data['service'];miss=data['deadline_misses'];count=len(data['samples'])
        lines.append(f"| [{path.stem}](metrics/{path.name}) | {count} | {s['p50_ms']:.2f} ms | {s['p95_ms']:.2f} ms | {s['max_ms']:.2f} ms | {data['sustained_updates_hz']:.3f} | {data['channel']['p50_ms']:.2f} ms | {data['cpu_iq_receiver']['p50_ms']:.2f} ms | {miss['120']}/{miss['200']} |")
    if not metrics: lines.append('| No successful unprofiled measurements | — | — | — | — | — | — | — | — |')
    lines+=['','Service includes local pose writes, synchronized propagation/export, waveform synthesis, diagnostic filters, noise, receiver filtering and ADC. It excludes AirSim RPC, network, queueing, storage and RF skill processing. First capture/setup are stored separately; disk JIT caches are not purged. Small sample counts do not establish latency tails.','',
        '## Paired CPU/CUDA comparison','']
    paired={}
    for path,data in metrics:
        a=data['arguments'];kind=a.get('renderer','numpy').split('-')[0]
        # Configuration belongs in pairing: do not compare differing diagnostics,
        # recurrence lengths, replay modes or reduction strategies as GPU speedup.
        paired.setdefault((a['tx'],a['rx'],a['samples'],a['samples_per_link'],kind,
                           a.get('sample_tile',32),a.get('accumulation','partial'),
                           a.get('no_link_diagnostics',False),a.get('no_replay',False),
                           a.get('max_render_lanes',1_000_000),a.get('batch_reduction','auto')),{})[a['backend']]=data
    for key,pair in paired.items():
        if {'cpu','cuda'}<=pair.keys():
            cpu,gpu=pair['cpu'],pair['cuda']
            cp=sum(s['retained_paths'] for s in cpu['samples'])/len(cpu['samples'])
            gp=sum(s['retained_paths'] for s in gpu['samples'])/len(gpu['samples'])
            lines.append(f"* {key[0]} TX / {key[1]} RX / {key[4]} renderer: observed median service ratio CPU/CUDA **{cpu['service']['p50_ms']/gpu['service']['p50_ms']:.2f}×**; channel ratio **{cpu['channel']['p50_ms']/gpu['channel']['p50_ms']:.2f}×**. Mean retained paths CPU/CUDA: {cp:.1f}/{gp:.1f}. This is end-to-end hybrid performance; filters/ADC and host/device transfers remain included.")
    if not any({'cpu','cuda'}<=v.keys() for v in paired.values()): lines.append('No complete CPU/CUDA pair is available.')
    lines+=['','## Renderer comparison','',
        '| Case | Renderer | Median rendering including transfers | Median service |',
        '|---|---|---:|---:|']
    for path,data in metrics:
        renderer=data['arguments'].get('renderer','numpy')
        duration=data.get('rendering',{}).get('p50_ms')
        label=f'{duration:.3f} ms' if duration is not None else 'not recorded'
        lines.append(f"| {path.stem} | {renderer} | {label} | {data['service']['p50_ms']:.3f} ms |")
    lines+=['','All direct/batched modes retain valid paths and independent Dopplers in FP64. Per-link direct rendering selects contribution buffers or local reduction. Batched rendering uses bounded independent jobs and replay, with local CUDA reduction and threshold-dependent thread-private CPU reduction; it has no path-by-sample contribution buffers. Configuration and replay/batch metrics are recorded in each JSON. See direct_renderer_correctness for GPU numerical checks.','']
    if sampled:
        lines+=['## Separate arbitrary sampled-input renderer stress','',
                'Renderer-only timings, excluding propagation and receiver DSP. Every job owns private input data; all configured paths are valid. Finite interpolation error relative to ideal sinc is not qualified by equality to the reference operator.','',
                '| Backend | Private links | Valid paths/link | Output samples | Interpolation taps | Median renderer | p95 |',
                '|---|---:|---:|---:|---:|---:|---:|']
        for path,data in sampled:
            a=data['arguments']
            lines.append(f"| [{a['backend']}](profiles/{path.name}) | {a['links']} | {a['paths']} | {a['samples']} | {a['taps']} | {data['p50_ms']:.3f} ms | {data['p95_ms']:.3f} ms |")
    lines+=['','## Separate instrumented profiles','',
        'These instrumented runs are excluded from the performance table. CUDA-event sums are recorded device operation time, not critical-path latency. Host ranges are inclusive and nested; do not add them together.','']
    if not summaries: lines.append('No completed instrumented profiles.')
    for name,summary in summaries.items():
        device=summary['cuda_event_time_sum'];label=f"{device['p50_ms']:.3f} ms" if device else 'unavailable'
        lines+=[f"### {name}",'',f"Timed captures: {summary['timed_capture_count']}; CUDA operations: {summary['cuda_operations']}; OptiX kernels: {summary['optix_kernels']}; NVTX available: {summary['nvtx_available']}. Median CUDA event-time sum/capture: **{label}**.",'',
            '| Host range | Median inclusive time/capture | p95 |','|---|---:|---:|']
        for key,value in summary['inclusive_host_ranges'].items():
            lines.append(f"| {key} | {value['p50_ms']:.3f} ms | {value['p95_ms']:.3f} ms |")
        lines+=['','Operation groups, compilation/cache metadata and original events: [profile_summary.json](profile_summary.json) and '+f'[raw event JSON](profiles/{name}).','']
    lines+=['## GPU telemetry','',telemetry['note'],'']
    for uuid,device in telemetry['devices'].items():
        lines.append(f"* `{uuid}`: {device['samples']} samples; maximum sampled memory {device['max_sampled_memory_mib']} MiB; utilization {device['max_sampled_utilization_percent']}%; temperature {device['max_sampled_temperature_c']} °C.")
    if not telemetry['devices']: lines.append('GPU telemetry unavailable or disabled.')
    lines+=['','## Task outcomes and compatibility','', '| Task | Status | Required | Log |','|---|---|---|---|']
    for task in manifest['tasks']:
        log=f"[log]({task['log']})" if task.get('log') else task.get('reason','—')
        lines.append(f"| {task['name']} | {task['status']} | {task.get('required',False)} | {log} |")
    if manifest.get('error'): lines+=['',f"Run error: `{manifest['error']}`."]
    preflight=root/'profiles/cuda_preflight.json'
    if preflight.exists() and load(preflight).get('error'):
        lines+=['','CUDA/OptiX blocker:','', '```text',load(preflight)['error'],'```']
    lines+=['','## Artifacts and interpretation','',
        '* Benchmark JSON, profile summaries, environment, logs and checksums are intended for git publication.',
        '* Large Nsight `.nsys-rep`/SQLite files, telemetry CSV and example I/Q/plots live in ignored `raw/`. Keep them locally or attach them to a release separately.',
        '* Nsight timeline/statistics are optional. Missing tooling or profiler permissions are recorded; CUDA-event profiles remain useful.',
        '* P100 lacks RT cores. RTX 4090 estimates in the architecture report are not predictions for this GPU.',
        '* This is one receiver worker. Ten GPUs increase fleet parallelism, not one receiver’s speed.',
        '* For a serial worker, a requested rate f needs f × mean service seconds < 1 for queue stability. Actual delivery latency also includes dispatch, transport and queueing.',
        '* No numerical CPU/GPU equivalence claim follows from matching path counts; this bundle measures performance and basic smoke validity.',
        '', '[Manifest](manifest.json) · [Device profile summaries](profile_summary.json) · [Telemetry summary](telemetry_summary.json) · [Checksums](checksums.json)','']
    report=root/'REPORT.md';report.write_text('\n'.join(lines))
    checksums={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*'))
        if p.is_file() and 'raw' not in p.relative_to(root).parts and p.name!='checksums.json'}
    (root/'checksums.json').write_text(json.dumps(checksums,indent=2)+'\n')
    print(f'Report: {report}')


if __name__=='__main__': main()
