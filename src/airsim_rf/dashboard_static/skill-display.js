'use strict';
// RF Skill Display v1: data-only descriptors and JSON Pointer bindings.
// No algorithm names, scenario kinds, remote scripts, HTML, or expressions.
(function(root){
 const states=new WeakMap(),colors=['#55d7d0','#e6b96c','#ac9aea','#8cc673'];
 function pointer(value,path,variables={}){
  if(path==='')return value;
  if(typeof path!=='string'||!path.startsWith('/'))return undefined;
  for(let key of path.slice(1).split('/')){
   key=key.replace(/\{([a-z][a-z0-9_-]*)\}/g,(_,name)=>variables[name]??'').replace(/~1/g,'/').replace(/~0/g,'~');
   if(value===null||typeof value!=='object'||!Object.hasOwn(value,key))return undefined;
   value=value[key];
  }
  return value;
 }
 function binding(frame,spec,variables={}){
  if(!spec||typeof spec!=='object')return undefined;
  if(Object.hasOwn(spec,'value'))return spec.value;
  const value=pointer(frame,spec.path,variables);
  if(spec.each){if(!Array.isArray(value))return [];return value.map((item,index)=>pointer(item,spec.each,{...variables,index}));}
  return value;
 }
 function node(tag,options={}){const result=document.createElement(tag);for(const [key,value] of Object.entries(options))result[key]=value;return result;}
 const label=axis=>axis?.label?(axis.unit?`${axis.label} (${axis.unit})`:axis.label):'';
 function bounds(values,fallback=[0,1]){const finite=values.filter(Number.isFinite);if(!finite.length)return fallback;let lo=Math.min(...finite),hi=Math.max(...finite);if(lo===hi){lo-=.5;hi+=.5;}return [lo,hi];}
 function surface(canvas){const rect=canvas.getBoundingClientRect(),ratio=root.devicePixelRatio||1;
  canvas.width=Math.max(1,Math.round(rect.width*ratio));canvas.height=Math.max(1,Math.round(rect.height*ratio));
  const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.clearRect(0,0,rect.width,rect.height);return [ctx,rect.width,rect.height];}
 function axes(canvas,xRange,yRange,xAxis,yAxis){const [ctx,w,h]=surface(canvas),m={l:66,r:18,t:16,b:48},pw=Math.max(1,w-m.l-m.r),ph=Math.max(1,h-m.t-m.b);
  const px=v=>m.l+(v-xRange[0])/(xRange[1]-xRange[0])*pw,py=v=>m.t+(yRange[1]-v)/(yRange[1]-yRange[0])*ph;
  ctx.font='10px monospace';ctx.lineWidth=.6;ctx.strokeStyle='#24343e';ctx.fillStyle='#a0b1bd';
  for(let i=0;i<=4;i++){
   const y=yRange[0]+i*(yRange[1]-yRange[0])/4,x=xRange[0]+i*(xRange[1]-xRange[0])/4;
   ctx.beginPath();ctx.moveTo(m.l,py(y));ctx.lineTo(w-m.r,py(y));ctx.stroke();ctx.textAlign='right';ctx.fillText(formatNumber(y),m.l-8,py(y)+3);
   ctx.textAlign='center';ctx.fillText(formatNumber(x),px(x),h-29);
  }
  ctx.fillText(label(xAxis),m.l+pw/2,h-8);ctx.save();ctx.translate(12,m.t+ph/2);ctx.rotate(-Math.PI/2);ctx.fillText(label(yAxis),0,0);ctx.restore();
  return {ctx,w,h,m,pw,ph,px,py};
 }
 function formatNumber(value){return Math.abs(value)>=10000?value.toExponential(1):Number.isInteger(value)?String(value):value.toFixed(1);}
 function noData(ctx,w,h){ctx.fillStyle='#82929f';ctx.textAlign='center';ctx.fillText('Awaiting skill data',w/2,h/2);}
 function seriesData(frame,panel,vars){const value=binding(frame,panel.series,vars);return Array.isArray(value)?(Array.isArray(value[0])?value:[value]):[];}
 function line(canvas,panel,frame,vars){const curves=seriesData(frame,panel,vars),length=Math.max(0,...curves.map(row=>row.length));
  const x=binding(frame,panel.x?.data,vars)||Array.from({length},(_,i)=>i+(panel.x?.index_start||0));
  const {ctx,w,h,m,pw,ph,px,py}=axes(canvas,panel.x?.range||bounds(x),panel.y?.range||bounds(curves.flat()),panel.x,panel.y);
  if(!length){noData(ctx,w,h);return;}
  ctx.save();ctx.beginPath();ctx.rect(m.l,m.t,pw,ph);ctx.clip();
  curves.forEach((row,k)=>{ctx.strokeStyle=colors[k%colors.length];ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=1.5;ctx.beginPath();let pen=false;
   row.forEach((v,i)=>{if(!Number.isFinite(v)||!Number.isFinite(x[i])){pen=false;return;}if(panel.type==='scatter'||panel.points){ctx.moveTo(px(x[i])+2,py(v));ctx.arc(px(x[i]),py(v),2,0,2*Math.PI);}
    if(panel.type!=='scatter'){if(pen)ctx.lineTo(px(x[i]),py(v));else ctx.moveTo(px(x[i]),py(v));pen=true;}});
   if(panel.type==='scatter')ctx.fill();else ctx.stroke();});ctx.restore();
 }
 function polar(canvas,panel,frame,vars){const [ctx,w,h]=surface(canvas),angles=binding(frame,panel.x?.data,vars)||[],curves=seriesData(frame,panel,vars),range=panel.y.range;
  const cx=w/2,cy=(h-22)/2,r=Math.max(1,Math.min(w-110,h-76)/2);
  const point=(angle,value)=>{const theta=angle*Math.PI/180,radius=r*(Math.max(range[0],Math.min(range[1],value))-range[0])/(range[1]-range[0]);return [cx-Math.sin(theta)*radius,cy-Math.cos(theta)*radius];};
  ctx.font='10px monospace';ctx.textAlign='center';ctx.strokeStyle='#2d424e';ctx.fillStyle='#a0b1bd';ctx.lineWidth=.7;
  for(const tick of panel.y.ticks||[range[0],(range[0]+range[1])/2,range[1]]){const radius=r*(tick-range[0])/(range[1]-range[0]);ctx.beginPath();ctx.arc(cx,cy,radius,0,2*Math.PI);ctx.stroke();ctx.fillText(`${tick} ${panel.y.unit||''}`,cx+radius*.707+13,cy+radius*.707+3);}
  for(let angle=-180;angle<180;angle+=45){const [x,y]=point(angle,range[1]);ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(x,y);ctx.stroke();}
  for(const [text,x,y] of [['0°',cx,cy-r-12],['±180°',cx,cy+r+16],['+90°',cx-r-27,cy+3],['−90°',cx+r+27,cy+3]])ctx.fillText(text,x,y);
  ctx.fillText(label(panel.y),cx,h-7);
  if(!angles.length||!curves.length){noData(ctx,w,h);return;}
  curves.forEach((values,k)=>{ctx.strokeStyle=colors[k%colors.length];ctx.lineWidth=1.7;ctx.beginPath();let started=false;
   values.forEach((v,i)=>{if(!Number.isFinite(v)||!Number.isFinite(angles[i]))return;const [x,y]=point(angles[i],v);if(started)ctx.lineTo(x,y);else ctx.moveTo(x,y);started=true;});
   if(angles.at(-1)-angles[0]>=Number(panel.x.period||360)-1)ctx.closePath();ctx.stroke();});
 }
 function heatColor(value,range){const f=Math.max(0,Math.min(1,(value-range[0])/(range[1]-range[0])));return `rgb(${Math.round(13+217*f*f)},${Math.round(21+189*f)},${Math.round(42+70*Math.sin(f*Math.PI))})`;}
 function matrix(canvas,panel,frame,vars){const history=panel.type==='waterfall';
  const rows=(binding(frame,history?panel.rows:panel.values,vars)||[]).map(row=>Array.isArray(row)?row:[]),xs=binding(frame,panel.x?.data,vars)||[];
  const ys=history?Array.from({length:rows.length},(_,i)=>i):binding(frame,panel.y?.data,vars)||[];
  const chart=axes(canvas,panel.x?.range||bounds(xs),panel.y?.range||bounds(ys),panel.x,panel.y),{ctx,w,h,m,pw,ph}=chart;
  if(!rows.length||!xs.length||!ys.length){noData(ctx,w,h);return;}
  for(let row=0;row<rows.length;row++)for(let col=0;col<rows[row].length;col++){
   const v=rows[row][col];if(!Number.isFinite(v))continue;ctx.fillStyle=heatColor(v,panel.color.range);
   ctx.fillRect(m.l+col*pw/xs.length,m.t+(rows.length-row-1)*ph/rows.length,pw/xs.length+1,ph/rows.length+1);
  }
  // Explicit color legend: every RF skill supplies its quantity and units.
  ctx.textAlign='center';ctx.fillStyle='#a0b1bd';ctx.fillText(`${label(panel.color)} · ${panel.color.range[0]} to ${panel.color.range[1]}`,m.l+pw/2,11);
 }
 function validate(manifest){
  if(!manifest||manifest.schema_version!==1)throw Error('Unsupported or missing RF skill display schema');
  if(typeof manifest.id!=='string'||typeof manifest.title!=='string'||!Array.isArray(manifest.panels)||manifest.panels.length>32)throw Error('Invalid RF skill display description');
  const selectorIds=new Set();if(manifest.selectors!==undefined&&!Array.isArray(manifest.selectors))throw Error('Invalid display selectors');
  if((manifest.selectors||[]).length>16)throw Error('Too many display selectors');
  for(const selector of manifest.selectors||[]){if(!selector||!/^[a-z][a-z0-9-]*$/.test(selector.id)||selectorIds.has(selector.id)||!Array.isArray(selector.options)||!selector.options.length)throw Error('Invalid display selector');selectorIds.add(selector.id);}
  const ids=new Set();for(const panel of manifest.panels){if(!panel||!/^[-a-zA-Z0-9_]+$/.test(panel.id)||ids.has(panel.id))throw Error('Invalid or duplicate display panel ID');ids.add(panel.id);
   if(!['line','scatter','polar','heatmap','waterfall','metrics','table'].includes(panel.type))continue;
   if(['polar'].includes(panel.type)&&(!Array.isArray(panel.y?.range)||panel.y.range[1]<=panel.y.range[0]))throw Error('Polar display requires an increasing radial range');
   if(['waterfall','heatmap'].includes(panel.type)&&(!Array.isArray(panel.color?.range)||panel.color.range[1]<=panel.color.range[0]))throw Error('Matrix display requires an increasing color range');
  }
  return manifest;
 }
 function render(container,frame){
  let manifest;try{manifest=validate(frame.display);}catch(error){container.replaceChildren(node('p',{className:'note',textContent:error.message}));states.delete(container);return;}
  const signature=JSON.stringify(manifest);let state=states.get(container);
  if(!state||state.signature!==signature){
   state={signature,variables:{},panels:[],selectors:[],frame};states.set(container,state);
   const heading=node('div',{className:'panel skill-display-heading'}),title=node('h3',{textContent:manifest.title});heading.appendChild(title);
   for(const selector of manifest.selectors||[]){const labelNode=node('label',{className:'receiver-picker',textContent:selector.label}),select=node('select',{id:'skill-select-'+selector.id});
    select.setAttribute('aria-label',selector.label);state.variables[selector.id]=String(selector.options?.[0]?.value??'');
    select.onchange=()=>{state.variables[selector.id]=select.value;paint(state);};labelNode.appendChild(select);heading.appendChild(labelNode);state.selectors.push({definition:selector,node:select,signature:''});}
   const nodes=[heading];
   for(const panel of manifest.panels){const article=node('article',{className:'panel skill-widget'}),head=node('div',{className:'panel-head'});
    article.id='skill-panel-'+panel.id;head.appendChild(node('h3',{textContent:panel.title||panel.id}));article.appendChild(head);
    const content=node(['metrics','table'].includes(panel.type)?'div':'canvas',{id:'skill-'+panel.id,className:panel.type==='polar'?'plot spatial-polar':panel.type==='metrics'?'skill-metrics':panel.type==='table'?'skill-table':'plot'});
    content.setAttribute('aria-label',panel.title||panel.id);article.appendChild(content);
    if(panel.legend?.length){const legend=node('div',{className:'skill-legend'});panel.legend.forEach((text,index)=>{const entry=node('span',{textContent:String(text)});entry.style.color=colors[index%colors.length];legend.appendChild(entry);});article.appendChild(legend);}
    const caption=node('p',{className:'note',id:'skill-caption-'+panel.id});article.appendChild(caption);nodes.push(article);state.panels.push({definition:panel,content,caption});
   }
   container.replaceChildren(...nodes);
  }
  state.frame=frame;paint(state);
 }
 function paint(state){const frame=state.frame,vars=state.variables;
  for(const selector of state.selectors){const definition=selector.definition,options=definition.options||[];
   const available=options.map(option=>!option.available||Boolean(binding(frame,option.available,vars)?.length||binding(frame,option.available,vars)===true));
   if(!available[options.findIndex(o=>String(o.value)===vars[definition.id])]&&available.some(Boolean))vars[definition.id]=String(options[available.indexOf(true)].value);
   const signature=JSON.stringify(available);
   if(selector.signature!==signature){selector.node.replaceChildren(...options.map((option,index)=>node('option',{value:String(option.value),textContent:option.label+(available[index]?'':' · no saved data'),disabled:!available[index]})));selector.signature=signature;}
   selector.node.value=vars[definition.id];
  }
  for(const widget of state.panels){const panel=widget.definition;widget.caption.textContent=panel.caption||'';
   try{
    if(panel.type==='line'||panel.type==='scatter')line(widget.content,panel,frame,vars);
    else if(panel.type==='polar'){polar(widget.content,panel,frame,vars);const angles=binding(frame,panel.x?.data,vars)||[];
     if(angles.length&&angles.at(-1)-angles[0]<Number(panel.x.period||360)-1)widget.caption.textContent+=` · Partial coverage: ${angles[0]}° to ${angles.at(-1)}° only`;}
    else if(panel.type==='heatmap'||panel.type==='waterfall')matrix(widget.content,panel,frame,vars);
    else if(panel.type==='metrics'){
     widget.content.replaceChildren(...(panel.items||[]).map(item=>{let value=binding(frame,item.value,vars),text=item.empty||'—';
      if(item.valid_when&&!binding(frame,item.valid_when,vars))value=null;
      if(typeof value==='boolean')text=value?(item.true_label||'Yes'):(item.false_label||'No');
      else if(typeof value==='number'&&Number.isFinite(value))text=value.toFixed(Math.max(0,Math.min(8,item.precision??2)))+(item.unit?' '+item.unit:'');
      else if(typeof value==='string')text=value;
      const row=node('div');row.appendChild(node('span',{textContent:item.label}));row.appendChild(node('strong',{textContent:text}));return row;}));
    }else if(panel.type==='table'){
     const rows=binding(frame,panel.rows,vars)||[],table=node('table'),head=node('tr');
     for(const column of panel.columns||[])head.appendChild(node('th',{textContent:column.label}));table.appendChild(head);
     for(const row of rows.slice(0,100)){const tr=node('tr');for(const column of panel.columns||[])tr.appendChild(node('td',{textContent:String(pointer(row,column.path,vars)??'—')}));table.appendChild(tr);}widget.content.replaceChildren(table);
    }else widget.caption.textContent=`Unsupported display primitive: ${panel.type}`;
   }catch(error){widget.caption.textContent='Display data unavailable: '+error.message;}
  }
 }
 root.RFSkillDisplay={render,validate,binding,pointer};
})(globalThis);
