/** HTTP client shared by the form and history. */
export async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    const message = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg).join('; ')
      : data.detail || 'No se pudo completar la solicitud.';
    throw new Error(message);
  }
  return data;
}

export function analyzeIncident(payload, signal) {
  return fetchJSON('/v1/incidents/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify(payload),
  });
}

/** Server events describe completed queries, not a simulated stage timer. */
export async function investigateIncident(payload, signal, onStep) {
  const response = await fetch('/v1/incidents/investigate-stream', {
    method:'POST', headers:{'Content-Type':'application/json'}, signal, body:JSON.stringify(payload),
  });
  if(!response.ok) throw new Error('No se pudo iniciar la investigación. Revisa la configuración.');
  const reader=response.body.getReader(), decoder=new TextDecoder();
  let buffer='', result;
  while(true) {
    const {value,done}=await reader.read();
    buffer+=decoder.decode(value,{stream:!done});
    let boundary;
    while((boundary=buffer.indexOf('\n'))>=0) {
      const line=buffer.slice(0,boundary); buffer=buffer.slice(boundary+1);
      if(!line.trim())continue;
      const event=JSON.parse(line);
      if(event.type==='error')throw new Error(event.message);
      if(event.type==='step')onStep(event.step);
      if(event.type==='result')result=event.result;
    }
    if(done)break;
  }
  if(!result)throw new Error('La transmisión terminó sin resultado; revisa el historial.');
  return result;
}
