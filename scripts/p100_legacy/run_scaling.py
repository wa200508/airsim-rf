"""Run independent bounded simultaneous-TX cases and retain failure checkpoints."""
import argparse,json,subprocess,time,statistics,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--image',default='airsim-rf:p100-legacy-metrics');args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
for d in ('metrics','logs','raw'):(out/d).mkdir()
harness=Path(__file__).resolve().parent
manifest={'run_id':out.name,'experiment':'legacy simultaneous propagation-only scaling','image':args.image,'rays_per_tx':1028,'cases':[],'scope':'No IQ/waveforms/receiver DSP; legacy native trace plus RF fields and synchronized scalar reductions; no transmitter batching. One RX over original terrain. Host memory cap 12 GiB; physical P100 VRAM 16 GiB.'}
def save():(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
def probe(cmd):
 r=subprocess.run(cmd,capture_output=True,text=True);return {'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
metadata={'gpu':probe(['nvidia-smi','--query-gpu=name,uuid,driver_version,memory.total,compute_cap','--format=csv']),'image':probe(['docker','image','inspect',args.image]),'source_revision':probe(['git','rev-parse','HEAD'])}
(out/'environment.json').write_text(json.dumps(metadata,indent=2)+'\n');save()
for tx,iterations,warmup,timeout in ((1000,10,3,240),(10000,3,1,240),(100000,3,1,360),(1000000,1,0,480)):
 name=out.name+'-'+str(tx);record={'tx':tx,'requested_rays':tx*1028,'timeout_s':timeout,'iterations':iterations,'warmup':warmup,'status':'running'};manifest['cases'].append(record);save();print(f'[{tx} TX] starting',flush=True)
 metric=out/'metrics'/f'{tx}tx.json';log=out/'logs'/f'{tx}tx.log';telemetry=out/'raw'/f'{tx}tx_telemetry.csv'
 command=['docker','run','--name',name,'--gpus','device=0','--memory','12g','--memory-swap','12g','-e','NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics','-v',f'{harness}:/work/harness:ro','-v',f'{out}:/work/results','--entrypoint','sh',args.image,'-c','umask 000; exec python /work/harness/launch.py /work/harness/benchmark_propagation.py "$@"','sh','--tx',str(tx),'--iterations',str(iterations),'--warmup',str(warmup),'--output',f'/work/results/metrics/{tx}tx.json']
 record['command']=command;save();begin=time.monotonic();timed_out=False
 with log.open('w') as stream,telemetry.open('w') as samples:
  monitor=subprocess.Popen(['nvidia-smi','--query-gpu=timestamp,uuid,memory.used,utilization.gpu,power.draw,temperature.gpu','--format=csv,noheader,nounits','-lms','100'],stdout=samples,stderr=subprocess.STDOUT)
  child=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT)
  try:
   while child.poll() is None:
    if time.monotonic()-begin>timeout:
     timed_out=True;subprocess.run(['docker','stop','--time','10',name],capture_output=True);child.wait(timeout=20);break
    time.sleep(1)
  finally:
   monitor.terminate();monitor.wait(timeout=10)
 record.update(returncode=child.returncode,wall_s=time.monotonic()-begin,timed_out=timed_out,container_state=probe(['docker','inspect','--format','{{json .State}}',name]))
 if metric.exists():data=json.loads(metric.read_text())
 else:data={'status':'no_checkpoint','arguments':{'tx':tx}}
 if data.get('status')!='ok':
  data['status']='timeout' if timed_out else 'failed';data['termination']={'returncode':child.returncode,'container_state':record['container_state']};metric.write_text(json.dumps(data,indent=2)+'\n')
 record['status']=data['status'];record['stage']=data.get('stage');
 import csv
 rows=[]
 for row in csv.reader(telemetry.read_text().splitlines()):
  try:rows.append({'memory_mib':float(row[2]),'gpu_percent':float(row[3]),'power_w':float(row[4]),'temperature_c':float(row[5])})
  except (ValueError,IndexError):pass
 record['telemetry']={'sampling_interval_ms':100,'samples':len(rows),'includes_other_processes':True,'max_sampled_memory_mib':max((r['memory_mib'] for r in rows),default=None),'max_sampled_utilization_percent':max((r['gpu_percent'] for r in rows),default=None),'max_sampled_power_w':max((r['power_w'] for r in rows),default=None)}
 save();subprocess.run(['docker','rm',name],capture_output=True);print(f'[{tx} TX] {record["status"]}, stage={record["stage"]}, {record["wall_s"]:.1f}s',flush=True)
manifest['complete']=True;save()
checks={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and 'raw' not in p.relative_to(out).parts};(out/'checksums.json').write_text(json.dumps(checks,indent=2)+'\n')
print('Bundle:',out,flush=True)
