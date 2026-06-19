import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

const role = 'pc1'

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  const text = await r.text()
  const data = text ? JSON.parse(text) : {}
  if (!r.ok) throw new Error(data?.error || text || `HTTP ${r.status}`)
  return data
}

export default function App() {
  const [state, setState] = useState(null)
  const pdfWinRef = useRef(null)

  useEffect(() => {
    let es
    let stopped = false

    const bootstrap = async () => {
      const snap = await api('/api/state')
      if (!stopped) setState(snap)

      es = new EventSource('/api/stream')
      es.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg?.type === 'state' && msg?.payload) setState(msg.payload)
        } catch {}
      }
      es.onerror = () => {}
    }

    bootstrap()
    return () => {
      stopped = true
      if (es) es.close()
    }
  }, [])

  const flips = useMemo(() => state?.flippedCardsByRole?.[role] || {}, [state])

  const sendAction = (type, payload = {}) =>
    api('/api/action', { method: 'POST', body: JSON.stringify({ type, payload }) })

  const openPdfManual = async () => {
    await sendAction('open_role_popup', { role })

    const url = `/pdf-viewer.html?role=${encodeURIComponent(role)}`
    if (!pdfWinRef.current || pdfWinRef.current.closed) {
      pdfWinRef.current = window.open(url, `pdf_${role}`, 'width=1200,height=900')
    } else {
      pdfWinRef.current.location.href = url
      pdfWinRef.current.focus()
    }
  }

  const closePdfManual = async () => {
    await sendAction('close_role_popup', { role })
    if (pdfWinRef.current && !pdfWinRef.current.closed) {
      pdfWinRef.current.close()
    }
  }

  return (
    <div className="app">
      <h1>Postcards — slice 2</h1>
      <div>stateVersion: {state?.stateVersion ?? '...'}</div>
      <div>Clicks ({role}): {state?.clicksByRole?.[role] ?? 0}</div>
      <div>
        Scenario: {state?.scenario?.active ? 'active' : 'idle'} · currentRole: {state?.scenario?.currentRole || '-'}
      </div>

      <div className="toolbar">
        <button onClick={openPdfManual}>Open PDF</button>
        <button onClick={closePdfManual}>Close PDF</button>
        <button onClick={() => sendAction('launch')}>Launch → next role</button>
        <button onClick={() => sendAction('reset_all')}>Reset</button>
      </div>

      <div className="cards">
        {Array.from({ length: 8 }).map((_, i) => {
          const flipped = Boolean(flips[String(i)])
          return (
            <button
              key={i}
              className={`card ${flipped ? 'flipped' : ''}`}
              onClick={() => sendAction('click_card', { role, cardIndex: i })}
            >
              {i + 1}
            </button>
          )
        })}
      </div>
    </div>
  )
}