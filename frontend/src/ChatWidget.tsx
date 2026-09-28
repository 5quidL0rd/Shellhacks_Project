import { useState, type FormEvent } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from './api'
import type { Position } from './hooks'

interface Message { role: 'user' | 'assistant'; text: string; source?: string }

export function ChatWidget({ holdings, positions }: { holdings: string[]; positions: Record<string, Position> }) {
  const location = useLocation()
  const selected = location.pathname.match(/^\/stock\/([A-Z.]+)$/i)?.[1]?.toUpperCase() ?? null
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [busy, setBusy] = useState(false)

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const text = question.trim()
    if (!text || busy) return
    setQuestion('')
    setMessages((rows) => [...rows, { role: 'user', text }])
    setBusy(true)
    try {
      const result = await api.chat(text, selected, holdings, positions)
      setMessages((rows) => [...rows, { role: 'assistant', text: result.answer,
        source: `${result.provider} · ${result.model}` }])
    } catch (error) {
      setMessages((rows) => [...rows, { role: 'assistant',
        text: error instanceof Error ? error.message : 'The assistant is unavailable.' }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="chat-dock">
      {open && <section className="chat-panel" aria-label="Cortex data assistant">
        <div className="chat-head">
          <div><strong>Ask your portfolio</strong><span>Snowflake Cortex · {selected ?? 'all holdings'}</span></div>
          <button type="button" onClick={() => setOpen(false)} aria-label="Close assistant">×</button>
        </div>
        <div className="chat-messages" aria-live="polite">
          {messages.length === 0 && <div className="chat-intro">
            Ask about {selected ? `${selected}'s price, major moves, or` : 'stock prices, saved news, or'} your portfolio's shared dependencies.
            <small>Quotes are from Finnhub; stories and news are dated snapshots. This is research, not investment advice.</small>
          </div>}
          {messages.map((message, index) => <div key={index} className={`chat-message ${message.role}`}>
            <p>{message.text}</p>{message.source && <small>{message.source}</small>}
          </div>)}
          {busy && <p className="chat-wait">Checking the data…</p>}
        </div>
        <form onSubmit={ask} className="chat-form">
          <label className="visually-hidden" htmlFor="chat-question">Ask a question</label>
          <input id="chat-question" value={question} onChange={(event) => setQuestion(event.target.value)}
                 placeholder={selected ? `Ask about ${selected}…` : 'Ask about your portfolio…'} maxLength={700} />
          <button type="submit" disabled={busy || !question.trim()}>Ask</button>
        </form>
      </section>}
      <button type="button" className="chat-launch" onClick={() => setOpen((value) => !value)}
              aria-expanded={open} aria-label={open ? 'Close Cortex assistant' : 'Open Cortex assistant'}>
        <span aria-hidden="true">✦</span> Ask Cortex
      </button>
    </div>
  )
}
