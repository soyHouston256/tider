/** Form interactions and session state. Rendering and HTTP have separate modules. */
import { fetchJSON, analyzeIncident } from './api.js';
import { $, node, renderFlow, showResult, renderHistory } from './render.js';

let configuration;
let currentResult;
let runs = [];

function selectResult(result) {
  currentResult = result;
  showResult(result);
}

function updateHistory() {
  renderHistory(runs, (result) => {
    selectResult(result);
    $('result').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

function setDates() {
  const end = new Date();
  const start = new Date(end.getTime() - 10 * 60 * 1000);
  const local = (date) => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  $('start').value = local(start);
  $('end').value = local(end);
}

function scenarioChanged() {
  const scenario = configuration.scenarios.find((item) => item.id === $('scenario').value);
  $('scenario-note').textContent = scenario.description;
  $('service').value = scenario.service;
}

function modeChanged() {
  const gcp = $('mode').value === 'gcp';
  $('scenario-fields').hidden = gcp;
  $('time-fields').hidden = !gcp;
  $('mode-note').textContent = gcp
    ? 'Consulta real de Cloud Logging, limitada al entorno configurado. Las métricas y trazas aún no están conectadas.'
    : 'Señales sintéticas. No necesita conexión a GCP.';
  if (gcp) setDates();
}

function buildRequest() {
  const gcp = $('mode').value === 'gcp';
  const end = gcp ? new Date($('end').value) : new Date();
  const start = gcp ? new Date($('start').value) : new Date(end.getTime() - 10 * 60 * 1000);
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start || end - start > 7200000) {
    throw new Error('Elige una ventana positiva de hasta dos horas.');
  }
  return {
    incident_id: $('incident').value.trim(), service: $('service').value,
    mode: $('mode').value, scenario: $('scenario').value,
    start: start.toISOString(), end: end.toISOString(),
  };
}

async function submitAnalysis(event) {
  event.preventDefault();
  $('error').hidden = true;
  $('run').disabled = true;
  $('run').textContent = 'Analizando…';
  $('flow-status').textContent = 'Procesando evidencia…';
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120000);
  try {
    const result = await analyzeIncident(buildRequest(), controller.signal);
    selectResult(result);
    runs = [result, ...runs].slice(0, configuration.history_limit);
    updateHistory();
  } catch (error) {
    $('error').textContent = error.name === 'AbortError'
      ? 'La consulta tardó demasiado. El servidor puede seguir procesándola; revisa el historial antes de repetir.'
      : error.message;
    $('error').hidden = false;
    $('flow-status').textContent = 'No se completó esta consulta';
  } finally {
    clearTimeout(timeout);
    $('run').disabled = false;
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
  $('incident').value = 'CF-' + Date.now().toString().slice(-8);
  try {
    configuration = await fetchJSON('/v1/lab/config');
    for (const id of ['project', 'cluster', 'namespace']) $(id).textContent = configuration[id];
    $('reasoning').textContent = configuration.reasoning_mode === 'none' ? 'Baseline por reglas' : configuration.model;
    const gcpOption = new Option('Logs de GKE', 'gcp');
    gcpOption.disabled = !configuration.gcp_enabled;
    $('mode').replaceChildren(new Option('Simulación local', 'mock'), gcpOption);
    $('service').replaceChildren(...configuration.services.map((service) => new Option(service, service)));
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
