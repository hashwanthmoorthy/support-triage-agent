import { useState } from 'react'
import { triage, resume } from './api.js'

const EXAMPLES = [
  { label: 'Simple', hint: 'password reset', text: 'I forgot my password and I am locked out. How do I reset it?' },
  { label: 'Ambiguous', hint: 'refund + cancel', text: 'I was charged twice this month. I want a full refund and my account closed.' },
  { label: 'Invalid', hint: 'off-topic', text: 'tell me about u' },
]

const CATEGORY_BADGE = { simple: 'simple', ambiguous: 'ambiguous', invalid: 'invalid' }

function Badge({ value, kind = '' }) {
  return <span className={`badge ${kind || value}`}>{String(value).replace('_', ' ')}</span>
}

// --- derived views ---------------------------------------------------------

function outcome(r) {
  if (r.status === 'pending_approval')
    return { cls: 'pending', icon: '⏳', title: 'Awaiting human approval',
             text: 'This ticket needs a human decision before any action is taken.' }
  if (r.category === 'invalid')
    return { cls: 'invalid', icon: '🚫', title: 'Not a support request', text: r.resolution?.body }
  if (r.status === 'escalated')
    return { cls: 'escalated', icon: '⚠️', title: 'Escalated to a human agent',
             text: 'A human rejected auto-resolution, so the ticket was routed to an agent.' }
  if (r.status === 'resolved')
    return { cls: 'resolved', icon: '✅',
             title: r.human_decision === 'approve' ? 'Approved & resolved' : 'Auto-resolved',
             text: r.resolution?.body }
  return { cls: '', icon: '•', title: r.status || 'Result', text: '' }
}

function journey(r) {
  if (r.category === 'invalid')
    return [{ label: 'Classified: invalid', s: 'done' }, { label: 'Clarification requested', s: 'done' }]
  if (r.category === 'simple')
    return [
      { label: 'Classified: simple', s: 'done' },
      { label: 'Gathered info (RAG + tools)', s: 'done' },
      { label: 'Auto-resolved', s: 'done' },
    ]
  // ambiguous
  const steps = [{ label: 'Classified: ambiguous', s: 'done' }]
  if (r.status === 'pending_approval') {
    steps.push({ label: 'Awaiting approval', s: 'current' }, { label: 'Action', s: 'todo' })
  } else if (r.human_decision === 'approve') {
    steps.push({ label: 'Human approved', s: 'done' }, { label: 'Resolved', s: 'done' })
  } else {
    steps.push({ label: 'Human rejected', s: 'done' }, { label: 'Escalated', s: 'done' })
  }
  return steps
}

function actionLabel(fa) {
  if (!fa) return null
  const map = {
    send_response: 'Sent response to customer',
    escalate: 'Escalated to a human agent',
    request_clarification: 'Requested clarification',
  }
  return map[fa.type] || fa.type
}

// --- components ------------------------------------------------------------

function Stepper({ steps }) {
  return (
    <div className="stepper">
      {steps.map((st, i) => (
        <div key={i} className={`step ${st.s}`}>
          <span className="dot" />
          <span className="lbl">{st.label}</span>
          {i < steps.length - 1 && <span className="conn" />}
        </div>
      ))}
    </div>
  )
}

function Sources({ sources }) {
  if (!sources?.length) return null
  return (
    <div className="sources">
      <span className="k">Knowledge base sources</span>
      <div className="src-pills">
        {sources.map((s) => (
          <span key={s.source} className="src" title={s.distance != null ? `distance ${s.distance}` : ''}>
            📄 {s.source}
          </span>
        ))}
      </div>
    </div>
  )
}

function ResultView({ r, busy, onDecision }) {
  const o = outcome(r)
  const pending = r.status === 'pending_approval'
  return (
    <div className={`card result ${o.cls}`}>
      <div className="banner">
        <span className="ic">{o.icon}</span>
        <div>
          <div className="btitle">{o.title}</div>
          <div className="bmeta">
            {r.ticket_id} · <Badge value={r.category} kind={CATEGORY_BADGE[r.category]} />
          </div>
        </div>
      </div>

      <Stepper steps={journey(r)} />

      {r.reasoning && (
        <div className="block">
          <span className="k">Why</span>
          <p>{r.reasoning}</p>
        </div>
      )}

      {pending && (
        <div className="approval">
          <p><strong>Human approval required.</strong> {r.approval_request?.question}</p>
          <div className="btns">
            <button className="approve" disabled={busy} onClick={() => onDecision('approve')}>
              {busy ? '…' : '✓ Approve'}
            </button>
            <button className="reject" disabled={busy} onClick={() => onDecision('reject')}>
              {busy ? '…' : '✕ Reject / escalate'}
            </button>
          </div>
        </div>
      )}

      {o.text && (
        <div className="block">
          <span className="k">{r.category === 'invalid' ? 'Response' : 'Auto-response'}</span>
          <p className="body">{o.text}</p>
        </div>
      )}

      <Sources sources={r.sources} />

      {r.final_action && (
        <div className="block">
          <span className="k">Action taken</span>
          <p className="action">{actionLabel(r.final_action)}</p>
          <details className="raw">
            <summary>Raw action JSON</summary>
            <pre>{JSON.stringify(r.final_action, null, 2)}</pre>
          </details>
        </div>
      )}
    </div>
  )
}

function History({ items, activeId, onSelect }) {
  return (
    <aside className="history">
      <h2>Session history</h2>
      {items.length === 0 && <p className="empty">No tickets yet. Submit one to get started.</p>}
      <ul>
        {items.map((it) => (
          <li key={it.thread_id}
              className={`${it.thread_id === activeId ? 'active' : ''}`}
              onClick={() => onSelect(it.thread_id)}>
            <div className="hrow">
              <span className="hid">{it.ticket_id}</span>
              <Badge value={it.status} />
            </div>
            <div className="htext">{it.ticketText}</div>
          </li>
        ))}
      </ul>
    </aside>
  )
}

export default function App() {
  const [ticketText, setTicketText] = useState('')
  const [ticketId, setTicketId] = useState('')
  const [history, setHistory] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const current = history.find((h) => h.thread_id === activeId) || null

  function upsert(record) {
    setHistory((prev) => {
      const rest = prev.filter((h) => h.thread_id !== record.thread_id)
      return [record, ...rest]
    })
    setActiveId(record.thread_id)
  }

  async function onSubmit(e) {
    e.preventDefault()
    if (!ticketText.trim()) return
    setError(''); setLoading(true)
    try {
      const data = await triage({ ticketText, ticketId })
      upsert({ ...data, ticketText })
      setTicketText(''); setTicketId('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function onDecision(decision) {
    if (!current?.thread_id) return
    setError(''); setBusy(true)
    try {
      const data = await resume({ threadId: current.thread_id, decision })
      upsert({ ...current, ...data })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) onSubmit(e)
  }

  return (
    <div className="wrap">
      <header>
        <div className="brand"><span className="mark">🎫</span><h1>Support Triage Agent</h1></div>
        <p className="sub">Classifies a ticket, then auto-resolves simple ones, pauses ambiguous ones for approval, and rejects invalid input.</p>
        <p className="tagline">Claude + LangGraph · RAG knowledge base · human-in-the-loop</p>
      </header>

      <div className="layout">
        <main>
          <form onSubmit={onSubmit} className="card">
            <label htmlFor="tid">Ticket ID</label>
            <input id="tid" value={ticketId} onChange={(e) => setTicketId(e.target.value)} placeholder="T-1001" />
            <p className="caption">Leave blank to auto-generate.</p>

            <label htmlFor="text">Ticket text</label>
            <textarea
              id="text" rows={4} value={ticketText}
              onChange={(e) => setTicketText(e.target.value)} onKeyDown={onKeyDown}
              placeholder="Describe the customer's issue…"
            />

            <div className="examples">
              <span className="ex-label">Try:</span>
              {EXAMPLES.map((ex) => (
                <button type="button" key={ex.label} className="chip" onClick={() => setTicketText(ex.text)}>
                  {ex.label} <span className="chip-hint">· {ex.hint}</span>
                </button>
              ))}
            </div>

            <div className="form-actions">
              <button type="submit" className="primary" disabled={loading || !ticketText.trim()}>
                {loading ? 'Classifying…' : 'Triage ticket'}
              </button>
              <span className="kbd-hint">⌘/Ctrl + Enter</span>
            </div>
          </form>

          {error && <div className="card error">⚠️ {error}</div>}

          {current && <ResultView r={current} busy={busy} onDecision={onDecision} />}
        </main>

        <History items={history} activeId={activeId} onSelect={setActiveId} />
      </div>

      <footer className="foot">🚀 Auto-deployed to AWS EC2 via GitHub Actions</footer>
    </div>
  )
}
