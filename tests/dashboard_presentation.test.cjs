// Run the shipped UI with controllable image decoding and a small DOM adapter.
// No npm packages are needed: CI must cover delayed video, not just Python JSON.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function dashboard(){
 const elements=new Map(),decodes=[],listeners={},draws=[],requests=[];
 function element(id){
  if(elements.has(id))return elements.get(id);
  const children=new Map();
  const node={id,hidden:false,textContent:'',classList:{toggle(){}},
   querySelector(selector){if(!children.has(selector))children.set(selector,element(id+selector));return children.get(selector);},
   getBoundingClientRect(){return {width:400,height:200};},
   getContext(){return new Proxy({},{get:(_,key)=>()=>draws.push(id+':'+key),set:()=>true});},
   replaceChildren(){},
   cloneNode(){return {id,src:'',decode(){return new Promise((resolve,reject)=>decodes.push({resolve,reject}));}};},
   replaceWith(replacement){replacement.replaceWith=this.replaceWith;replacement.cloneNode=this.cloneNode;replacement.classList=this.classList;elements.set(id,replacement);},
  };
  elements.set(id,node);return node;
 }
 element('site-status').children=[element('site0'),element('site1')];
 const context=vm.createContext({document:{getElementById:element,querySelector:element,createElement:element},
  window:{addEventListener:(event,callback)=>listeners[event]=callback},devicePixelRatio:1,
  fetch:(url,options)=>{requests.push({url,options});return new Promise(()=>{});},AbortSignal,setTimeout,clearTimeout,
  requestAnimationFrame:callback=>queueMicrotask(callback),performance,console});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/airsim_rf/dashboard_static/app.js'),'utf8'),context);
 return {context,element,decodes,listeners,draws,requests};
}

function frame(index){
 return {token:'test',processes:{},ready:false,busy:false,events:[],scenario:{},no_render:false,
  producer:{status:'running',presentation_session:'mission-a',origin_ns:0,sim_elapsed_s:index*.12,position_rf_m:[index,0,200],history:[]},
  skill:{sim_time_ns:index*120000000,complete_windows:index+1,payload_bytes:(index+1)*1000000},
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
