// API client for the triage backend. Base URL is configurable at build time
// via VITE_API_BASE (set in docker-compose in Step 5); defaults to local dev.
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function post(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(data.detail || `Request failed (${res.status})`)
  }
  return data
}

export function triage({ ticketText, ticketId }) {
  return post('/triage', { ticket_text: ticketText, ticket_id: ticketId || null })
}

export function resume({ threadId, decision }) {
  return post('/resume', { thread_id: threadId, decision })
}

export { API_BASE }
