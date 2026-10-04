import argparse,json,hashlib,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('bundle',type=Path);args=p.parse_args();b=args.bundle
m=json.loads((b/'manifest.json').read_text());env=json.loads((b/'environment.json').read_text())
scope={'stack':{'sionna':'0.19.2','mitsuba':'3.5.2','drjit':'0.4.6','tensorflow':'2.15.1','python':'3.11'},'propagation':'Legacy native Sionna Fibonacci solver; max_depth=1, LoS/reflection/scattering, scat_keep_prob=1, scat_random_phases=False. 1028 launched rays per TX, shared across receivers. Synthetic single-element arrays. Original terrain mesh and dielectric parameters (epsilon_r=5, conductivity=.01, scattering=.3), converted to legacy scene format; the legacy material has no thickness equivalent.','receiver':'Original branch SDRNetworkReceiver, waveform synthesis, independent clocks, filtering, noise and ADC; external Paths adapter supplies compact legacy channels and platform Doppler.','comparison_limit':'Not the profiling/p100 custom first-order sampler or Sionna 2.2 implementation. No numerical equivalence validation. Legacy rays and retained-path counts differ. Published current-solver CPU results and its work-count model are not directly comparable.','profile_limit':'Dr.Jit histories record its CUDA/OptiX operations only, not TensorFlow CUDA kernels. Inclusive host ranges overlap. Device-event sums are not service critical-path latency.','sampling_timers':'Original host_numpy_sampling_ms and proposal_table_prepare_ms are adapter compatibility placeholders set to zero; they are not measured stage timings and are excluded from the report.','cpu_baseline':'CPU cases hide GPUs from TensorFlow and use Mitsuba llvm_ad_rgb. CUDA cases use cuda_ad_rgb and TensorFlow CUDA. Dr.Jit uses two threads; TensorFlow thread defaults are not constrained.','outputs':'4096 complex samples per capture at 2 MS/s, 915 MHz carrier, 1 MHz receive bandwidth, one receiver per benchmark; example uses two TX and two RX.'}
(b/'legacy_scope.json').write_text(json.dumps(scope,indent=2)+'\n')
rows={}
for directory in ('metrics','profiles'):
    for path in (b/directory).glob('*.json'):
        data=json.loads(path.read_text());data['legacy_scope']=scope
        if 'arguments' in data:
            for key in ('gpu_workload_per_receiver','conditional_gpu_ray_stage'):
                data.pop(key,None)
            data['gpu_note']='Measured legacy service/channel latency. Original custom-solver work-count estimates do not apply.'
            data.get('stage_timings',{}).pop('host_numpy_sampling_ms',None)
            data.get('stage_timings',{}).pop('proposal_table_prepare_ms',None)
        path.write_text(json.dumps(data,indent=2)+'\n')
        if directory=='metrics': rows[path.stem]=data
lines=['# P100 legacy Sionna profiling results','','Status: **'+('COMPLETE — required collection tasks passed' if m.get('required_tasks_passed') else 'FAILED / INCOMPLETE')+'**.','', '**These results measure Sionna 0.19.2 native propagation plus the branch’s original I/Q/receiver chain. They do not measure the unchanged `profiling/p100` propagation solver.**','', '## Stack and workload','']
lines+=[scope['propagation'],'',scope['receiver'],'',scope['outputs'],'',scope['comparison_limit'],'',scope['cpu_baseline'],'']
lines+=['Source branch commit: `'+env.get('source_revision','unknown')+'`. Repository code was not edited. The external harness is retained in `external_harness/`.','', 'GPU inventory:','```text',env.get('gpu',{}).get('stdout','unavailable').strip(),'```','', '## Unprofiled service and channel timings','','| Case | Epochs | Service median / p95 / max (ms) | Channel median (ms) | I/Q+receiver median (ms) | Updates/s | Misses 120 Hz / 200 Hz | Retained paths |','|---|---:|---:|---:|---:|---:|---:|---:|']
for name,r in sorted(rows.items()):
    s=r['service'];counts=r['retained_paths']
    lines.append(f"| {name} | {r['arguments']['iterations']} | {s['p50_ms']:.2f} / {s['p95_ms']:.2f} / {s['max_ms']:.2f} | {r['channel']['p50_ms']:.2f} | {r['cpu_iq_receiver']['p50_ms']:.2f} | {r['sustained_updates_hz']:.3f} | {r['deadline_misses']['120']} / {r['deadline_misses']['200']} | {counts['min']}–{counts['max']} |")
lines+=['','Service includes poses, channel solve and synchronization/NumPy export, per-path waveform summation, per-link diagnostics, filtering, noise and ADC. Imports, setup, AirSim, transport, queueing and storage/plotting are excluded.','', '## Paired CPU/CUDA comparison','','| TX | CPU/CUDA median service ratio | CPU/CUDA median channel ratio |','|---|---:|---:|']
for tx in (2,100):
    cpu=rows.get(f'cpu_{tx}tx_1rx');gpu=rows.get(f'cuda_{tx}tx_1rx')
    if cpu and gpu:
        lines.append(f"| {tx} | {cpu['service']['p50_ms']/gpu['service']['p50_ms']:.3f}× | {cpu['channel']['p50_ms']/gpu['channel']['p50_ms']:.3f}× |")
lines+=['','Ratios above 1 favor CUDA. Retained path counts and backend rounding may differ; these are paired workload timings, not a numerical equivalence claim.','', '## Startup and separate instrumented profiles','','| Case | Preparation (ms) | First capture (ms) |','|---|---:|---:|']
for name,r in sorted(rows.items()):lines.append(f"| {name} | {r['preparation_ms']:.2f} | {r['first_capture']['service_ms']:.2f} |")
lines+=['','First capture is a fresh process with existing disk caches; caches were not purged. Warmup counts are recorded; first-capture/timed-epoch data and available JIT cache/compilation metadata are retained.','',scope['profile_limit'],'', '| CUDA profile | Timed epochs | Median Dr.Jit device-event sum (ms) | Median CUDA operation count | Median OptiX operation count |','|---|---:|---:|---:|---:|']
import statistics
for path in sorted((b/'profiles').glob('*events.json')):
    r=json.loads(path.read_text());ps=[x['profile'] for x in r.get('samples',[])];
    if ps:lines.append(f"| {path.stem} | {len(ps)} | {statistics.median(x['cuda_event_time_sum_ms'] for x in ps):.3f} | {statistics.median(x['cuda_operation_count'] for x in ps)} | {statistics.median(x['optix_kernel_count'] for x in ps)} |")
pre=json.loads((b/'profiles/cuda_preflight.json').read_text())
lines+=['',f"Preflight: `{pre.get('status')}`; {pre.get('retained_paths')} retained paths; {pre.get('profile',{}).get('cuda_operation_count')} CUDA operations and {pre.get('profile',{}).get('optix_kernel_count')} OptiX operations recorded.",'',scope['sampling_timers'],'','## Telemetry and task outcomes','']
telemetry=json.loads((b/'telemetry_summary.json').read_text())
lines+=['```json',json.dumps(telemetry,indent=2),'```','', 'Telemetry is sampled at one-second intervals and includes other GPU processes; it is not exact per-process peak allocation. Detailed host, driver, quotas and package versions are in `environment.json` and `installed_packages.json`.','', '| Task | Status | Log |','|---|---|---|']
for t in m['tasks']:lines.append(f"| {t['name']} | {t['status']} | [{t.get('log','optional')}]({t.get('log','manifest.json')}) |")
lines+=['','Nsight is optional and was unavailable unless the task table shows a successful capture. NVTX and Dr.Jit event profiling are retained separately from unprofiled performance runs.','', 'The two-beacon/two-receiver example captures and plots are in `raw/example/`. No independent numerical or scientific correctness validation has been performed.','', '[Manifest](manifest.json) · [Scope](legacy_scope.json) · [Profile summary](profile_summary.json) · [Checksums](checksums.json)','']
(b/'REPORT.md').write_text('\n'.join(lines))
try:
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,4.8))
    for ax,tx in zip(axes,(2,100)):
        names=[n for n in (f'cpu_{tx}tx_1rx',f'cuda_{tx}tx_1rx') if n in rows]
        x=list(range(len(names)));channel=[rows[n]['channel']['p50_ms'] for n in names];host=[rows[n]['cpu_iq_receiver']['p50_ms'] for n in names]
        ax.bar(x,channel,label='Channel');ax.bar(x,host,bottom=channel,label='I/Q + receiver')
        ax.set_xticks(x,[n.split('_')[0].upper() for n in names]);ax.set_ylabel('Median time (ms)');ax.set_title(f'{tx} TX / 1 RX');ax.legend()
    fig.suptitle('P100 legacy Sionna: service stage medians');fig.tight_layout();fig.savefig(b/'service_timings.png',dpi=180);plt.close(fig)
except ImportError:pass
checksums={str(p.relative_to(b)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(b.rglob('*')) if p.is_file() and 'raw' not in p.relative_to(b).parts and p.name!='checksums.json'}
(b/'checksums.json').write_text(json.dumps(checksums,indent=2)+'\n')
print('Report:', b/'REPORT.md')
