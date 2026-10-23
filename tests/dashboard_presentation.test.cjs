// Run the shipped UI with controllable image decoding and a small DOM adapter.
// No npm packages are needed: CI must cover delayed video, not just Python JSON.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function dashboard(){
 const elements=new Map(),decodes=[],listeners={},draws=[],drawCalls=[],requests=[];let created=0;
 function element(id){
  if(elements.has(id))return elements.get(id);
  const children=new Map();
  const node={hidden:false,textContent:'',style:{},children:[],classList:{toggle(){}},
   appendChild(child){this.children.push(child);return child;},
   setAttribute(name,value){this[name]=value;},
   querySelector(selector){if(!children.has(selector))children.set(selector,element(id+selector));return children.get(selector);},
   getBoundingClientRect(){return {width:400,height:200};},
   getContext(){return new Proxy({},{get:(_,key)=>(...args)=>{draws.push(node.id+':'+key);drawCalls.push({id:node.id,method:key,args});},set:()=>true});},
   replaceChildren(...nodes){this.children=nodes;},
   cloneNode(){return {id,src:'',decode(){return new Promise((resolve,reject)=>decodes.push({resolve,reject}));}};},
   replaceWith(replacement){replacement.replaceWith=this.replaceWith;replacement.cloneNode=this.cloneNode;replacement.classList=this.classList;elements.set(id,replacement);},
  };
  let identifier=id;Object.defineProperty(node,'id',{get(){return identifier;},set(value){identifier=value;elements.set(value,node);}});
  elements.set(id,node);return node;
 }
 element('site-status').children=[element('site0'),element('site1')];
 const context=vm.createContext({document:{getElementById:element,querySelector:element,createElement:tag=>element(tag+'-'+created++)},
  window:{addEventListener:(event,callback)=>listeners[event]=callback},devicePixelRatio:1,
  fetch:(url,options)=>{requests.push({url,options});return new Promise(()=>{});},AbortSignal,setTimeout,clearTimeout,
  requestAnimationFrame:callback=>queueMicrotask(callback),performance,console});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/airsim_rf/dashboard_static/skill-display.js'),'utf8'),context);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/airsim_rf/dashboard_static/app.js'),'utf8'),context);
 return {context,element,decodes,listeners,draws,drawCalls,requests};
}

const descriptor=name=>JSON.parse(fs.readFileSync(path.join(__dirname,'../src/airsim_rf/assets/legacy-display-'+name+'.json'),'utf8'));
function frame(index){
 return {token:'test',processes:{},ready:false,busy:false,events:[],scenario:{},no_render:false,
  producer:{status:'running',presentation_session:'mission-a',origin_ns:0,sim_elapsed_s:index*.12,position_rf_m:[index,0,200],history:[]},
  skill:{display:descriptor('df'),sim_time_ns:index*120000000,complete_windows:index+1,payload_bytes:(index+1)*1000000},
  // A future live counter must never leak into the mission display.
  transport:{complete_windows:999,payload_bytes:999000000},
  camera:{available:true,url:'/camera.jpg?frame='+index,age_s:0},
  synchronization:{status:'matched',rf_sim_time_ns:index*120000000,camera_sim_time_ns:index*120000000,latest_rf_sim_time_ns:index*120000000,offset_ms:0}};
}

test('image, clock, position, counters and plots wait for decoding and commit together',async()=>{
 const ui=dashboard(),first=ui.context.present(frame(0));ui.decodes.shift().resolve();await first;
 const clock=ui.element('clock').textContent,position=ui.element('position').textContent;
 assert.equal(ui.element('windows').textContent,1);
 assert.equal(ui.element('payload').textContent,'1.0 MB');
 const draws=ui.draws.length,second=ui.context.present(frame(1));
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(ui.element('camera').src,'/camera.jpg?frame=0');
 assert.equal(ui.element('clock').textContent,clock);
 assert.equal(ui.element('position').textContent,position);
 assert.equal(ui.element('windows').textContent,1);
 assert.equal(ui.draws.length,draws);
 ui.decodes.shift().resolve();await second;
 assert.equal(ui.element('camera').src,'/camera.jpg?frame=1');
 assert.match(ui.element('clock').textContent,/0\.120/);
 assert.match(ui.element('position').textContent,/N 1\.0/);
 assert.equal(ui.element('windows').textContent,2);
 assert.equal(ui.element('payload').textContent,'2.0 MB');
 assert.ok(ui.draws.length>draws);
});

test('failed video and an out-of-order status cannot replace a coherent frame',async()=>{
 const ui=dashboard(),first=ui.context.present(frame(1));ui.decodes.shift().resolve();await first;
 const clock=ui.element('clock').textContent,second=ui.context.present(frame(2));
 ui.decodes.shift().reject(Error('Bad image'));await assert.rejects(second,/Bad image/);
 assert.equal(ui.element('camera').src,'/camera.jpg?frame=1');
 assert.equal(ui.element('clock').textContent,clock);
 await ui.context.present(frame(0));
 assert.equal(ui.decodes.length,0);
 assert.equal(ui.element('clock').textContent,clock);
 // An intentional new mission can restart its simulation clock.
 const next=frame(0);next.producer.presentation_session='mission-b';
 const restarted=ui.context.present(next);ui.decodes.shift().resolve();await restarted;
 assert.match(ui.element('clock').textContent,/0\.000/);
});

test('live pause/resume controls work while the next camera image is pending',async()=>{
 const ui=dashboard(),first=ui.context.present(frame(0));ui.decodes.shift().resolve();await first;
 const paused=frame(1);paused.producer.status='paused';const pending=ui.context.present(paused);
 assert.equal(ui.element('pause').textContent,'Resume computation');
 ui.element('pause').onclick();
 assert.equal(ui.requests.at(-1).url,'/api/resume');
 assert.equal(ui.element('windows').textContent,1);
 ui.decodes.shift().resolve();await pending;
});

test('recorded playback can seek backward atomically without pausing computation',async()=>{
 const ui=dashboard(),id='0123456789abcdef';ui.context.chooseRecording(id);
 function saved(index){const state=frame(index);state.recordings=[{id,created_utc:'2026-10-22T00:00:00Z'}];
  state.playback={id,start_s:0,end_s:.24,frame_time_s:index*.12,playable_frames:3,duration_s:.36,computed_s:.36,status:'complete'};
  state.control_producer={status:'running'};return state;}
 const first=ui.context.present(saved(1));ui.decodes.shift().resolve();await first;
 assert.match(ui.element('clock').textContent,/0\.120/);
 assert.equal(ui.element('record-progress').value,.36);
 const requests=ui.requests.length;
 ui.element('playback-play').onclick();
 assert.equal(ui.requests.length,requests); // Playback pause never calls /api/pause.
 ui.element('playback-seek').value=0;ui.element('playback-seek').oninput();
 const earlier=ui.context.present(saved(0));
 assert.match(ui.element('clock').textContent,/0\.120/);
 ui.decodes.shift().resolve();await earlier;
 assert.match(ui.element('clock').textContent,/0\.000/);
 assert.equal(ui.element('windows').textContent,1);
 assert.equal(ui.element('camera').src,'/camera.jpg?frame=0');
 assert.equal(ui.element('playback-seek').value,0);
 assert.equal(ui.element('record-progress').value,.36); // Seeking cannot erase completed computation.
});

test('receiver selection switches actual spectra and saved waterfall without advancing playback',{timeout:3000},async()=>{
 const ui=dashboard(),state=frame(0);
 state.scenario.sites=[{id:'site0',center_rf_m:[0,-25,110]},{id:'site1',center_rf_m:[0,25,110]}];
 state.skill.receiver_spectra=[
  {site_id:'site0',psd:{frequency_khz:[-50,50],density_db_v2_hz:[-170,-130]}},
  {site_id:'site1',psd:{frequency_khz:[-50,50],density_db_v2_hz:[-120,-175]}}];
 state.skill.waterfall=[{sim_time_ns:0,psd_db:[-170,-130],site_psd_db:[[-170,-130],[-120,-175]]}];
 const shown=ui.context.present(state);ui.decodes.shift().resolve();await shown;
 const clock=ui.element('clock').textContent,requests=ui.requests.length;
 ui.element('skill-select-receiver').value='1';ui.element('skill-select-receiver').onchange();
 assert.equal(ui.element('skill-select-receiver').value,'1');
 const selected=ui.drawCalls.filter(c=>c.id==='skill-psd'&&c.method==='moveTo').at(-1);
 assert.equal(selected.args[1],43.2);
 const lastMove=ui.drawCalls.filter(c=>c.id==='skill-psd'&&c.method==='moveTo').at(-1);
 // Site 1's first bin is -120 dB: y=10+(15/75)*(200-10-24).
 assert.equal(lastMove.args[1],43.2);
 assert.equal(ui.element('clock').textContent,clock);
 assert.equal(ui.requests.length,requests);
 assert.equal(ui.element('camera').src,'/camera.jpg?frame=0');
 const labels=ui.drawCalls.filter(c=>c.method==='fillText').map(c=>c.args[0]);
 for(const label of ['Pseudospectrum (dB)','Relative power (dB)','Phase (rad)'])assert.ok(labels.includes(label));
});

test('missing receiver data disables that option instead of relabeling another receiver',async()=>{
 const ui=dashboard(),state=frame(0);state.camera.available=false;
 state.skill.receiver_spectra=[{site_id:'site0',psd:{frequency_khz:[0],density_db_v2_hz:[-150]}}];
 state.skill.waterfall=[{timestamp_ns:0,site_psd_db:[[-150]]}];
 await ui.context.present(state);
 assert.equal(ui.element('skill-select-receiver').children[1].disabled,true);
 assert.match(ui.element('skill-select-receiver').children[1].textContent,/no saved data/);
});

test('circular MUSIC closes the full azimuth seam and identifies partial older searches',()=>{
 const ui=dashboard();
 const circular=frame(0);circular.camera.available=false;circular.skill.angle_grid_deg=[-180,-90,0,90,180];circular.skill.music_db=[[-5,-40,-5,-40,-5]];ui.context.render(circular);
 const path=ui.drawCalls.filter(c=>c.id==='skill-spatial'&&(c.method==='moveTo'||c.method==='lineTo')).slice(-5);
 assert.ok(Math.abs(path[0].args[0]-path.at(-1).args[0])<1e-9);
 assert.ok(Math.abs(path[0].args[1]-path.at(-1).args[1])<1e-9);
 assert.ok(ui.drawCalls.some(c=>c.id==='skill-spatial'&&c.method==='closePath'));
 const state=frame(0);state.camera.available=false;state.skill.angle_grid_deg=[-70,0,70];state.skill.music_db=[[-40,0,-40]];
 ui.context.render(state);
 assert.match(ui.element('skill-caption-spatial').textContent,/−?\-?70° to 70° only/);
});

test('scenario selector names packaged inputs and disables switching during a mission',()=>{
 const ui=dashboard(),state=frame(0);
 state.scenario_catalog=[{id:'drone-orbit',title:'Direction finding'},{id:'mmwave-radar',title:'Radar racetrack'}];
 state.selected_scenario='mmwave-radar';ui.context.renderControls(state);
 assert.equal(ui.element('scenario-select').children[1].textContent,'Radar racetrack');
 assert.equal(ui.element('scenario-select').value,'mmwave-radar');
 assert.equal(ui.element('scenario-select').disabled,false);
 state.mission_started=true;ui.context.renderControls(state);
 assert.equal(ui.element('scenario-select').disabled,true);
});

test('radar view uses receiver result and labels range and range-rate axes',()=>{
 const ui=dashboard(),state=frame(0);state.camera.available=false;
 state.scenario.skill_kind='direction-finding';state.skill.display=descriptor('radar');state.skill.radar={range_m:[0,10],range_rate_m_s:[-20,20],power_db:[[-10,5],[2,30]],detection:{detected:true,range_m:10,range_rate_m_s:20}};
 ui.context.render(state);
 assert.ok(ui.element('skill-display').children.some(n=>n.id==='skill-panel-range-doppler'));
 assert.ok(!ui.element('skill-display').children.some(n=>n.id==='skill-panel-spatial'));
 assert.match(ui.element('skill-detection').children[1].children[1].textContent,/10.0 m/);
 const labels=ui.drawCalls.filter(c=>c.id==='skill-range-doppler'&&c.method==='fillText').map(c=>c.args[0]);
 assert.ok(labels.includes('Range (m)')&&labels.includes('Range rate (m/s)'));
});

test('a third RF skill supplies metrics, scatter and a table without dashboard-specific code',async()=>{
 const ui=dashboard(),state=frame(0);state.camera.available=false;
 state.skill={sim_time_ns:0,complete_windows:1,snr:17.25,symbols:{i:[-1,1],q:[1,-1]},packets:[{protocol:'QPSK',count:12}],
  display:{schema_version:1,id:'unrelated-packet-skill',revision:'1',title:'Packet quality',panels:[
   {id:'quality',type:'metrics',title:'Link quality',items:[{label:'SNR',value:{path:'/snr'},unit:'dB',precision:2}]},
   {id:'symbols',type:'scatter',title:'Constellation',x:{data:{path:'/symbols/i'},label:'In-phase',unit:'V',range:[-2,2]},y:{label:'Quadrature',unit:'V',range:[-2,2]},series:{path:'/symbols/q'}},
   {id:'packets',type:'table',title:'Decoded packets',rows:{path:'/packets'},columns:[{label:'Protocol',path:'/protocol'},{label:'Count',path:'/count'}]}]}};
 await ui.context.present(state);
 assert.equal(ui.element('skill-quality').children[0].children[1].textContent,'17.25 dB');
 assert.equal(ui.element('skill-packets').children[0].children[1].children[0].textContent,'QPSK');
 assert.ok(ui.drawCalls.some(c=>c.id==='skill-symbols'&&c.method==='arc'));
 assert.ok(!ui.element('skill-display').children.some(n=>n.id==='skill-panel-spatial'));
});

test('skill layout changes wait for the matching camera and replay restores the prior layout',async()=>{
 const ui=dashboard(),first=ui.context.present(frame(0));ui.decodes.shift().resolve();await first;
 const radar=frame(1);radar.skill.display=descriptor('radar');
 const pending=ui.context.present(radar);
 assert.ok(ui.element('skill-display').children.some(n=>n.id==='skill-panel-spatial'));
 assert.ok(!ui.element('skill-display').children.some(n=>n.id==='skill-panel-range-doppler'));
 ui.decodes.shift().resolve();await pending;
 assert.ok(ui.element('skill-display').children.some(n=>n.id==='skill-panel-range-doppler'));
 ui.context.chooseRecording('0123456789abcdef');
 const earlier=frame(0);earlier.playback={id:'0123456789abcdef',start_s:0,end_s:1,frame_time_s:0,playable_frames:2,duration_s:1,computed_s:1,status:'complete'};
 const seeking=ui.context.present(earlier);ui.decodes.shift().resolve();await seeking;
 assert.ok(ui.element('skill-display').children.some(n=>n.id==='skill-panel-spatial'));
 assert.ok(!ui.element('skill-display').children.some(n=>n.id==='skill-panel-range-doppler'));
});

test('display bindings use escaped JSON pointers and unsupported versions clear stale panels',()=>{
 const ui=dashboard();
 const value=ui.context.RFSkillDisplay.binding({'a/b':{'~key':[2,3]}},{path:'/a~1b/~0key'});
 assert.deepEqual(Array.from(value),[2,3]);
 const state=frame(0);state.camera.available=false;ui.context.render(state);
 state.skill.display={schema_version:99};ui.context.render(state);
 assert.equal(ui.element('skill-display').children.length,1);
 assert.match(ui.element('skill-display').children[0].textContent,/Unsupported/);
});
