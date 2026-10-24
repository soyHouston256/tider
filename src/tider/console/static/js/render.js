/** DOM presentation only. All server content is rendered as text. */
export const $ = (id) => document.getElementById(id);

const stages = [
  ['intake', 'Recepción'], ['context', 'Contexto'],
  ['investigator', 'Investigador'], ['judge', 'Juez'],
  ['decisor', 'Decisor'], ['ejecutor', 'Propuesta'],
  ['verificador', 'Verificación'], ['reporter', 'Reporte'],
];
const statusLabels = {
  completed: 'Completado', needs_review: 'Revisión humana', skipped: 'Omitido',
};

export function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

export function renderFlow(audit = []) {
  $('flow').replaceChildren(...stages.map(([id, label], index) => {
    const event = audit.find((entry) => entry.agent === id);
    const complete = Boolean(event) && !event.skipped;
    const item = node('li', undefined, complete ? 'complete' : '');
    const number = event?.skipped ? '—' : complete ? '✓' : String(index + 1).padStart(2, '0');
    item.append(node('span', number, 'step-number'), node('span', label));
    return item;
  }));
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
      item.append(refs);
    }
    return item;
  }));
}

export function showResult(result) {
  $('empty-state').hidden = true;
  $('result').hidden = false;
  renderFlow(result.workflow.audit);
  $('flow-status').textContent = 'Recorrido completado';
  $('hypothesis').textContent = result.hypothesis;
  $('component').textContent = result.status === 'hypothesis' ? result.component : 'Sin determinar';
  $('confidence').textContent = Math.round(result.confidence * 100) + ' %';
  $('signal-count').textContent = result.evidence.length;
  $('recommendation').textContent = result.recommendation;
  $('judge-note').textContent = result.workflow.verdict?.notes || '';
  $('result-mode').textContent = result.evidence_mode === 'mock'
    ? 'Simulación · señales sintéticas' : 'Cloud Logging · logs reales';
  $('result-id').textContent = result.incident_id;
  $('result-time').textContent = result.elapsed_ms.toFixed(0) + ' ms de análisis';
  $('evidence-count').textContent = result.evidence.length + ' señales';
  $('no-evidence').hidden = result.evidence.length > 0;
  $('evidence').replaceChildren(...result.evidence.map((signal) => {
    const row = node('tr');
    row.id = `signal-${signal.id}`;
    const source = node('td');
    source.append(node('span', signal.source, 'source-tag'));
    const message = node('td', signal.message);
    message.append(node('div', new Date(signal.timestamp).toLocaleString() + ' · ' + signal.severity, 'hint'));
    row.append(node('td', signal.id), source, node('td', signal.service), message);
    return row;
  }));
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
