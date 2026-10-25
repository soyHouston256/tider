/** A read-only map of the editable review, not a live infrastructure view. */
const NS = 'http://www.w3.org/2000/svg';
function svgNode(tag, attrs = {}, text) {
  const node = document.createElementNS(NS, tag);
  for (const [key,value] of Object.entries(attrs)) node.setAttribute(key,String(value));
  if (text !== undefined) node.textContent = text;
  return node;
}
export function renderCatalogMap(container, services, relations, onSelect) {
  const prefix = container.id;
  const ids = new Set(services.map(s=>s.id));
  const edges = relations.filter(e=>e.check.checked && ids.has(e.source.value) && ids.has(e.target.value));
  const depth = new Map(services.map(s=>[s.id,0]));
  const incoming = new Map(services.map(s=>[s.id,0]));
  for(const edge of edges) incoming.set(edge.target.value,incoming.get(edge.target.value)+1);
  const queue=services.filter(s=>!incoming.get(s.id)).map(s=>s.id), visited=new Set();
  while(queue.length) {
    const id=queue.shift(); visited.add(id);
    for(const edge of edges.filter(e=>e.source.value===id)) {
      const target=edge.target.value;
      depth.set(target,Math.max(depth.get(target),depth.get(id)+1));
      incoming.set(target,incoming.get(target)-1);
      if(!incoming.get(target)) queue.push(target);
    }
  }
  // Cycles remain representable; do not pretend the diagram proves a DAG.
  let cyclic=0;
  for(const service of services) if(!visited.has(service.id)) depth.set(service.id,cyclic++%4);
  const positions=new Map(), columns=new Map();
  for(const service of services) {
    const level=depth.get(service.id);
    if(!columns.has(level)) columns.set(level,[]);
    columns.get(level).push(service);
  }
  const rowGap=100, columnGap=260;
  const maxRows=Math.max(1,...[...columns.values()].map(c=>c.length));
  const height=Math.max(300,maxRows*rowGap+150);
  const width=Math.max(600,(Math.max(0,...depth.values())+1)*columnGap+40);
  // Center sparse levels; order peers by the position of their upstream callers.
  for(const [level,list] of [...columns.entries()].sort((a,b)=>a[0]-b[0])) {
    const score=s=>{const parents=edges.filter(e=>e.target.value===s.id).map(e=>positions.get(e.source.value)?.y).filter(y=>y!==undefined);return parents.length?parents.reduce((a,b)=>a+b,0)/parents.length:0;};
    list.sort((a,b)=>score(a)-score(b)||a.name.value.localeCompare(b.name.value));
    list.forEach((service,row)=>positions.set(service.id,{x:30+level*columnGap,y:100+(maxRows-list.length)*rowGap/2+row*rowGap}));
  }
  const svg=svgNode('svg',{viewBox:`0 0 ${width} ${height}`,width,height,role:'group','aria-label':'Servicios candidatos y relaciones documentadas'});
  const defs=svgNode('defs');
  for(const [name,color] of [['active','#176d5b'],['pending','#9ca9a4']]) {
    const marker=svgNode('marker',{id:`${prefix}-arrow-${name}`,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto-start-reverse'});
    marker.append(svgNode('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:color})); defs.append(marker);
  }
  svg.append(defs);
  for(const [level] of columns) svg.append(svgNode('text',{x:30+level*columnGap+82,y:35,'text-anchor':'middle','font-size':11,fill:'#71847c'},level===0?'Punto de entrada':`Dependencia · nivel ${level}`));
  const byId=new Map(services.map(s=>[s.id,s]));
  let bypass=0;
  for(const edge of edges) {
    const from=positions.get(edge.source.value), to=positions.get(edge.target.value);
    const active=byId.get(edge.source.value).check.checked && byId.get(edge.target.value).check.checked;
    const color=active?'#176d5b':'#9ca9a4';
    const x1=from.x+165,y1=from.y+28,x2=to.x,y2=to.y+28;
    const skip=to.x-from.x>columnGap+1 || to.x<=from.x;
    const lane=55+(bypass++%6)*7;
    const d=skip ? `M ${x1} ${y1} L ${x1+20} ${y1} L ${x1+20} ${lane} L ${x2-20} ${lane} L ${x2-20} ${y2} L ${x2} ${y2}`
      : `M ${x1} ${y1} C ${x1+48} ${y1}, ${x2-48} ${y2}, ${x2} ${y2}`;
    const path=svgNode('path',{d,fill:'none',class:'catalog-map-edge','data-source':edge.source.value,'data-target':edge.target.value,stroke:color,'stroke-width':1.7,'marker-end':`url(#${prefix}-arrow-${active?'active':'pending'})`});
    path.append(svgNode('title',{},`${byId.get(edge.source.value).name.value} → ${byId.get(edge.target.value).name.value}: ${edge.label.value}`));
    svg.append(path);

  }
  for(const service of services) {
    const pos=positions.get(service.id), active=service.check.checked;
    const group=svgNode('g',{tabindex:0,role:'button','aria-label':`Ver fuente de ${service.name.value}`,class:'catalog-map-node','data-service':service.name.value});
    group.append(svgNode('rect',{x:pos.x,y:pos.y,width:165,height:56,rx:10,fill:active?'#e3f0ea':'#f4f6f3',stroke:active?'#176d5b':'#b8c3bd'}));
    const name=service.name.value || service.original;
    group.append(svgNode('text',{x:pos.x+82.5,y:pos.y+32,'text-anchor':'middle','font-size':12,fill:'#192b29'},name.length>23?name.slice(0,21)+'…':name));
    group.append(svgNode('title',{},`${name} — ${active?'incluido en la revisión':'pendiente de selección'}`));
    const highlight=()=>{svg.querySelectorAll('.catalog-map-edge').forEach(path=>{const connected=path.dataset.source===service.id||path.dataset.target===service.id;path.style.opacity=connected?'1':'.12';path.style.strokeWidth=connected?'3':'1.7';});};
    const reset=()=>{svg.querySelectorAll('.catalog-map-edge').forEach(path=>{path.style.opacity='';path.style.strokeWidth='';});};
    group.addEventListener('mouseenter',highlight);group.addEventListener('mouseleave',reset);group.addEventListener('focus',highlight);group.addEventListener('blur',reset);
    const reveal=()=>{if(onSelect){onSelect(service);return;}service.box.querySelector('details').open=true;service.box.scrollIntoView({block:'center',behavior:'smooth'});service.check.focus({preventScroll:true});};
    group.addEventListener('click',reveal);group.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();reveal();}});
    svg.append(group);
  }
  container.replaceChildren(svg);
}
