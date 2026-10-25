/** DOM presentation only. All server content is rendered as text. */
export const $ = (id) => document.getElementById(id);

import { renderFlow } from './flow.js';
export { renderFlow } from './flow.js';

const statusLabels = {
  completed: 'Completado', needs_review: 'Revisión humana', skipped: 'Omitido',
};

export function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function renderDecisions(steps) {
  $('decision-steps').replaceChildren(...steps.map((step) => {
    const item = node('li', undefined, `decision-step ${step.status}`);
    const heading = node('div', undefined, 'decision-heading');
    heading.append(
      node('span', String(step.sequence).padStart(2, '0'), 'decision-number'),
      node('h3', step.title),
      node('span', statusLabels[step.status], 'decision-status'),
    );
    item.append(heading, node('strong', step.outcome), node('p', step.reason));
    if (step.evidence_ids.length) {
      const refs = node('div', undefined, 'evidence-refs');
      refs.append(node('span', 'Señales consultadas: '));
      for (const id of step.evidence_ids) {
        const link = node('a', id);
        link.href = `#signal-${id}`;
        refs.append(link);
      }
      const wrap=node('div',undefined,'evidence-refs-wrap');
      wrap.append(refs);
      if(step.evidence_ids.length>20) {
        refs.classList.add('refs-collapsed');
        const toggle=node('button',`Ver más (${step.evidence_ids.length} referencias)`,'text-button refs-toggle');toggle.type='button';toggle.setAttribute('aria-expanded','false');
        toggle.addEventListener('click',()=>{const collapsed=refs.classList.toggle('refs-collapsed');toggle.textContent=collapsed?`Ver más (${step.evidence_ids.length} referencias)`:'Ver menos';toggle.setAttribute('aria-expanded',String(!collapsed));});
        wrap.append(toggle);
      }
      item.append(wrap);
    }
    return item;
  }));
}

export function showResult(result) {
  $('empty-state').hidden = true;
  $('result').hidden = false;
  renderFlow(result.workflow.audit);
  $('flow-status').textContent = 'Recorrido registrado';
  $('flow-caption').textContent = 'Registro del análisis · la reproducción visual no altera su duración real';
  $('flow-detail').textContent = '';
  $('flow-replay').hidden = false;
  $('hypothesis').textContent = result.hypothesis;
  $('component').textContent = result.status === 'hypothesis' ? result.component : 'Sin determinar';
  $('confidence').textContent = Math.round(result.confidence * 100) + ' %';
  $('signal-count').textContent = result.evidence.length;
  $('recommendation').textContent = result.recommendation;
  $('judge-note').textContent = result.workflow.verdict?.notes || '';
  $('result-mode').textContent = result.evidence_mode === 'mock'
    ? 'Simulación · señales sintéticas' : 'Cloud Logging · logs reales';
  $('result-id').textContent = result.incident_id + (result.scope === 'general' ? ' · Análisis general' : ' · Análisis enfocado');
  $('result-time').textContent = result.elapsed_ms.toFixed(0) + ' ms de análisis';
  $('evidence-count').textContent = result.evidence.length + ' señales';
  $('no-evidence').hidden = result.evidence.length > 0;
  evidenceRecords = result.evidence; evidencePage = 0; renderEvidencePage();
  renderDecisions(result.decision_steps);
  $('decision').textContent = result.workflow.decision?.reason || '';
  $('execution').textContent = 'Acciones ejecutadas: 0 · Revisión humana requerida';
  $('audit').textContent = JSON.stringify(result.workflow, null, 2);
}

export function renderHistory(runs, onSelect) {
  $('history-empty').hidden = runs.length > 0;
  $('history').replaceChildren(...runs.map((result) => {
    const button = node('button', undefined, 'history-item');
    button.type = 'button';
    const component = result.status === 'hypothesis' ? result.component : 'Sin causa respaldada';
    const source = result.evidence_mode === 'mock' ? 'Simulación' : 'GKE';
    button.append(node('strong', result.incident_id), node('span', `${component} · ${source}`));
    button.addEventListener('click', () => onSelect(result));
    return button;
  }));
}

let evidenceRecords = [], evidencePage = 0, evidenceSize = 10;
function renderEvidencePage() {
  $('evidence').replaceChildren(...evidenceRecords.slice(evidencePage*evidenceSize,(evidencePage+1)*evidenceSize).map((signal) => {
    const row = node('tr');
    row.id = `signal-${signal.id}`;
    const source = node('td');
    source.append(node('span', signal.source, 'source-tag'));
    const message = node('td', signal.message);
    message.append(node('div', new Date(signal.timestamp).toLocaleString() + ' · ' + signal.severity, 'hint'));
    row.append(node('td', signal.id), source, node('td', signal.service), message);
    return row;
  }));
  const pages = Math.max(1,Math.ceil(evidenceRecords.length/evidenceSize));
  $('evidence-page').textContent = evidenceRecords.length ? `${evidencePage*evidenceSize+1}–${Math.min((evidencePage+1)*evidenceSize,evidenceRecords.length)} de ${evidenceRecords.length} · Página ${evidencePage+1} de ${pages}` : 'Sin señales';
  $('evidence-prev').disabled = evidencePage===0;
  $('evidence-next').disabled = evidencePage>=pages-1;
  $('evidence-pagination').hidden = !evidenceRecords.length;
}
$('evidence-prev').addEventListener('click',()=>{if(evidencePage>0){evidencePage--;renderEvidencePage();}});
$('evidence-next').addEventListener('click',()=>{if((evidencePage+1)*evidenceSize<evidenceRecords.length){evidencePage++;renderEvidencePage();}});
document.addEventListener('click',event=>{
  const link=event.target.closest('.evidence-refs a'); if(!link)return;
  const id=link.hash.slice('#signal-'.length), index=evidenceRecords.findIndex(s=>s.id===id);
  if(index<0)return;
  event.preventDefault();evidencePage=Math.floor(index/evidenceSize);renderEvidencePage();
  const row=document.getElementById('signal-'+id);row.tabIndex=-1;row.focus({preventScroll:true});row.scrollIntoView({block:'center',behavior:'smooth'});
});

$('evidence-size').addEventListener('change',()=>{evidenceSize=Number($('evidence-size').value);evidencePage=0;renderEvidencePage();});
