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


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle',type=Path)
    args=p.parse_args();root=args.bundle.resolve()
    manifest=load(root/'manifest.json');env=load(root/'environment.json')
    metrics=[]
    summaries={}
    for path in sorted((root/'metrics').glob('*.json')):
        data=load(path)
        if data.get('measurement_mode')!='unprofiled_benchmark':
            raise ValueError(f'{path.name}: instrumented run cannot enter performance table')
        metrics.append((path,data))
    for path in sorted((root/'profiles').glob('*.json')):
        data=load(path)
        if data.get('measurement_mode')=='instrumented_profile': summaries[path.name]=event_summary(data)
    (root/'profile_summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    telemetry=telemetry_summary(root/'raw/gpu_telemetry.csv')
    (root/'telemetry_summary.json').write_text(json.dumps(telemetry,indent=2)+'\n')
    verdict='COMPLETE' if manifest.get('complete') and manifest.get('required_tasks_passed') else 'FAILED / INCOMPLETE'
    if manifest.get('gpu_status')=='not_requested': verdict+=' — CPU-only harness validation; no GPU result'
    lines=[f"# RF profiling results: {manifest['run_id']}",'',f"Status: **{verdict}**.",'',
        f"GPU status: `{manifest.get('gpu_status')}`. Source: `{env.get('source_revision') or 'unknown'}`; dirty: `{env.get('source_dirty')}`.",'',
        f"Started: {manifest['started_utc']}. Finished: {manifest.get('finished_utc','interrupted')}.",'',
        'This measures the existing hybrid implementation: propagation may use CUDA, but proposal draws and I/Q/receiver processing remain CPU work. GPU synthesis optimizations are not implemented by this branch.','',
        '## Environment','',f"Host: `{env['hostname']}`. Python: `{env['python'].splitlines()[0]}`.",
        f"CPU quota: `{env.get('cpu_quota')}`; memory limit: `{env.get('memory_limit')}`. Detailed hardware, versions and source-file hashes: [environment.json](environment.json).",'',
        'GPU inventory:','', '```text',env.get('gpu',{}).get('stdout','').strip() or env.get('gpu',{}).get('error','nvidia-smi unavailable'),'```','',
        '## Unprofiled latency and serial throughput','',
        '| Case | Epochs | Median service | p95 service | Max service | Updates/s | Median channel | Median CPU I/Q+receiver | Misses 120/200 Hz |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for path,data in metrics:
        s=data['service'];miss=data['deadline_misses'];count=len(data['samples'])
        lines.append(f"| [{path.stem}](metrics/{path.name}) | {count} | {s['p50_ms']:.2f} ms | {s['p95_ms']:.2f} ms | {s['max_ms']:.2f} ms | {data['sustained_updates_hz']:.3f} | {data['channel']['p50_ms']:.2f} ms | {data['cpu_iq_receiver']['p50_ms']:.2f} ms | {miss['120']}/{miss['200']} |")
    if not metrics: lines.append('| No successful unprofiled measurements | — | — | — | — | — | — | — | — |')
    lines+=['','Service includes local pose writes, synchronized propagation/export, waveform synthesis, diagnostic filters, noise, receiver filtering and ADC. It excludes AirSim RPC, network, queueing, storage and RF skill processing. First capture/setup are stored separately; disk JIT caches are not purged. Small sample counts do not establish latency tails.','',
        '## Paired CPU/CUDA comparison','']
    paired={}
    for path,data in metrics:
        a=data['arguments'];paired.setdefault((a['tx'],a['rx'],a['samples'],a['samples_per_link']),{})[a['backend']]=data
    for key,pair in paired.items():
        if {'cpu','cuda'}<=pair.keys():
            cpu,gpu=pair['cpu'],pair['cuda']
            cp=sum(s['retained_paths'] for s in cpu['samples'])/len(cpu['samples'])
            gp=sum(s['retained_paths'] for s in gpu['samples'])/len(gpu['samples'])
            lines.append(f"* {key[0]} TX / {key[1]} RX: observed median service ratio CPU/CUDA **{cpu['service']['p50_ms']/gpu['service']['p50_ms']:.2f}×**; channel ratio **{cpu['channel']['p50_ms']/gpu['channel']['p50_ms']:.2f}×**. Mean retained paths CPU/CUDA: {cp:.1f}/{gp:.1f}. This is hybrid performance, not a GPU-resident synthesis speedup.")
    if not any({'cpu','cuda'}<=v.keys() for v in paired.values()): lines.append('No complete CPU/CUDA pair is available.')
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
