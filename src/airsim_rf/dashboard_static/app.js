'use strict';
let token='',lastFrame=-1,lastWindow=-1,lastStatus=null,waterRows=[];
const $=id=>document.getElementById(id);
function surface(id){const canvas=$(id),ratio=devicePixelRatio||1,rect=canvas.getBoundingClientRect();canvas.width=Math.round(rect.width*ratio);canvas.height=Math.round(rect.height*ratio);const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);return [ctx,rect.width,rect.height];}
function graph(id,x,curves,rangeX,rangeY,colors=['#55d7d0','#e6b96c'],points=false){
 const [ctx,w,h]=surface(id),m={l:40,r:13,t:10,b:24},pw=w-m.l-m.r,ph=h-m.t-m.b;
 const px=v=>m.l+(v-rangeX[0])/(rangeX[1]-rangeX[0])*pw,py=v=>m.t+(rangeY[1]-v)/(rangeY[1]-rangeY[0])*ph;
 ctx.font='9px monospace';ctx.textAlign='right';ctx.fillStyle='#6d8696';ctx.strokeStyle='#24343e';ctx.lineWidth=.6;
 for(let i=0;i<=4;i++){const y=rangeY[0]+i*(rangeY[1]-rangeY[0])/4;ctx.beginPath();ctx.moveTo(m.l,py(y));ctx.lineTo(w-m.r,py(y));ctx.stroke();ctx.fillText(y.toFixed(0),m.l-7,py(y)+3);}
 ctx.textAlign='center';for(let i=0;i<=4;i++){const xx=rangeX[0]+i*(rangeX[1]-rangeX[0])/4;ctx.fillText(xx.toFixed(0),px(xx),h-6);}
 if(!x?.length){ctx.fillStyle='#526f81';ctx.fillText('Awaiting received I/Q',w/2,h/2);return;}
 ctx.save();ctx.beginPath();ctx.rect(m.l,m.t,pw,ph);ctx.clip();
 curves.forEach((values,k)=>{ctx.strokeStyle=colors[k%colors.length];ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=1.5;ctx.beginPath();values.forEach((v,i)=>{if(i===0)ctx.moveTo(px(x[i]),py(v));else ctx.lineTo(px(x[i]),py(v));});ctx.stroke();if(points)values.forEach((v,i)=>{ctx.beginPath();ctx.arc(px(x[i]),py(v),3,0,Math.PI*2);ctx.fill();});});ctx.restore();
}
function gauge(rate){const [ctx,w,h]=surface('gauge'),cx=w/2,cy=h-16,r=Math.min(w/2-24,h-30);ctx.lineWidth=10;ctx.lineCap='round';ctx.strokeStyle='#22333e';ctx.beginPath();ctx.arc(cx,cy,r,Math.PI,2*Math.PI);ctx.stroke();const fraction=Math.min(rate/128,1);ctx.strokeStyle='#55d7d0';ctx.beginPath();ctx.arc(cx,cy,r,Math.PI,Math.PI+fraction*Math.PI);ctx.stroke();ctx.font='9px monospace';ctx.fillStyle='#607c8e';ctx.fillText('0',cx-r-5,cy+13);ctx.fillText('128',cx+r-15,cy+13);const angle=Math.PI+fraction*Math.PI;ctx.lineWidth=2;ctx.strokeStyle='#e6b96c';ctx.beginPath();ctx.moveTo(cx+Math.cos(angle)*(r-21),cy+Math.sin(angle)*(r-21));ctx.lineTo(cx+Math.cos(angle)*(r+6),cy+Math.sin(angle)*(r+6));ctx.stroke();}
function waterfall(){const [ctx,w,h]=surface('waterfall');if(!waterRows.length){ctx.font='9px monospace';ctx.fillStyle='#526f81';ctx.fillText('Spectrum waterfall appears with received windows',15,h/2);return;}const count=waterRows[0].length,dh=h/Math.max(waterRows.length,20),dw=w/count;waterRows.forEach((row,j)=>row.forEach((v,i)=>{let f=Math.max(0,Math.min(1,(v+178)/65));let r=Math.round(13+215*f*f),g=Math.round(21+190*f),b=Math.round(42+70*Math.sin(f*Math.PI));ctx.fillStyle=`rgb(${r},${g},${b})`;ctx.fillRect(i*dw,h-(j+1)*dh,dw+1,dh+1);}));}
function groundtrack(p,scenario){const [ctx,w,h]=surface('groundtrack'),cx=w/2,cy=h/2,scale=Math.min(w-36,h-36)/(scenario.terrain_width_m||800);
 const point=v=>[cx-v[1]*scale,cy-v[0]*scale];const grid=scenario.terrain_grid;
 if(grid){const heights=grid.heights_m.flat(),lo=Math.min(...heights),hi=Math.max(...heights);
  for(let y=0;y<grid.y_m.length-1;y++)for(let x=0;x<grid.x_m.length-1;x++){
   const cells=[[y,x],[y,x+1],[y+1,x+1],[y+1,x]];
   for(const triangle of [[0,1,2],[0,2,3]]){const vertices=triangle.map(k=>cells[k]),elevation=vertices.reduce((s,[j,i])=>s+grid.heights_m[j][i],0)/3,f=(elevation-lo)/Math.max(hi-lo,1);
    ctx.fillStyle=`rgb(${Math.round(30+105*f)},${Math.round(64+75*f)},${Math.round(47+42*f)})`;ctx.beginPath();vertices.forEach(([j,i],k)=>{const [px,py]=point([grid.x_m[i],grid.y_m[j]]);if(k)ctx.lineTo(px,py);else ctx.moveTo(px,py);});ctx.closePath();ctx.fill();}}
  ctx.font='9px monospace';ctx.fillStyle='#c3d5de';ctx.textAlign='left';ctx.fillText(`N ↑ · elevation ${lo.toFixed(0)}–${hi.toFixed(0)} m`,9,14);}
 ctx.strokeStyle='#6e8a96';ctx.setLineDash([3,3]);ctx.beginPath();ctx.arc(cx,cy,(scenario.radius_m||250)*scale,0,2*Math.PI);ctx.stroke();ctx.setLineDash([]);
 ctx.strokeStyle='#55d7d0';ctx.lineWidth=1.6;ctx.beginPath();(p.history||[]).forEach((row,i)=>{const [x,y]=point(row.position_rf_m);if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);});ctx.stroke();
 if(p.position_rf_m){const [x,y]=point(p.position_rf_m);ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(x,y,3,0,Math.PI*2);ctx.fill();}
 (p.site_paths||scenario.sites||[]).forEach((site,i)=>{const [x,y]=point(site.center_rf_m);ctx.fillStyle=i?'#e6b96c':'#55d7d0';ctx.fillRect(x-3,y-3,6,6);
  if(p.position_rf_m){const [tx,ty]=point(p.position_rf_m);ctx.strokeStyle=site.direct_elements?'#55d7d0':'#e6b96c';ctx.setLineDash(site.direct_elements?[]:[4,4]);ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(tx,ty);ctx.stroke();ctx.setLineDash([]);}
  if(site.blocker_rf_m){const [bx,by]=point(site.blocker_rf_m);ctx.strokeStyle='#ffae65';ctx.beginPath();ctx.moveTo(bx-4,by-4);ctx.lineTo(bx+4,by+4);ctx.moveTo(bx-4,by+4);ctx.lineTo(bx+4,by-4);ctx.stroke();}});
}
async function action(name){try{const response=await fetch('/api/'+name,{method:'POST',headers:{'X-Dashboard-Token':token}});if(!response.ok)throw Error(await response.text());}catch(error){$('error').textContent=error.message;$('error').hidden=false;}}
$('prepare').onclick=()=>action('prepare');$('start').onclick=()=>action('start');$('stop').onclick=()=>action('stop');$('pause').onclick=()=>action(lastStatus?.producer.status==='paused'?'resume':'pause');
function render(state){lastStatus=state;token=state.token;const s=state.skill,p=state.producer,transport=state.transport||s,sync=state.synchronization||{};const running=Object.values(state.processes).some(v=>v.state==='running');
 $('start').disabled=state.busy||!state.ready||state.mission_started;$('prepare').disabled=state.busy||state.ready;$('connection').textContent=state.ready?'SERVICES READY':state.busy?'PREPARING':'NOT READY';$('stop').disabled=state.busy||!running;$('pause').disabled=state.busy||p.status!=='running'&&p.status!=='paused';$('pause').textContent=p.status==='paused'?'Resume':'Pause';
 $('error').hidden=!state.error&&!p.error&&!transport.error;$('error').textContent=state.error||p.error||transport.error||'';
 for(const part of ['sim','rf','skill']){const element=document.querySelector(`[data-process="${part}"]`),process=state.processes[part],badge=element.querySelector('.status');badge.textContent=process?process.state.toUpperCase():'OFFLINE';badge.classList.toggle('on',process?.state==='running');element.querySelector('.identity').textContent=process?`${process.container||part} · PID ${process.pid}`:['Ready for launch','CUDA deployment','Coherent TCP metadata extension'][['sim','rf','skill'].indexOf(part)];}
 $('clock').textContent=sync.status==='matched'?`RF T+ ${(p.sim_elapsed_s||0).toFixed(3)} s`+(!state.no_render?` / view T+ ${((sync.camera_sim_time_ns-(p.origin_ns||0))/1e9).toFixed(3)} s`:''):'WAITING FOR MATCHED TIMES';$('position').textContent=sync.status==='matched'&&p.position_rf_m?`N ${p.position_rf_m[0].toFixed(1)} / W ${p.position_rf_m[1].toFixed(1)} / UP ${p.position_rf_m[2].toFixed(1)} m`:'NO MATCHED PLATFORM TELEMETRY';
 if(state.camera.available){$('camera').hidden=false;$('camera-empty').hidden=true;if(lastFrame!==state.camera.url){$('camera').src=state.camera.url;lastFrame=state.camera.url;}$('camera-status').textContent=p.status==='paused'?'PAUSED FRAME':p.status==='complete'?'LAST FRAME':state.camera.age_s>3?'CAMERA LAG':'AIRSIM CAMERA';$('camera-status').classList.toggle('warning',state.camera.age_s>3);}else{$('camera').hidden=true;$('camera-empty').hidden=false;$('camera-status').textContent=state.no_render?'RENDERING DISABLED':'WAITING FOR MATCHED CAMERA';}
 const visible=sync.status==='matched'?p.direct_visible:null;$('visibility').innerHTML=visible?`<i style="background:${visible.every(Boolean)?'#55d7d0':'#e6b96c'}"></i> Receiver direct paths: ${visible.map((v,i)=>'S'+i+' '+(v?'clear':'blocked')).join(' / ')}`:'<i></i> Visibility: awaiting matched geometry';
 const lag=sync.status==='matched'?Math.max(0,(sync.latest_rf_sim_time_ns-sync.rf_sim_time_ns)/1e9):null;
 $('sync-status').textContent=sync.status==='matched'?(state.no_render?'RF EPOCH MATCHED':`CAMERA / RF Δ ${sync.offset_ms.toFixed(0)} ms`):'WAITING FOR MATCHED TIMES';
 $('scene-rate').textContent=(p.status==='paused'?'Paused':`${(p.simulation_speed||0).toFixed(2)}× sim / wall`)+(lag!==null?` · displayed RF ${lag.toFixed(2)} s behind latest`:'');
 groundtrack(sync.status==='matched'?p:{},state.scenario);
 $('path-summary').replaceChildren(...(sync.status==='matched'?p.site_paths||[]:[]).map((site,i)=>{const row=document.createElement('p'),echoes=site.reflected_paths_per_element||[],power=s.bearings?.[i]?.received_power_dbm;
  row.textContent=`${site.id}: ${site.direct_elements}/${site.elements} elements have a direct path. Reflected paths per element: ${echoes.join(', ')}. ${power!==undefined?`Received ${power.toFixed(1)} dBm.`:''} ${site.direct_elements===0?'Echoes and receiver noise only; no direct path.':''}`;return row;}));
 const rate=(transport.payload_bytes_per_second||0)/1e6;gauge(rate);$('throughput').textContent=rate.toFixed(2);$('payload').textContent=((transport.payload_bytes||0)/1e6).toFixed(1)+' MB';$('windows').textContent=transport.complete_windows||0;$('latency').textContent=s.processing_latency_ms?s.processing_latency_ms.toFixed(0)+' ms':'—';$('stream-state').textContent=(p.status==='paused'?'PAUSED':transport.status||'NO DATA').toUpperCase();
 [0,1].forEach(i=>{const bearing=s.bearings?.[i],e=$('site-status').children[i].querySelector('span');e.textContent=!bearing?'Awaiting matched I/Q':!bearing.detected?'No stable MUSIC peak':visible&&!visible[i]?`${bearing.angle_deg.toFixed(1)}° · direct blocked`:`${bearing.angle_deg.toFixed(1)}° · candidate`;e.classList.toggle('warning',Boolean(bearing&&(!bearing.detected||visible&&!visible[i])));});
 graph('psd',s.psd?.frequency_khz,[s.psd?.density_db_v2_hz||[]],[-100,100],[-180,-105]);
 graph('music',s.angle_grid_deg,s.music_db||[],[-70,70],[-65,0]);graph('eigen',[1,2,3,4],s.eigenvalues_db||[],[1,4],[-60,0],undefined,true);graph('phase',[0,1,2,3],s.phase_rad?[s.phase_rad]:[],[0,3],[-9,9],undefined,true);
 if(s.waterfall?.length){waterRows=s.waterfall.map(row=>row.psd_db);lastWindow=s.complete_windows;
 const origin=p.origin_ns||0,first=(s.waterfall[0].sim_time_ns-origin)/1e9,last=(s.waterfall[s.waterfall.length-1].sim_time_ns-origin)/1e9;
 $('waterfall-caption').textContent=`RF T+ ${first.toFixed(2)}–${last.toFixed(2)} s · ${waterRows.length} rows · 12 ms PSD snapshots every 120 ms · −178 to −113 dB`;
 }else waterRows=[];waterfall();
 $('events').replaceChildren(...state.events.map(e=>{const row=document.createElement('div');row.textContent=e.time+'  '+e.message;return row;}));
}
async function poll(){try{const response=await fetch('/api/status');if(!response.ok)throw Error('Status endpoint unavailable');render(await response.json());$('connection').textContent='LOCALHOST · CONNECTED';}catch(e){$('connection').textContent='DISCONNECTED';}setTimeout(poll,700);}
window.addEventListener('resize',()=>lastStatus&&render(lastStatus));poll();
