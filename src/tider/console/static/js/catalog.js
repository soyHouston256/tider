import { renderCatalogMap } from './catalog-map.js';
/** Human review of source-backed candidates. No automatic confirmation. */
const el = (id) => document.getElementById(id);
let current;
let pending = false;
let serviceRows = [];
let edgeRows = [];
const node = (tag, text) => { const n = document.createElement(tag); if (text) n.textContent = text; return n; };
async function api(path, body) {
  const response = await fetch(path, body ? {method: 'POST', headers: {'Content-Type':'application/json'}, body:JSON.stringify(body)} : {});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Revisa los nombres y las relaciones. Usa identificadores en minúsculas, números y guiones.');
  return data;
}
async function refresh() {
  const data = await api('/v1/context/catalog');
  const count = data.proposal.services.length;
  el('catalog-status').textContent = data.status === 'confirmed'
    ? `${data.confirmed.services.length} servicios confirmados · ${data.confirmed.relations.length} relaciones`
    : count ? `${count} candidatos encontrados · pendientes de revisión`
    : 'Sin candidatos reconocidos. Usa identificadores técnicos en los nodos o relaciones Mermaid.';
  el('catalog-open').disabled = !count;
  el('architecture-review').disabled = !count;
  el('nav-catalog').disabled = !count;
  const confirmed = data.status === 'confirmed';
  const catalog = confirmed ? data.confirmed : data.proposal;
  el('architecture-status').textContent = count ? (confirmed ? 'Catálogo confirmado' : 'Propuesta · pendiente de revisión') : 'Sin contexto';
  if (catalog.services.length) {
    renderCatalogMap(el('architecture-map'), catalog.services.map(s => ({...s, original:s.name, name:{value:s.name}, check:{checked:confirmed}})),
      catalog.relations.map(r => ({...r, source:{value:r.source},target:{value:r.target},label:{value:r.label},check:{checked:true}})),
      () => el('catalog-open').click());
  } else {
    el('architecture-map').replaceChildren(node('p','Carga documentos para proponer un mapa de servicios y relaciones.'));
  }
  markDiagnosis();
  return data;
}
function sources(items) {
  const details = node('details'); details.className = 'catalog-sources';
  details.append(node('summary', `Ver origen (${items.length})`));
  for (const source of items) {
    const block = node('div'); block.append(node('strong', `${source.file} · ${source.location}`), node('p', source.excerpt));
    details.append(block);
  }
  return details;
}
function selectionChanged() {
  const included = new Set(serviceRows.filter(r => r.check.checked).map(r => r.id));
  for (const row of serviceRows) row.name.disabled = !row.check.checked;
  for (const row of edgeRows) {
    for (const select of [row.source, row.target]) {
      for (const option of select.options) {
        const service = serviceRows.find(r => r.id === option.value);
        option.textContent = service.name.value || service.original;
      }
    }
    const active = included.has(row.source.value) && included.has(row.target.value);
    row.box.classList.toggle('catalog-excluded', !active);
    row.label.disabled = !active || !row.check.checked;
  }
  renderCatalogMap(el('catalog-map'), serviceRows, edgeRows);
  el('catalog-selection').textContent = `${included.size} servicios seleccionados`;
  el('catalog-confirm').disabled = pending || !included.size;
}
function render(data) {
  current = data; serviceRows = []; edgeRows = [];
  el('catalog-services').replaceChildren(); el('catalog-relations').replaceChildren();
  el('catalog-error').hidden = true;
  const confirmedServices = new Map((data.confirmed?.services || []).map(s => [s.id, s]));
  const confirmedEdges = new Map((data.confirmed?.relations || []).map(r => [r.id, r]));
  for (const service of data.proposal.services) {
    const box = node('div'); box.className = 'catalog-service';
    const label = node('label'); const check = node('input'); check.type = 'checkbox';
    check.checked = confirmedServices.has(service.id);
    check.setAttribute('aria-label', `Incluir ${service.name}`);
    label.append(check, node('span', service.name));
    const name = node('input'); name.type = 'text'; name.maxLength = 63;
    name.pattern = '[a-z0-9](([a-z0-9]|-){0,61}[a-z0-9])?'; name.required = true;
    name.value = confirmedServices.get(service.id)?.name || service.name;
    name.setAttribute('aria-label', `Nombre de ${service.name}`);
    const aliases = node('input'); aliases.type='text'; aliases.maxLength=600;
    const suggestion = service.name.replace(/-?service$/, '');
    aliases.value = ((confirmedServices.get(service.id)?.aliases?.length ? confirmedServices.get(service.id).aliases : null) || (suggestion !== service.name && suggestion.length>2 ? [suggestion] : [])).join(', ');
    aliases.setAttribute('aria-label',`Alias u operaciones de ${service.name}`);
    aliases.placeholder='Alias u operaciones, separados por comas';
    const names=node('div');names.append(name,node('p','Alias / operaciones (revisar antes de confirmar)'),aliases,node('small','Admite varios alias separados por comas. Ejemplo: nombre corto, operación singular, operación plural. Máximo 20.'));
    box.append(label, names, sources(service.sources));
    serviceRows.push({id:service.id,check,name,original:service.name,aliases,box});
    check.addEventListener('change',selectionChanged); name.addEventListener('input',selectionChanged);
    el('catalog-services').append(box);
  }
  for (const edge of data.proposal.relations) {
    const value = confirmedEdges.get(edge.id) || edge;
    const box = node('div'); box.className = 'catalog-edge';
    const check = node('input'); check.type = 'checkbox'; check.checked = data.confirmed ? confirmedEdges.has(edge.id) : true;
    check.setAttribute('aria-label', `Incluir relación ${edge.id}`);
    const source = node('select'), target = node('select'), label = node('input');
    for (const s of data.proposal.services) { source.add(new Option(s.name,s.id)); target.add(new Option(s.name,s.id)); }
    source.value = value.source; target.value = value.target; label.value = value.label;
    label.maxLength = 120; label.required = true;
    source.setAttribute('aria-label','Origen de relación'); target.setAttribute('aria-label','Destino de relación');
    label.setAttribute('aria-label','Descripción de relación');
    const fields = node('div'); fields.className = 'catalog-edge-fields';
    fields.append(check,source,node('span','→'),target,label);
    box.append(fields,sources(edge.sources));
    edgeRows.push({id:edge.id,check,source,target,label,box});
    label.addEventListener('input',selectionChanged);
    check.addEventListener('change',selectionChanged);
    source.addEventListener('change',selectionChanged); target.addEventListener('change',selectionChanged);
    el('catalog-relations').append(box);
  }
  if (!edgeRows.length) el('catalog-relations').append(node('p','No se reconocieron relaciones estructuradas.'));
  selectionChanged();
}
el('catalog-open').addEventListener('click', async () => {
  try { render(await refresh()); location.hash = '#catalog'; }
  catch (error) { el('catalog-status').textContent = error.message; }
});
el('catalog-close').addEventListener('click',()=>{ if (!pending) location.hash = '#investigation'; });
el('catalog-select-all').addEventListener('click',()=>{ serviceRows.forEach(r=>{r.check.checked=true;}); edgeRows.forEach(r=>{r.check.checked=true;});selectionChanged(); });
el('catalog-review-form').addEventListener('submit',async(event)=>{
  event.preventDefault(); if(pending) return;
  const services = serviceRows.filter(r=>r.check.checked).map(r=>({id:r.id,name:r.name.value.trim(),aliases:r.aliases.value.split(',').map(a=>a.trim()).filter(Boolean)}));
  const ids = new Set(services.map(s=>s.id));
  const relations = edgeRows.filter(r=>r.check.checked && ids.has(r.source.value) && ids.has(r.target.value))
    .map(r=>({id:r.id,source:r.source.value,target:r.target.value,label:r.label.value.trim()}));
  pending=true;selectionChanged();el('catalog-error').hidden=true;
  try {
    await api('/v1/context/catalog/confirm',{revision:current.revision,services,relations});
    await refresh();location.hash = '#investigation';document.dispatchEvent(new Event('catalog-confirmed'));
  } catch(error) {el('catalog-error').textContent=error.message;el('catalog-error').hidden=false;}
  finally {pending=false;selectionChanged();}
});
document.addEventListener('context-documents-changed',()=>refresh().catch(error=>{el('catalog-status').textContent=error.message;}));
refresh().catch(error=>{el('catalog-status').textContent=error.message;});

el('nav-catalog').addEventListener('click',()=>el('catalog-open').click());
el('architecture-review').addEventListener('click',()=>el('catalog-open').click());
document.querySelectorAll('.side-nav a').forEach(link=>link.addEventListener('click',()=>{document.querySelectorAll('.side-nav a').forEach(a=>a.classList.remove('selected'));link.classList.add('selected');if(link.hash==='#context-lake')document.querySelector('.context-panel').open=true;}));

async function loadCatalogPage() { if(location.hash === '#catalog') { try { render(await refresh()); } catch(error) { el('catalog-error').hidden=false; el('catalog-error').textContent=error.message; } } }
window.addEventListener('hashchange',loadCatalogPage);
loadCatalogPage();

let selectedDiagnosis;
function markDiagnosis() {
  const nodes = [...el('architecture-map').querySelectorAll('[data-service]')];
  nodes.forEach(n=>n.classList.remove('diagnosis-component'));
  const note = el('architecture-diagnosis');
  note.hidden = !selectedDiagnosis;
  if (!selectedDiagnosis) return;
  const result = selectedDiagnosis;
  const component = result.status === 'hypothesis' ? result.component : null;
  const match = nodes.find(n => n.dataset.service === component);
  if (match) match.classList.add('diagnosis-component');
  const source = result.evidence_mode === 'mock' ? 'Simulación' : 'Logs reales';
  note.textContent = `${source} · ${result.incident_id} · ` + (match ? `Rojo: ${component}, componente señalado por la hipótesis.` : component ? `El componente ${component} no aparece en el catálogo actual.` : 'Sin componente respaldado para resaltar.') + ' Mapa documental actual; no indica salud en vivo.';
}
document.addEventListener('diagnosis-selected',event=>{selectedDiagnosis=event.detail;markDiagnosis();});
