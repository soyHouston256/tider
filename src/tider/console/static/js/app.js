import { replayFlow } from './flow.js';
import './catalog.js';
import './context.js';
/** Form interactions and session state. Rendering and HTTP have separate modules. */
import { fetchJSON, analyzeIncident, investigateIncident } from './api.js';
import { $, node, renderFlow, showResult, renderHistory } from './render.js';

let configuration;
let currentResult;
let runs = [];
let analyzing = false;
let playback;
let viewVersion = 0;

function selectResult(result) {
  viewVersion++;
  playback?.abort();
  currentResult = result;
  showResult(result);
  document.dispatchEvent(new CustomEvent('diagnosis-selected', {detail:result}));
}

function updateHistory() {
  renderHistory(runs, (result) => {
    location.hash = '#investigation';
    navigateWorkspace();
    selectResult(result);
    $('result').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

function setDates() {
  const end = new Date(), start = new Date(end.getTime() - 10 * 60 * 1000);
  const clock = date => String(date.getHours()).padStart(2,'0') + ':' + String(date.getMinutes()).padStart(2,'0');
  $('start').value = start.toDateString() === end.toDateString() ? clock(start) : '00:00';
  $('end').value = clock(end);
  updateTimeChoice();
}
function updateTimeChoice() {
  const custom = document.querySelector('input[name="time-mode"]:checked').value === 'custom';
  $('custom-hours').hidden = !custom;
  $('start').required = custom && $('mode').value === 'gcp';
  $('end').required = custom && $('mode').value === 'gcp';
  $('time-today').textContent = 'Hoy · ' + new Date().toLocaleDateString('es', {day:'numeric',month:'long',year:'numeric'});
}

function scenarioChanged() {
  renderScenarioPicker();
  const scenario = configuration.scenarios.find((item) => item.id === $('scenario').value);
  $('scenario-note').textContent = scenario.description;
  $('service').value = scenario.service;
  renderServicePicker();
}

function updateServices() {
  if (!configuration) return;
  const mock = $('mode').value !== 'gcp';
  const names = mock ? configuration.mock_services : configuration.services;
  const previous = $('service').value;
  $('service').replaceChildren(...names.map((service) => new Option(service, service)));
  if (names.includes(previous)) $('service').value = previous;
  renderServicePicker();
  updateScope();
  $('service-catalog-note').textContent = mock ? 'Servicios de los escenarios simulados.'
    : configuration.catalog_status === 'confirmed' ? 'Catálogo documental confirmado. No es un inventario en vivo.'
    : configuration.catalog_status === 'pending' ? 'Revisa y confirma el catálogo del Context Lake antes de consultar logs.'
    : 'Catálogo predeterminado de Online Boutique. Carga documentos para proponer el tuyo.';
}

async function refreshCatalogConfig() {
  if (!configuration) return;
  try { configuration = await fetchJSON('/v1/lab/config'); updateServices(); }
  catch (error) { $('error').textContent = error.message; $('error').hidden = false; }
}
document.addEventListener('context-documents-changed', refreshCatalogConfig);
document.addEventListener('catalog-confirmed', refreshCatalogConfig);

function modeChanged() {
  renderSourcePicker();
  const gcp = $('mode').value === 'gcp';
  $('evidence-source-card').dataset.source = gcp ? 'gcp' : 'mock';
  $('source-kind').textContent = gcp ? 'LOGS REALES · GOOGLE CLOUD' : 'DATOS SIMULADOS · LABORATORIO';
  $('scenario-fields').hidden = gcp;
  $('time-fields').hidden = !gcp;
  $('mode-note').textContent = gcp
    ? 'Consulta real de Cloud Logging, limitada al entorno configurado. Las métricas y trazas aún no están conectadas.'
    : 'Señales sintéticas. No necesita conexión a GCP.';
  if (gcp) setDates();
  updateTimeChoice();
  updateServices();
}

function buildRequest() {
  const gcp = $('mode').value === 'gcp';
  const now = new Date();
  const custom = gcp && document.querySelector('input[name="time-mode"]:checked').value === 'custom';
  const today = [now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');
  const end = custom ? new Date(today + 'T' + $('end').value) : now;
  const start = custom ? new Date(today + 'T' + $('start').value) : new Date(end.getTime() - 10 * 60 * 1000);
  updateTimeChoice();
  if (custom && end > now) throw new Error('La hora final no puede estar en el futuro.');
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start || end - start > 7200000) {
    throw new Error('Elige una ventana positiva de hasta dos horas.');
  }
  return {
    objective: $('objective').value.trim() || "Investiga el incidente y determina qué evidencia falta.",
    incident_id: $('incident').value.trim(), scope: selectedScope(), service: selectedScope() === 'general' ? null : $('service').value,
    mode: $('mode').value, scenario: $('scenario').value,
    start: start.toISOString(), end: end.toISOString(),
  };
}

async function submitAnalysis(event) {
  event.preventDefault();
  if (analyzing) return;
  analyzing = true;
  const version = ++viewVersion;
  playback?.abort();
  renderFlow();
  document.dispatchEvent(new CustomEvent('diagnosis-selected', {detail:null}));
  $('result').hidden = true;
  $('empty-state').hidden = true;
  $('flow-replay').hidden = true;
  $('flow-detail').textContent = '';
  $('flow-caption').textContent = 'Consultando evidencia. La reproducción comenzará al recibir el resultado.';
  $('error').hidden = true;
  $('run').disabled = true;
  $('run').textContent = 'Analizando…';
  $('flow-status').textContent = 'Procesando evidencia…';
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 330000);
  try {
    const agentic = configuration.reasoning_mode !== 'none';
    const observedSteps=[];
    const result = agentic
      ? await investigateIncident(buildRequest(), controller.signal, step => {
          if(version!==viewVersion)return;
          observedSteps.push({agent:step.stage,outcome:step.title});
          renderFlow(observedSteps,true);
          $('flow-status').textContent=step.title;
          $('flow-caption').textContent='Investigación adaptativa · eventos reales';
          $('flow-detail').textContent=step.outcome+' · '+step.reason;
        })
      : await analyzeIncident(buildRequest(), controller.signal);
    clearTimeout(timeout);
    runs = [result, ...runs].slice(0, configuration.history_limit);
    updateHistory();
    await suggestIncident();
    if (version === viewVersion) {
      playback = new AbortController();
      $('run').textContent = 'Mostrando recorrido…';
      if(result.reasoning_mode !== 'agentic') await replayFlow(result, playback.signal);
      if (version === viewVersion) selectResult(result);
    }
  } catch (error) {
    $('error').textContent = error.name === 'AbortError'
      ? 'La consulta tardó demasiado. El servidor puede seguir procesándola; revisa el historial antes de repetir.'
      : error.message;
    $('error').hidden = false;
    $('flow-status').textContent = 'No se completó esta consulta';
    $('flow-caption').textContent = 'No hay un recorrido nuevo disponible para reproducir.';
  } finally {
    clearTimeout(timeout);
    analyzing = false;
    updateServices();
    $('run').textContent = 'Analizar incidente →';
  }
}

function downloadResult() {
  if (!currentResult) return;
  const blob = new Blob([JSON.stringify(currentResult, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = node('a');
  link.href = url;
  link.download = `tiderops-${currentResult.run_id}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function init() {
  renderFlow();
  setDates();
  await suggestIncident();
  try {
    configuration = await fetchJSON('/v1/lab/config');
    for (const id of ['project', 'cluster', 'namespace']) $(id).textContent = configuration[id];
    $('objective').disabled = configuration.reasoning_mode === 'none';
    $('objective').placeholder = configuration.reasoning_mode === 'none' ? 'Activa un modelo para investigar un síntoma libre.' : 'La compra falla; investiga qué componente está implicado.';
    $('reasoning').textContent = configuration.reasoning_mode === 'none' ? 'Baseline por reglas' : configuration.model;
    const gcpOption = new Option('Logs de GKE', 'gcp');
    gcpOption.disabled = !configuration.gcp_enabled;
    $('mode').replaceChildren(new Option('Simulación local', 'mock'), gcpOption);
    updateServices();
    $('scenario').replaceChildren(...configuration.scenarios.map((item) => new Option(item.name, item.id)));
    scenarioChanged();
    modeChanged();
    $('connection').textContent = 'API conectada';
    $('run').disabled = false;
    runs = await fetchJSON('/v1/incidents');
    updateHistory();
  } catch (error) {
    $('connection').textContent = 'Sin conexión';
    $('connection').classList.add('offline');
    $('error').hidden = false;
    $('error').textContent = error.message;
  }
}

$('analysis-form').addEventListener('submit', submitAnalysis);
$('download').addEventListener('click', downloadResult);
$('mode').addEventListener('change', modeChanged);
$('scenario').addEventListener('change', scenarioChanged);
init();

$('flow-skip').addEventListener('click', () => playback?.abort());
$('flow-replay').addEventListener('click', async () => {
  if (!currentResult || analyzing) return;
  const result = currentResult;
  const version = ++viewVersion;
  analyzing = true;
  updateServices();
  playback = new AbortController();
  try {
    if(result.reasoning_mode !== 'agentic') await replayFlow(result, playback.signal);
    if (version === viewVersion) selectResult(result);
  } finally {
    analyzing = false;
    updateServices();
  }
});

// Separate views keep the document library out of the investigation workspace.
function navigateWorkspace() {
  const context = location.hash === '#context-lake';
  const catalog = location.hash === '#catalog';
  const history = location.hash === '#session-history';
  $('catalog-dialog').hidden = !catalog;
  $('nav-catalog').classList.toggle('selected', catalog);
  $('context-view').hidden = !context;
  document.querySelector('.workspace').hidden = context || catalog || history;
  $('session-history').hidden = !history;
  $('page-title').textContent = context ? 'Context Lake' : catalog ? 'Catálogo de servicios' : history ? 'Historial de investigaciones' : 'Centro de investigación';
  $('page-description').textContent = context ? 'La documentación de tu plataforma, organizada en un solo lugar.' : catalog ? 'Revisa los servicios, sus relaciones y las fuentes que los documentan.' : history ? 'Consulta los análisis de esta sesión y vuelve a sus evidencias y decisiones.' : 'Del contexto a la evidencia, en un solo lugar.';
  document.querySelectorAll('.side-nav a').forEach(a => {
    const active = !catalog && a.hash === (context ? '#context-lake' : location.hash === '#session-history' ? '#session-history' : '#investigation');
    a.classList.toggle('selected', active);
    if (active) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current');
  });
  if (context) document.querySelector('.context-panel').open = true;
}
window.addEventListener('hashchange', navigateWorkspace);
navigateWorkspace();

function closeSourcePicker(focus = false) {
  $('mode-options').hidden = true;
  $('mode-trigger').setAttribute('aria-expanded', 'false');
  if (focus) $('mode-trigger').focus();
}
function renderSourcePicker() {
  const select = $('mode');
  $('mode-trigger').replaceChildren(document.createTextNode(select.selectedOptions[0]?.textContent || 'Fuente de evidencia'), node('span','⌄'));
  $('mode-options').replaceChildren(...[...select.options].map(option => {
    const button = node('button',option.textContent);
    button.type = 'button'; button.role = 'option'; button.disabled = option.disabled;
    button.setAttribute('aria-selected',String(option.selected));
    button.addEventListener('click',()=>{select.value=option.value;modeChanged();closeSourcePicker(true);});
    return button;
  }));
}
function openSourcePicker() {
  renderSourcePicker(); $('mode-options').hidden=false;
  $('mode-trigger').setAttribute('aria-expanded','true');
  ($('mode-options').querySelector('[aria-selected="true"]:not(:disabled)') || $('mode-options').querySelector('button:not(:disabled)'))?.focus();
}
$('mode-trigger').addEventListener('click',()=>{$('mode-options').hidden ? openSourcePicker() : closeSourcePicker();});
$('mode-trigger').addEventListener('keydown',event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();openSourcePicker();}});
$('mode-options').addEventListener('keydown',event=>{
  const items=[...$('mode-options').querySelectorAll('button:not(:disabled)')];
  const index=items.indexOf(document.activeElement);
  if(event.key==='Escape'){event.preventDefault();closeSourcePicker(true);}
  if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
    event.preventDefault(); const next=event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowDown'?1:-1)+items.length)%items.length;items[next]?.focus();
  }
});
document.addEventListener('click',event=>{if(!event.target.closest('.evidence-picker'))closeSourcePicker();});
document.querySelector('.evidence-picker').addEventListener('focusout',event=>{if(!event.currentTarget.contains(event.relatedTarget))closeSourcePicker();});

function closeServicePicker(focus = false) {
  $('service-options').hidden = true;
  $('service-trigger').setAttribute('aria-expanded','false');
  if(focus) $('service-trigger').focus();
}
function renderServicePicker() {
  const select = $('service');
  $('service-trigger').disabled = !select.options.length;
  $('service-trigger').replaceChildren(document.createTextNode(select.selectedOptions[0]?.textContent || 'Sin servicios disponibles'),node('span','⌄'));
  $('service-options').replaceChildren(...[...select.options].map(option=>{
    const button=node('button',option.textContent); button.type='button'; button.role='option';button.disabled=option.disabled;
    button.setAttribute('aria-selected',String(option.selected));
    button.addEventListener('click',()=>{select.value=option.value;select.dispatchEvent(new Event('change'));renderServicePicker();closeServicePicker(true);});
    return button;
  }));
}
function openServicePicker() {
  renderServicePicker(); $('service-options').hidden=false; $('service-trigger').setAttribute('aria-expanded','true');
  ($('service-options').querySelector('[aria-selected="true"]') || $('service-options').querySelector('button'))?.focus({preventScroll:true});
}
$('service-trigger').addEventListener('click',()=>{$('service-options').hidden?openServicePicker():closeServicePicker();});
$('service-trigger').addEventListener('keydown',event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();openServicePicker();}});
$('service-options').addEventListener('keydown',event=>{
  const items=[...$('service-options').querySelectorAll('button:not(:disabled)')],index=items.indexOf(document.activeElement);
  if(event.key==='Escape'){event.preventDefault();closeServicePicker(true);}
  if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowDown'?1:-1)+items.length)%items.length;items[next]?.focus();}
});
document.addEventListener('click',event=>{if(!event.target.closest('.service-picker'))closeServicePicker();});
document.querySelector('.service-picker').addEventListener('focusout',event=>{if(!event.currentTarget.contains(event.relatedTarget))closeServicePicker();});

function closeScenarioPicker(focus = false) {
  $('scenario-options').hidden = true;
  $('scenario-trigger').setAttribute('aria-expanded','false');
  if(focus) $('scenario-trigger').focus();
}
function renderScenarioPicker() {
  const select = $('scenario');
  $('scenario-trigger').disabled = !select.options.length;
  $('scenario-trigger').replaceChildren(document.createTextNode(select.selectedOptions[0]?.textContent || 'Sin servicios disponibles'),node('span','⌄'));
  $('scenario-options').replaceChildren(...[...select.options].map(option=>{
    const button=node('button',option.textContent); button.type='button'; button.role='option';button.disabled=option.disabled;
    button.setAttribute('aria-selected',String(option.selected));
    button.addEventListener('click',()=>{select.value=option.value;select.dispatchEvent(new Event('change'));renderScenarioPicker();closeScenarioPicker(true);});
    return button;
  }));
}
function openScenarioPicker() {
  renderScenarioPicker(); $('scenario-options').hidden=false; $('scenario-trigger').setAttribute('aria-expanded','true');
  ($('scenario-options').querySelector('[aria-selected="true"]') || $('scenario-options').querySelector('button'))?.focus({preventScroll:true});
}
$('scenario-trigger').addEventListener('click',()=>{$('scenario-options').hidden?openScenarioPicker():closeScenarioPicker();});
$('scenario-trigger').addEventListener('keydown',event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();openScenarioPicker();}});
$('scenario-options').addEventListener('keydown',event=>{
  const items=[...$('scenario-options').querySelectorAll('button:not(:disabled)')],index=items.indexOf(document.activeElement);
  if(event.key==='Escape'){event.preventDefault();closeScenarioPicker(true);}
  if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowDown'?1:-1)+items.length)%items.length;items[next]?.focus();}
});
document.addEventListener('click',event=>{if(!event.target.closest('.scenario-picker'))closeScenarioPicker();});
document.querySelector('.scenario-picker').addEventListener('focusout',event=>{if(!event.currentTarget.contains(event.relatedTarget))closeScenarioPicker();});

function selectedScope() { return document.querySelector('input[name="scope"]:checked').value; }
function updateScope() {
  const general = selectedScope() === 'general', gcp = $('mode').value === 'gcp';
  $('focused-fields').hidden = general;
  $('service').required = !general;
  $('scope-note').textContent = general ? (gcp ? 'Consulta los servicios del catálogo confirmado, dentro de la ventana indicada. Errores paginados en toda la ventana; sin errores, muestra de actividad reciente. El diagnóstico conserva sus reglas actuales.' : 'Analiza todas las señales del escenario simulado seleccionado. No consulta el entorno real.') : 'Comienza por el servicio elegido y sus vecinos documentados.';
  const unavailable = general && gcp && configuration?.catalog_status !== 'confirmed';
  if(unavailable) $('scope-note').textContent = 'Confirma el catálogo antes de iniciar un análisis general con logs reales.';
  $('run').disabled = analyzing || unavailable || (!general && !$('service').options.length);
}
document.querySelectorAll('input[name="scope"]').forEach(input=>input.addEventListener('change',updateScope));

async function suggestIncident() {
  const reserve = () => {
    try {
      const raw = Number(localStorage.getItem('tider.incident.sequence.v1'));
      const previous = Number.isSafeInteger(raw) && raw >= 0 ? raw : 0;
      const next = previous + 1;
      localStorage.setItem('tider.incident.sequence.v1',String(next));
      $('incident').value = 'INC-' + String(next).padStart(4,'0');
      $('incident-note').textContent = 'Numeración automática de este navegador. Puedes editar la referencia. Los números reservados pueden dejar saltos.';
    } catch {
      $('incident').value = 'INC-' + Date.now();
      $('incident-note').textContent = 'El navegador no permite guardar la secuencia; se generó una referencia temporal.';
    }
  };
  if(navigator.locks) await navigator.locks.request('tider-incident-sequence',reserve); else reserve();
}

function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle('sidebar-collapsed',collapsed);
  $('sidebar-toggle').setAttribute('aria-expanded',String(!collapsed));
  const label=collapsed?'Expandir menú':'Contraer menú';
  $('sidebar-toggle').setAttribute('aria-label',label); $('sidebar-toggle').title=label;
}
document.querySelectorAll('.side-nav a,.side-nav button').forEach(item=>{const label=item.querySelector('.nav-label')?.textContent;if(label){item.setAttribute('aria-label',label);item.title=label;}});
try { setSidebarCollapsed(localStorage.getItem('tider.sidebar.collapsed')==='true'); } catch {}
$('sidebar-toggle').addEventListener('click',()=>{const collapsed=!document.body.classList.contains('sidebar-collapsed');setSidebarCollapsed(collapsed);try{localStorage.setItem('tider.sidebar.collapsed',String(collapsed));}catch{}});

document.querySelectorAll('input[name="time-mode"]').forEach(input=>input.addEventListener('change',updateTimeChoice));
