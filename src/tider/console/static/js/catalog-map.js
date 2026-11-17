/** A read-only map of the editable review, not a live infrastructure view. */
const NS = 'http://www.w3.org/2000/svg';
function svgNode(tag, attrs = {}, text) {
  const node = document.createElementNS(NS, tag);
  // Los colores son tokens CSS (var(--x)); los atributos de presentación SVG no aceptan var(), el estilo sí.
  for (const [key,value] of Object.entries(attrs)) {
    if (['fill','stroke'].includes(key) && String(value).startsWith('var(')) node.style.setProperty(key,String(value));
    else node.setAttribute(key,String(value));
  }
  if (text !== undefined) node.textContent = text;
  return node;
}
// Pipeline v2: el nodo se pinta por su estado y lleva un borde según su rol en la hipótesis principal; la
// arista se pinta por su estado y se dibuja punteada si solo es observada. El enlace causa se resalta.
const T = name => `var(--${name})`;
const NODE_STATE = {falla:[T('critical-soft'),T('critical')], sano:[T('ok-soft'),T('ok')], sin_datos:[T('surface'),T('border-strong')]};
const ROLE_BORDER = {causa:{width:3.5,dash:''}, victima:{width:2.5,dash:'5 3'}};
const EDGE_STATE = {falla:T('critical'), sano:T('ok'), sin_datos:T('border-strong')};
// Polilínea ortogonal con esquinas redondeadas.
function rounded(points, radius) {
  const pts=points.filter((p,i)=>!i||p[0]!==points[i-1][0]||p[1]!==points[i-1][1]);
  let d=`M ${pts[0][0]} ${pts[0][1]}`;
  for(let i=1;i<pts.length-1;i++) {
    const [px,py]=pts[i-1],[cx,cy]=pts[i],[nx,ny]=pts[i+1];
    const d1=Math.hypot(cx-px,cy-py), d2=Math.hypot(nx-cx,ny-cy), r=Math.min(radius,d1/2,d2/2);
    if(!r){d+=` L ${cx} ${cy}`;continue;}
    d+=` L ${cx-(cx-px)/d1*r} ${cy-(cy-py)/d1*r} Q ${cx} ${cy} ${cx+(nx-cx)/d2*r} ${cy+(ny-cy)/d2*r}`;
  }
  const last=pts[pts.length-1];
  return d+` L ${last[0]} ${last[1]}`;
}
export function renderCatalogMap(container, services, relations, onSelect, options = {}) {
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
  // Sin relaciones no hay capas: repartir en una cuadrícula en vez de apilar todo en una columna.
  if(!edges.length) services.forEach((service,index)=>depth.set(service.id,index%4));
  const positions=new Map(), columns=new Map();
  for(const service of services) {
    const level=depth.get(service.id);
    if(!columns.has(level)) columns.set(level,[]);
    columns.get(level).push(service);
  }
  // Rejilla común: todas las columnas comparten filas, así los pasillos entre filas y columnas quedan libres
  // y las aristas que saltan niveles no atraviesan nodos.
  const W=190, H=40, rowGap=62, columnGap=236, top=72, left=20;
  const maxRows=Math.max(1,...[...columns.values()].map(c=>c.length));
  const maxLevel=Math.max(0,...depth.values());
  const height=top+maxRows*rowGap+16;
  const width=left*2+maxLevel*columnGap+W;
  // Order peers by the position of their upstream callers; sparse levels sit near the middle.
  for(const [level,list] of [...columns.entries()].sort((a,b)=>a[0]-b[0])) {
    const score=s=>{const parents=edges.filter(e=>e.target.value===s.id).map(e=>positions.get(e.source.value)?.y).filter(y=>y!==undefined);return parents.length?parents.reduce((a,b)=>a+b,0)/parents.length:0;};
    list.sort((a,b)=>score(a)-score(b)||a.name.value.localeCompare(b.name.value));
    const offset=Math.floor((maxRows-list.length)/2);
    list.forEach((service,row)=>positions.set(service.id,{x:left+level*columnGap,y:top+(offset+row)*rowGap}));
  }
  const svg=svgNode('svg',{viewBox:`0 0 ${width} ${height}`,width,height,role:'group','aria-label':'Servicios candidatos y relaciones documentadas'});
  const defs=svgNode('defs');
  for(const [name,color] of [['active',T('border-strong')],['pending',T('border')],['falla',T('critical')]]) {
    const marker=svgNode('marker',{id:`${prefix}-arrow-${name}`,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});
    marker.append(svgNode('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:color})); defs.append(marker);
  }
  svg.append(defs);
  for(const [level] of columns) svg.append(svgNode('text',{x:left+level*columnGap+4,y:28,class:'to-map__col'},level===0?'Entrada':`Nivel ${level}`));
  const byId=new Map(services.map(s=>[s.id,s]));
  const gutter=(columnGap-W)/2, corridor=(rowGap-H)/2;
  for(const edge of edges) {
    const from=positions.get(edge.source.value), to=positions.get(edge.target.value);
    const active=byId.get(edge.source.value).check.checked && byId.get(edge.target.value).check.checked;
    const state=edge.estado && EDGE_STATE[edge.estado];
    const color=state || (active?T('border-strong'):T('border'));
    const marker=edge.estado==='falla'?'falla':edge.estado==='sin_datos'||!active?'pending':'active';
    const cause=options.causeEdge && options.causeEdge.origen===edge.source.value && options.causeEdge.destino===edge.target.value;
    const x1=from.x+W, y1=from.y+H/2, x2=to.x, y2=to.y+H/2;
    let points;
    if(to.x===from.x) points=[[from.x+W/2,from.y+(to.y>from.y?H:0)],[to.x+W/2,to.y+(to.y>from.y?0:H)]];
    else if(to.x-from.x<=columnGap+1 && to.x>from.x) points=[[x1,y1],[x1+gutter,y1],[x1+gutter,y2],[x2,y2]];
    else {
      // Salto de nivel o retorno: sale al pasillo de su columna, recorre el pasillo entre filas y entra por el pasillo del destino.
      const lane=to.y-corridor;
      points=[[x1,y1],[x1+gutter,y1],[x1+gutter,lane],[x2-gutter,lane],[x2-gutter,y2],[x2,y2]];
    }
    const path=svgNode('path',{d:rounded(points,8),fill:'none',class:'catalog-map-edge'+(cause?' diagnosis-cause-edge':''),'data-source':edge.source.value,'data-target':edge.target.value,stroke:color,'stroke-width':cause?3.5:1.5,'marker-end':`url(#${prefix}-arrow-${marker})`,...(edge.origen_dato==='observada'?{'stroke-dasharray':'6 4'}:{})});
    path.append(svgNode('title',{},`${byId.get(edge.source.value).name.value} → ${byId.get(edge.target.value).name.value}: ${edge.label.value}`));
    svg.append(path);
  }
  for(const service of services) {
    const pos=positions.get(service.id), active=service.check.checked;
    const group=svgNode('g',{tabindex:0,role:'button','aria-label':`Ver fuente de ${service.name.value}`,class:'catalog-map-node','data-service':service.name.value});
    const [fill,stroke]=NODE_STATE[service.estado] || (active?[T('surface'),T('border-strong')]:[T('surface-sunken'),T('border')]);
    const dot=service.estado ? NODE_STATE[service.estado]?.[1] : active ? T('brand') : T('border-strong');
    const role=ROLE_BORDER[service.rol];
    group.append(svgNode('rect',{x:pos.x,y:pos.y,width:W,height:H,rx:8,fill,stroke:role?T('ink'):stroke,
      ...(role?{'stroke-width':role.width,...(role.dash?{'stroke-dasharray':role.dash}:{})}:{}),...(service.tipo==='auxiliar'?{opacity:.75}:{})}));
    group.append(svgNode('circle',{cx:pos.x+16,cy:pos.y+H/2,r:4,fill:active||service.estado?dot:'none',stroke:dot,'stroke-width':1.5,class:'catalog-map-dot'}));
    if(service.estado) group.dataset.estado=service.estado;
    if(service.rol) group.dataset.rol=service.rol;
    const name=service.name.value || service.original;
    group.append(svgNode('text',{x:pos.x+30,y:pos.y+H/2+5,class:'to-map__label catalog-map-label'},name.length>21?name.slice(0,19)+'…':name));
    group.append(svgNode('title',{},service.estado ? `${name} — estado: ${service.estado.replace('_',' ')} · rol: ${service.rol||'ninguno'}${service.tipo==='auxiliar'?' · auxiliar':''}` : `${name} — ${active?'incluido en la revisión':'pendiente de selección'}`));
    const highlight=()=>{svg.querySelectorAll('.catalog-map-edge').forEach(path=>{const connected=path.dataset.source===service.id||path.dataset.target===service.id;path.style.opacity=connected?'1':'.12';path.style.strokeWidth=connected?'2.5':'';if(connected)path.style.stroke=T('brand');});};
    const reset=()=>{svg.querySelectorAll('.catalog-map-edge').forEach(path=>{path.style.opacity='';path.style.strokeWidth='';path.style.stroke=path.dataset.stroke;});};
    group.addEventListener('mouseenter',highlight);group.addEventListener('mouseleave',reset);group.addEventListener('focus',highlight);group.addEventListener('blur',reset);
    const reveal=()=>{if(onSelect){onSelect(service);return;}if(!service.box)return;service.box.querySelector('details').open=true;service.box.scrollIntoView({block:'center',behavior:'smooth'});service.check.focus({preventScroll:true});};
    group.addEventListener('click',reveal);group.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();reveal();}});
    svg.append(group);
  }
  svg.querySelectorAll('.catalog-map-edge').forEach(path=>{path.dataset.stroke=path.style.stroke;});
  container.replaceChildren(svg);
}
