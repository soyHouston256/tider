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
