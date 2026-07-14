import { useState } from 'react'
import { triage, resume } from './api.js'

const EXAMPLES = [
  { label: 'Simple: password reset', text: 'I forgot my password and I am locked out. How do I reset it?' },
  { label: 'Ambiguous: refund + cancel', text: 'I was charged twice this month. I want a full refund and my account closed.' },
]

function Badge({ value }) {
  const cls =
    value === 'simple' ? 'badge simple'
    : value === 'ambiguous' ? 'badge ambiguous'
    : value === 'resolved' ? 'badge resolved'
    : value === 'escalated' ? 'badge escalated'
    : value === 'pending_approval' ? 'badge pending'
    : 'badge'
  return <span className={cls}>{value}</span>
}

export default function App() {
  const [ticketText, setTicketText] = useState('')
  const [ticketId, setTicketId] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function onSubmit(e) {
    e.preventDefault()
    setError(''); setResult(null); setLoading(true)
    try {
      const data = await triage({ ticketText, ticketId })
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function onDecision(decision) {
    if (!result?.thread_id) return
    setError(''); setBusy(true)
    try {
      const data = await resume({ threadId: result.thread_id, decision })
      // Merge so we keep the original ticket context alongside the outcome.
      setResult((prev) => ({ ...prev, ...data }))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const pending = result?.status === 'pending_approval'

  return (
    <div className="wrap">
      <header>
        <h1>Support Triage Agent</h1>
        <p className="sub">Classify a ticket → auto-resolve simple ones, pause ambiguous ones for approval.</p>
        <p className="tagline">Powered by Claude + LangGraph · RAG knowledge base · human-in-the-loop</p>
      </header>

      <form onSubmit={onSubmit} className="card">
        <label htmlFor="tid">Ticket ID <span className="muted">(optional)</span></label>
        <input id="tid" value={ticketId} onChange={(e) => setTicketId(e.target.value)} placeholder="T-1001" />

        <label htmlFor="text">Ticket text</label>
        <textarea
          id="text" rows={4} value={ticketText} required
          onChange={(e) => setTicketText(e.target.value)}
          placeholder="Describe the customer's issue..."
        />

        <div className="examples">
          {EXAMPLES.map((ex) => (
            <button type="button" key={ex.label} className="chip" onClick={() => setTicketText(ex.text)}>
              {ex.label}
            </button>
          ))}
        </div>

        <button type="submit" className="primary" disabled={loading || !ticketText.trim()}>
          {loading ? 'Triaging…' : 'Triage ticket'}
        </button>
      </form>

      {error && <div className="card error">Error: {error}</div>}

      {result && (
        <div className="card result">
          <div className="row">
            <span className="k">Ticket</span>
            <span>{result.ticket_id}</span>
          </div>
          <div className="row">
            <span className="k">Category</span>
            <Badge value={result.category} />
          </div>
          <div className="row">
            <span className="k">Status</span>
            <Badge value={result.status} />
          </div>
          {result.reasoning && (
            <div className="reasoning"><span className="k">Reasoning</span><p>{result.reasoning}</p></div>
          )}

          {pending && (
            <div className="approval">
              <p><strong>Human approval required.</strong> {result.approval_request?.question}</p>
              <div className="btns">
                <button className="approve" disabled={busy} onClick={() => onDecision('approve')}>
                  {busy ? '…' : 'Approve'}
                </button>
                <button className="reject" disabled={busy} onClick={() => onDecision('reject')}>
                  {busy ? '…' : 'Reject / escalate'}
                </button>
              </div>
            </div>
          )}

          {result.human_decision && (
            <div className="row"><span className="k">Human decision</span><span>{result.human_decision}</span></div>
          )}

          {result.final_action && (
            <div className="final">
              <span className="k">Final action</span>
              <pre>{JSON.stringify(result.final_action, null, 2)}</pre>
            </div>
          )}

          {result.resolution && (
            <div className="final">
              <span className="k">Auto-response</span>
              <p className="body">{result.resolution.body}</p>
            </div>
          )}
        </div>
      )}

      <footer className="foot">🚀 Auto-deployed to AWS EC2 via GitHub Actions</footer>
    </div>
  )
}
