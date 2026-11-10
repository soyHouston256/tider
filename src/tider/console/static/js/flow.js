/** Replay recorded stages. Animation time is never reported as execution time. */
// Rules mode records only the steps that run: investigator → judge → decisor → reporter.
// The archived graph's intake/context/ejecutor/verificador stages are no longer drawn by default.
const stages = [['investigator','Investigador'],['judge','Juez'],['decisor','Decisor'],['reporter','Reporte']];
// Pipeline v2 (TIDER_PIPELINE=v2): barrido → Cartógrafo → verificador de firmas → Investigador → Proponente
// → Juez → Reporte. `signatures` no reutiliza `verificador`, que es la etapa del grafo archivado.
export const stagesV2 = [['sweep','Barrido'],['cartographer','Cartógrafo'],['signatures','Verificador de firmas'],
  ['investigator','Investigador'],['proposer','Proponente'],['judge','Juez'],['reporter','Reporte']];
const labels = {
  intake:'Recepción', context:'Contexto', investigator:'Investigador', judge:'Juez',
  decisor:'Decisor', ejecutor:'Propuesta', verificador:'Verificación', reporter:'Reporte',
  ...Object.fromEntries(stagesV2),
};
const paths = {
  intake: 'M12 3v12m-4-4 4 4 4-4M4 15v5h16v-5',
  context: 'M3 6l9-4 9 4-9 4-9-4m0 6 9 4 9-4m-18 6 9 4 9-4',
  investigator: 'M15 15l6 6M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0',
  judge: 'M8 3l7 7-4 4-7-7 4-4m5 9 7 7M3 20h11M5 17h7v3H5z',
  decisor: 'M12 3v6m0 0L5 15m7-6 7 6M5 12v6H2m17-6v6h3',
  ejecutor: 'M6 3h9l4 4v14H6zM14 3v5h5M9 12h7m-7 4h5',
  verificador: 'M12 2l8 4v6c0 5-8 10-8 10S4 17 4 12V6l8-4m-4 10 3 3 5-6',
  reporter: 'M5 2h10l4 4v16H5zM14 2v5h5M8 11h8m-8 4h8m-8 4h5',
  sweep: 'M4 6h16M4 12h16M4 18h10',
  cartographer: 'M5 5h4v4H5zM15 5h4v4h-4zM10 15h4v4h-4zM9 7h6M7 9l5 6m5-6-5 6',
  signatures: 'M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9',
  proposer: 'M6 3h9l4 4v14H6zM14 3v5h5M9 12h7m-7 4h5',
};
const $=id=>document.getElementById(id);
function icon(id) {
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  for(const [k,v] of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'1.6','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'})) svg.setAttribute(k,v);
  const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',paths[id]||paths.reporter);svg.append(path);return svg;
}
/** Stages present in the recorded run, in first-seen order; the 4 rules stages when nothing was recorded. */
function presentStages(ids=[]) {
  const unique=[...new Set(ids.filter(Boolean))];
  return unique.length ? unique.map(id=>[id,labels[id]||id]) : stages;
}
export function renderFlow(audit=[], adaptive=false, order=null) {
  const adaptiveLabel=id=>({investigator:'Consulta',judge:'Evaluación',reporter:'Conclusión',intake:'Objetivo'})[id]||labels[id]||id;
  const displayed=adaptive ? audit.map((e,i)=>[e.agent,`${i+1}. ${adaptiveLabel(e.agent)}`]) : presentStages(order || audit.map(e=>e.agent));
  $('flow').style.setProperty('--flow-columns', String(Math.min(Math.max(displayed.length,1),8)));
  $('flow').replaceChildren(...displayed.map(([id,label])=>{
    const events=audit.filter(e=>e.agent===id), event=events.at(-1);
    const item=document.createElement('li');item.dataset.stage=id;
    item.className=event ? event.skipped ? 'skipped' : 'complete' : '';
    const badge=document.createElement('span');badge.className='step-number';badge.append(icon(id));
    const text=document.createElement('span');text.textContent=label;
    const state=document.createElement('small');state.className='flow-stage-state';
    state.textContent=event ? event.skipped ? 'Omitida' : 'Completada' : '';
    item.append(badge,text,state);return item;
  }));
}
function wait(ms,signal) {
  return new Promise(resolve=>{
    if(signal.aborted){resolve();return;}
    const finish=()=>{clearTimeout(timer);signal.removeEventListener('abort',finish);resolve();};
    const timer=setTimeout(finish,ms);signal.addEventListener('abort',finish,{once:true});
  });
}
async function transfer(from,to,signal,reduced) {
  if(!from || reduced || signal.aborted) return;
  const host=$('flow').parentElement;
  const box=host.getBoundingClientRect();
  const a=from.querySelector('.step-number').getBoundingClientRect(),b=to.querySelector('.step-number').getBoundingClientRect();
  const dot=document.createElement('span');dot.className='flow-transfer';dot.setAttribute('aria-hidden','true');host.append(dot);
  const motion=dot.animate([
    {transform:`translate(${a.x-box.x+a.width/2}px,${a.y-box.y+a.height/2}px)`,opacity:0.3},
    {transform:`translate(${b.x-box.x+b.width/2}px,${b.y-box.y+b.height/2}px)`,opacity:1},
  ],{duration:260,easing:'ease-in-out',fill:'forwards'});
  await wait(260,signal);motion.cancel();dot.remove();
}
export async function replayFlow(result,signal) {
  renderFlow([], false, result.decision_steps.map(step=>step.stage));
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  $('flow').classList.toggle('reduced-motion',reduced);
  $('flow').setAttribute('aria-busy','true');
  $('flow-caption').textContent='Reproducción del registro real · 1,1 s por etapa · no representa tiempos de ejecución';
  $('flow-skip').hidden=false;$('flow-replay').hidden=true;
  let previous;
  try {
    for(const step of result.decision_steps) {
      if(signal.aborted) break;
      const item=[...$('flow').children].find(e=>e.dataset.stage===step.stage);
      if(!item) continue;
      await transfer(previous,item,signal,reduced);
      if(signal.aborted) break;
      item.classList.remove('complete','skipped','review');item.classList.add('active');
      item.setAttribute('aria-current','step');
      item.querySelector('.flow-stage-state').textContent=step.status==='skipped'?'Omitida':'En reproducción';
      $('flow-status').textContent=`${step.sequence}/${result.decision_steps.length} · ${step.title}`;
      $('flow-detail').textContent=step.outcome;
      if(step.status==='skipped') item.classList.add('skipped');
      await wait(1100,signal);
      item.classList.remove('active');item.removeAttribute('aria-current');
      item.classList.add(step.status==='skipped'?'skipped':step.status==='needs_review'?'review':'complete');
      item.querySelector('.flow-stage-state').textContent=step.status==='skipped'?'Omitida':step.status==='needs_review'?'Revisión':'Completada';
      previous=item;
    }
  } finally {
    $('flow').setAttribute('aria-busy','false');$('flow-skip').hidden=true;
    $('flow').querySelectorAll('.active').forEach(item=>{item.classList.remove('active');item.removeAttribute('aria-current');});
  }
}
