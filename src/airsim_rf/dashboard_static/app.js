'use strict';
let token='',lastFrame=-1,lastWindow=-1,lastStatus=null,lastControlStatus=null,presentationGeneration=0;
const $=id=>document.getElementById(id);
const player={id:null,autoSelect:true,playing:true,following:false,time:0,end:0,start:0,rate:1,lastTick:performance.now()};
let recordingOptions='',scenarioOptions='';
$('scenario-select').onchange=async()=>{
 chooseRecording(null,true);
 const response=await fetch('/api/scenario',{method:'POST',headers:{'X-Dashboard-Token':token,'Content-Type':'application/json'},body:JSON.stringify({id:$('scenario-select').value})});
 if(!response.ok){$('error').hidden=false;$('error').textContent=await response.text();}
};
function chooseRecording(id,autoSelect=false){
 player.id=id;player.autoSelect=autoSelect;player.time=0;player.end=0;player.start=0;player.playing=true;player.following=false;player.lastTick=performance.now();presentationGeneration++;
}
$('recording-select').onchange=()=>chooseRecording($('recording-select').value);
$('playback-seek').oninput=()=>{player.time=Number($('playback-seek').value);player.playing=false;player.following=false;player.lastTick=performance.now();presentationGeneration++;};
$('playback-play').onclick=()=>{if(!player.playing&&player.time>=player.end)player.time=player.start;player.playing=!player.playing;player.following=false;player.lastTick=performance.now();presentationGeneration++;};
$('playback-rate').onchange=()=>{player.rate=Number($('playback-rate').value);player.lastTick=performance.now();};
$('playback-latest').onclick=()=>{player.time=player.end;player.following=true;player.playing=true;player.lastTick=performance.now();presentationGeneration++;};
function recordingControls(state){
 const recordings=state.recordings||[],signature=recordings.map(r=>r.id).join(',');
 if(signature!==recordingOptions){
  $('recording-select').replaceChildren(...recordings.map(r=>{const option=document.createElement('option');option.value=r.id;option.textContent=r.created_utc.slice(0,19).replace('T',' ')+' UTC · '+r.id;return option;}));recordingOptions=signature;
 }
 if(recordings.length&&player.autoSelect&&player.id!==recordings[0].id)chooseRecording(recordings[0].id,true);
 $('recording-select').value=player.id||'';
 const timeline=state.playback,available=timeline&&timeline.id===player.id&&timeline.playable_frames>0;
 $('playback-play').disabled=!available;$('playback-seek').disabled=!available;$('playback-latest').disabled=!available;
 if(!timeline||timeline.id!==player.id)return;
 player.start=timeline.start_s;player.end=timeline.end_s;
 if(player.playing&&timeline.status==='complete'&&player.time>=player.end)player.playing=false;
 $('playback-play').textContent=player.playing?'Pause playback':'Play';
 $('playback-state').textContent=!available?'WAITING FOR MATCHED DATA':player.time>=player.end?(timeline.status==='complete'?'END OF RECORDING':player.playing?'BUFFERING / END OF SAVED PORTION':'PAUSED'):player.playing?(player.following?'FOLLOWING LATEST':'PLAYING'):'PAUSED';
 $('playback-seek').min=timeline.start_s;$('playback-seek').max=timeline.end_s;
 $('record-progress').max=timeline.duration_s;$('record-progress').value=timeline.computed_s;
 const active=state.active_recording_id===timeline.id&&!state.replay_only;
 const label=timeline.status==='complete'?'Complete':active?(timeline.status==='paused'?'Computation paused':'Computing'):timeline.status==='failed'?'Failed · saved portion':'Saved portion';
 $('record-progress-label').textContent=`${label} · ${timeline.computed_s.toFixed(2)} / ${timeline.duration_s.toFixed(2)} s computed · ${timeline.playable_frames} synchronized frames`;
}

function surface(id){const canvas=$(id),ratio=devicePixelRatio||1,rect=canvas.getBoundingClientRect();canvas.width=Math.round(rect.width*ratio);canvas.height=Math.round(rect.height*ratio);const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);return [ctx,rect.width,rect.height];}
function gauge(rate,fullScale=128){const [ctx,w,h]=surface('gauge'),cx=w/2,cy=h-16,r=Math.min(w/2-24,h-30);ctx.lineWidth=10;ctx.lineCap='round';ctx.strokeStyle='#22333e';ctx.beginPath();ctx.arc(cx,cy,r,Math.PI,2*Math.PI);ctx.stroke();const fraction=Math.min(rate/fullScale,1);ctx.strokeStyle='#55d7d0';ctx.beginPath();ctx.arc(cx,cy,r,Math.PI,Math.PI+fraction*Math.PI);ctx.stroke();ctx.font='9px monospace';ctx.fillStyle='#607c8e';ctx.fillText('0',cx-r-5,cy+13);ctx.fillText(fullScale.toFixed(0),cx+r-15,cy+13);const angle=Math.PI+fraction*Math.PI;ctx.lineWidth=2;ctx.strokeStyle='#e6b96c';ctx.beginPath();ctx.moveTo(cx+Math.cos(angle)*(r-21),cy+Math.sin(angle)*(r-21));ctx.lineTo(cx+Math.cos(angle)*(r+6),cy+Math.sin(angle)*(r+6));ctx.stroke();}
function groundtrack(p,scenario){const [ctx,w,h]=surface('groundtrack'),cx=w/2,cy=h/2,scale=Math.min(w-36,h-36)/(scenario.terrain_width_m||800);
 const point=v=>[cx-v[1]*scale,cy-v[0]*scale];const grid=scenario.terrain_grid;
 if(grid){const heights=grid.heights_m.flat(),lo=Math.min(...heights),hi=Math.max(...heights);
  for(let y=0;y<grid.y_m.length-1;y++)for(let x=0;x<grid.x_m.length-1;x++){
   const cells=[[y,x],[y,x+1],[y+1,x+1],[y+1,x]];
   for(const triangle of [[0,1,2],[0,2,3]]){const vertices=triangle.map(k=>cells[k]),elevation=vertices.reduce((s,[j,i])=>s+grid.heights_m[j][i],0)/3,f=(elevation-lo)/Math.max(hi-lo,1);
    ctx.fillStyle=`rgb(${Math.round(30+105*f)},${Math.round(64+75*f)},${Math.round(47+42*f)})`;ctx.beginPath();vertices.forEach(([j,i],k)=>{const [px,py]=point([grid.x_m[i],grid.y_m[j]]);if(k)ctx.lineTo(px,py);else ctx.moveTo(px,py);});ctx.closePath();ctx.fill();}}
  ctx.font='9px monospace';ctx.fillStyle='#c3d5de';ctx.textAlign='left';ctx.fillText(`N ↑ · elevation ${lo.toFixed(0)}–${hi.toFixed(0)} m`,9,14);}
 ctx.strokeStyle='#6e8a96';ctx.setLineDash([3,3]);
 if(scenario.routes_rf_m){for(const route of scenario.routes_rf_m){ctx.beginPath();route.forEach((v,i)=>{const [x,y]=point(v);if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);});ctx.stroke();}}
 else if(scenario.radius_m){ctx.beginPath();ctx.arc(cx,cy,scenario.radius_m*scale,0,2*Math.PI);ctx.stroke();}ctx.setLineDash([]);
 ctx.strokeStyle='#55d7d0';ctx.lineWidth=1.6;ctx.beginPath();(p.history||[]).forEach((row,i)=>{const [x,y]=point(row.position_rf_m);if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);});ctx.stroke();
 if(p.position_rf_m){const [x,y]=point(p.position_rf_m);ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(x,y,3,0,Math.PI*2);ctx.fill();}
 (p.site_paths||scenario.sites||[]).forEach((site,i)=>{const [x,y]=point(site.center_rf_m);ctx.fillStyle=i?'#e6b96c':'#55d7d0';ctx.fillRect(x-3,y-3,6,6);
  if(p.position_rf_m){const [tx,ty]=point(p.line_target_position_rf_m||p.primary_tx_position_rf_m||p.position_rf_m);ctx.strokeStyle=site.direct_elements?'#55d7d0':'#e6b96c';ctx.setLineDash(site.direct_elements?[]:[4,4]);ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(tx,ty);ctx.stroke();ctx.setLineDash([]);}
  if(site.blocker_rf_m){const [bx,by]=point(site.blocker_rf_m);ctx.strokeStyle='#ffae65';ctx.beginPath();ctx.moveTo(bx-4,by-4);ctx.lineTo(bx+4,by+4);ctx.moveTo(bx-4,by+4);ctx.lineTo(bx+4,by-4);ctx.stroke();}});
}
async function action(name){if(name==='prepare'){chooseRecording(null,true);}try{const response=await fetch('/api/'+name,{method:'POST',headers:{'X-Dashboard-Token':token}});if(!response.ok)throw Error(await response.text());}catch(error){$('error').textContent=error.message;$('error').hidden=false;}}
$('prepare').onclick=()=>action('prepare');$('start').onclick=()=>action('start');$('stop').onclick=()=>action('stop');$('pause').onclick=()=>action((lastControlStatus?.control_producer||lastControlStatus?.producer)?.status==='paused'?'resume':'pause');
function renderControls(state){
 const choices=state.scenario_catalog||[],signature=JSON.stringify(choices);
 if(signature!==scenarioOptions){$('scenario-select').replaceChildren(...choices.map(row=>{const option=document.createElement('option');option.value=row.id;option.textContent=row.title;return option;}));scenarioOptions=signature;}
 $('scenario-select').value=state.selected_scenario||'';
 $('scenario-select').disabled=Boolean(state.busy||state.mission_started||state.replay_only);
lastControlStatus=state;token=state.token;const p=state.control_producer||state.producer,health=state.service_health||{},running=Object.values(state.processes).some(v=>v.state==='running');
 $('start').disabled=state.busy||!state.ready||state.mission_started;$('prepare').disabled=state.busy||state.ready;$('connection').textContent=state.replay_only?'REPLAY ONLY':state.ready?'SERVICES READY':state.busy?'PREPARING':'NOT READY';$('stop').disabled=state.busy||!running;$('pause').disabled=state.busy||p.status!=='running'&&p.status!=='paused';$('pause').textContent=p.status==='paused'?'Resume computation':'Pause computation';
 if(state.replay_only){for(const id of ['prepare','start','pause','stop'])$(id).disabled=true;}
 recordingControls(state);
 $('error').hidden=!state.error&&!p.error&&!health.skill_error;$('error').textContent=state.error||p.error||health.skill_error||'';
 for(const part of ['sim','rf','skill']){const element=document.querySelector(`[data-process="${part}"]`),process=state.processes[part],badge=element.querySelector('.status');badge.textContent=process?process.state.toUpperCase():state.replay_only?'NOT NEEDED':'OFFLINE';badge.classList.toggle('on',process?.state==='running');element.querySelector('.identity').textContent=state.replay_only?'Playing saved mission output':process?`${process.container||part} · PID ${process.pid}`:['Ready for launch','CUDA deployment','Coherent TCP metadata extension'][['sim','rf','skill'].indexOf(part)];}
}
function render(state){lastStatus=state;renderControls(state);const s=state.skill,p=state.producer,transport=s,sync=state.synchronization||{};
 const scenario=state.scenario,carrier=s.carrier_hz||scenario.carrier_hz,fs=s.sample_rate_hz||scenario.sample_rate_hz;
 $('geometry-note').textContent='North up · shared terrain elevation · cyan: direct sight line · amber dashed: terrain-blocked sight line. Reflected RF can remain when the direct path is blocked.';
 $('scenario-title').textContent=scenario.title||'Recorded scenario / tracking camera';
 $('mission-label').textContent=scenario.id||'RECORDED SCENARIO';
 $('signal-label').textContent=`${carrier?(carrier/1e6).toFixed(3)+' MHz':'Carrier pending'} · ${fs?(fs/1e6).toFixed(3)+' MS/s':'Rate pending'}`;
 $('flight-summary').textContent=scenario.flight_type==='racetrack'?`${scenario.straight_length_m} m straights / ${scenario.turn_radius_m} m turns / ${scenario.speed_m_s} m/s`:scenario.radius_m?`${scenario.radius_m} m orbit / ${scenario.altitude_rf_m} m RF-up`:'Scenario flight plan';
 if(scenario.terrain_clearance_m)$('flight-summary').textContent=(scenario.flight_type==='racetrack'?`${scenario.straight_length_m} m straights / ${scenario.turn_radius_m} m turns`:scenario.radius_m?`${scenario.radius_m} m orbit`:'Terrain-following route')+` / ≥${scenario.terrain_clearance_m} m AGL / ${scenario.speed_m_s} m/s`;
 const noise=scenario.receiver_noise;$('noise-summary').textContent=noise?(noise.enabled?`${noise.noise_power_offset_db} dB versus receiver noise model`+(noise.noise_power_offset_db!==0?' · demo adjustment':''):'Thermal noise off'):'Not recorded';
 $('propagation-summary').textContent=typeof scenario.propagation==='object'?`${scenario.propagation.path_solver} / depth ${scenario.propagation.max_depth}`:(scenario.propagation||'Recorded propagation');
 document.querySelector('[data-process="skill"]').querySelector('h3').textContent=s.display?.title||scenario.skill_name||'RF Skill';
 RFSkillDisplay.render($('skill-display'),s);
 $('clock').textContent=sync.status==='matched'?`RF T+ ${(p.sim_elapsed_s||0).toFixed(3)} s`+(!state.no_render?` / view T+ ${((sync.camera_sim_time_ns-(p.origin_ns||0))/1e9).toFixed(3)} s`:''):'WAITING FOR MATCHED TIMES';$('position').textContent=sync.status==='matched'&&p.position_rf_m?`N ${p.position_rf_m[0].toFixed(1)} / W ${p.position_rf_m[1].toFixed(1)} / UP ${p.position_rf_m[2].toFixed(1)} m`:'NO MATCHED PLATFORM TELEMETRY';
 if(state.camera.available){$('camera').hidden=false;$('camera-empty').hidden=true;$('camera-status').textContent=state.playback?'RECORDED FRAME':p.status==='paused'?'PAUSED FRAME':p.status==='complete'?'LAST FRAME':state.camera.age_s>3?'CAMERA LAG':'AIRSIM CAMERA';$('camera-status').classList.toggle('warning',state.camera.age_s>3);}else{$('camera').hidden=true;$('camera-empty').hidden=false;$('camera-status').textContent=state.no_render?'RENDERING DISABLED':'WAITING FOR MATCHED CAMERA';}
 const visible=sync.status==='matched'?p.direct_visible:null;$('visibility').innerHTML=visible?`<i style="background:${visible.every(Boolean)?'#55d7d0':'#e6b96c'}"></i> Receiver direct paths: ${visible.map((v,i)=>'S'+i+' '+(v?'clear':'blocked')).join(' / ')}`:'<i></i> Visibility: awaiting matched geometry';
 const lag=sync.status==='matched'?Math.max(0,(sync.latest_rf_sim_time_ns-sync.rf_sim_time_ns)/1e9):null;
 $('sync-status').textContent=sync.status==='matched'?(state.no_render?'RF EPOCH MATCHED':`CAMERA / RF Δ ${sync.offset_ms.toFixed(0)} ms`):'WAITING FOR MATCHED TIMES';
 $('scene-rate').textContent=(state.playback?'Recorded performance · ':'')+(p.status==='paused'?'Paused':`${(p.simulation_speed||0).toFixed(2)}× sim / wall`)+(lag!==null?` · displayed RF ${lag.toFixed(2)} s behind latest`:'');
 groundtrack(sync.status==='matched'?p:{},state.scenario);
 $('path-summary').replaceChildren(...(sync.status==='matched'?p.site_paths||[]:[]).map((site,i)=>{const row=document.createElement('p'),echoes=site.reflected_paths_per_element||[];
  row.textContent=`${site.id}: ${site.direct_elements}/${site.elements} elements have a direct path. Reflected paths per element: ${echoes.join(', ')}. ${site.direct_elements===0?'Echoes and receiver noise only; no direct path.':''}`;return row;}));
 const channels=(scenario.sites||[]).reduce((sum,site)=>sum+(site.channels?.length||0),0)||8;
 const requiredRate=channels*(fs||2e6)*8/1e6;
 $('throughput-caption').textContent=`Wall-clock throughput at the displayed RF epoch. ${channels} cf32 channels require ${requiredRate.toFixed(1)} MB/s at real time.`;
 const rate=(transport.payload_bytes_per_second||0)/1e6;gauge(rate,requiredRate);$('throughput').textContent=rate.toFixed(2);$('payload').textContent=((transport.payload_bytes||0)/1e6).toFixed(1)+' MB';$('windows').textContent=transport.complete_windows||0;$('latency').textContent=s.processing_latency_ms?s.processing_latency_ms.toFixed(0)+' ms':'—';$('stream-state').textContent=(state.playback?'RECORDED':p.status==='paused'?'PAUSED':transport.status||'NO DATA').toUpperCase();
 if(state.playback){$('playback-seek').value=state.playback.frame_time_s||0;$('playback-time').textContent=`T+ ${(state.playback.frame_time_s||0).toFixed(3)} / ${state.playback.end_s.toFixed(3)} s ready`;}
 $('events').replaceChildren(...state.events.map(e=>{const row=document.createElement('div');row.textContent=e.time+'  '+e.message;return row;}));
}
async function present(state){
 renderControls(state);
 if(player.id&&state.playback?.id!==player.id)return;
 const generation=presentationGeneration,epoch=state.synchronization?.rf_sim_time_ns;
 if(!state.playback&&lastStatus?.producer.presentation_session===state.producer.presentation_session&&epoch<lastStatus?.synchronization?.rf_sim_time_ns)return;
 let prepared=null;
 if(state.camera.available&&lastFrame!==state.camera.url){
  prepared=$('camera').cloneNode(false);prepared.src=state.camera.url;
  let timer;
  try{await Promise.race([prepared.decode(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Camera image is delayed; holding synchronized frame')),6000);})]);}
  finally{clearTimeout(timer);}
 }
 if(generation!==presentationGeneration)return;
 await new Promise(resolve=>requestAnimationFrame(()=>{
  if(generation===presentationGeneration){
   if(prepared){$('camera').replaceWith(prepared);lastFrame=state.camera.url;}
   render(state);
  }
  resolve();
 }));
}
async function poll(){
 const now=performance.now(),elapsed=(now-player.lastTick)/1000;player.lastTick=now;
 if(player.id&&player.playing)player.time=player.following?player.end:Math.min(player.end,player.time+elapsed*player.rate);
 const generation=presentationGeneration,url=player.id?`/api/status?recording=${player.id}&time_s=${player.time}`:'/api/status';
 try{
  const response=await fetch(url,{signal:AbortSignal.timeout(4000)});if(!response.ok)throw Error('Status endpoint unavailable');
  const state=await response.json();if(generation===presentationGeneration)await present(state);
  $('connection').textContent=state.replay_only?'REPLAY · LOCALHOST':'LOCALHOST · CONNECTED';
 }catch(e){$('connection').textContent=e.message.startsWith('Camera image')?'WAITING FOR CAMERA · FRAME HELD':'DISCONNECTED · FRAME HELD';}
 // Freeze the playback clock during a long fetch/decode stall.
 if(performance.now()-now>300)player.lastTick=performance.now();
 setTimeout(poll,100);
}
window.addEventListener('resize',()=>lastStatus&&render(lastStatus));poll();
