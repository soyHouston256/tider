/** Context retrieval sandbox: DOM text only, no execution of uploaded content. */
const el = (id) => document.getElementById(id);
const status = (text) => { el('context-status').textContent = text; };
let busy = false;
async function request(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Revisa el archivo o la consulta.');
  return body;
}
function textNode(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}
async function refresh() {
  const data = await request('/v1/context');
  el('context-documents').replaceChildren();
  for (const doc of data.documents) {
    const item = document.createElement('li');
    const diagram = /\.drawio$/i.test(doc.name);
    item.className = diagram ? 'document-row document-diagram' : 'document-row document-markdown';
    const icon = document.createElement('span'); icon.className = 'document-icon'; icon.setAttribute('aria-hidden','true');
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    for (const [key,value] of Object.entries({viewBox:'0 0 32 32',fill:'none',stroke:'currentColor','stroke-width':'1.6','stroke-linecap':'round','stroke-linejoin':'round'})) svg.setAttribute(key,value);
    const paths = diagram
      ? ['M14 10v5H7v6m7-6h11v6', 'M11 3h10v7H11z', 'M3 21h8v7H3z', 'M21 21h8v7h-8z']
      : ['M19 3H8a2 2 0 0 0-2 2v22a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V10z', 'M19 3v7h7', 'M11 16h10M11 21h10M11 25h6'];
    for (const d of paths) { const path=document.createElementNS(ns,'path');path.setAttribute('d',d);svg.append(path); }
    icon.append(svg);
    const description = document.createElement('div'); description.className = 'document-description';
    description.append(textNode('strong', doc.name), textNode('small', `${doc.chunks} fragmentos disponibles para búsqueda`));
    const type = textNode('span', diagram ? 'draw.io · Diagrama' : 'Markdown · Documento'); type.className = 'document-type';
    item.append(icon, description, type);
    const remove = textNode('button', 'Retirar');
    remove.type = 'button';
    remove.setAttribute('aria-label', `Retirar ${doc.name}`);
    remove.addEventListener('click', async () => {
      if (busy) return;
      busy = true;
      try {
        await request(`/v1/context/documents/${doc.id}`, {method: 'DELETE'});
        el('context-matches').replaceChildren();
        await refresh();
      } catch (error) { status(error.message); }
      finally { busy = false; }
    });
    item.append(remove);
    el('context-documents').append(item);
  }
  document.dispatchEvent(new Event('context-documents-changed'));
  status(data.documents.length ? `${data.documents.length} documentos · ${data.chunks} fragmentos disponibles` : 'Sin documentos. Carga tu primer archivo.');
}
async function upload(files) {
  if (busy) return;
  busy = true;
  const errors = [];
  try {
    for (const file of files) {
      status(`Procesando ${file.name}… La primera carga puede tardar por la descarga del modelo local.`);
      try {
        if (file.size > 1000000) throw new Error('supera 1 MB');
        if (!/\.(md|drawio)$/i.test(file.name)) throw new Error('formato no admitido');
        await request('/v1/context/documents', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({name: file.name, content: await file.text()})});
      } catch (error) { errors.push(`${file.name}: ${error.message}`); }
    }
    await refresh();
    if (errors.length) status(errors.join(' · '));
  } catch (error) { status(error.message); }
  finally { busy = false; el('context-files').value = ''; }
}
el('context-files').addEventListener('change', (event) => upload([...event.target.files]));
const drop = el('context-drop');
for (const name of ['dragenter', 'dragover']) drop.addEventListener(name, (event) => {
  event.preventDefault(); drop.classList.add('dragging');
});
for (const name of ['dragleave', 'drop']) drop.addEventListener(name, (event) => {
  event.preventDefault(); drop.classList.remove('dragging');
});
drop.addEventListener('drop', (event) => upload([...event.dataTransfer.files]));
el('context-search').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;
  const query = el('context-query').value.trim();
  if (!query) return;
  busy = true;
  status('Buscando fragmentos relacionados…');
  el('context-matches').replaceChildren();
  try {
    const data = await request('/v1/context/search', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({query})});
    for (const match of data.matches) {
      const card = document.createElement('article');
      card.append(textNode('strong', `${match.title} · ${match.page} · fragmento ${match.chunk}`));
      card.append(textNode('p', match.text));
      el('context-matches').append(card);
    }
    status(data.matches.length ? 'Fragmentos más cercanos. Revisa su relevancia; no prueban una causa del incidente.' : 'No encontramos información suficiente sobre esta consulta en los documentos cargados.');
  } catch (error) { status(error.message); }
  finally { busy = false; }
});
refresh().catch((error) => status(error.message));
