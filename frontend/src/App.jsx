import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

const ROLES = ['pc1', 'pc2', 'pc3', 'pc4']

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  return r.json()
}

export default function App() {
  const [role, setRole] = useState('pc1')
  const [state, setState] = useState(null)
  const pdfWinRef = useRef(null)

  const flips = useMemo(
    () => state?.flippedCardsByRole?.[role] || {},
    [state, role]
  )

  async function loadState() {
    const s = await api('/api/state')
    setState(s)
  }

  useEffect(() => {
    loadState()
    const t = setInterval(loadState, 500)
    return () => clearInterval(t)
  }, [])

  async function sendAction(payload) {
    await api('/api/action', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await loadState()
  }

  async function onCardClick(i) {
    await sendAction({ type: 'card_click', role, cardIndex: i })
  }

  async function openPdf() {
    const pdfFile = state?.pdfsByRole?.[role] || `${role}.pdf`
    await sendAction({ type: 'open_pdf', role, pdfFile })

    const url = `/pdf-viewer.html?role=${encodeURIComponent(role)}`
    if (!pdfWinRef.current || pdfWinRef.current.closed) {
      pdfWinRef.current = window.open(url, `pdf_${role}`, 'width=1100,height=800')
    } else {
      pdfWinRef.current.focus()
    }
  }

  async function closePdf() {
    await sendAction({ type: 'close_pdf', role })
  }

  async function resetRole() {
    await sendAction({ type: 'reset_clicks', role })
  }

  return (
    <div className="wrap">
      <h1>Postcards · Slice 1</h1>

      <div className="toolbar">
        <label>Роль:&nbsp;
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {ROLES.map((r) => <option key={r} value={r}>{r.toUpperCase()}</option>)}
          </select>
        </label>

        <button onClick={openPdf}>Открыть PDF-окно</button>
        <button onClick={closePdf}>Закрыть PDF-окно</button>
        <button onClick={resetRole}>Сбросить клики роли</button>
      </div>

      <div className="status">
        <div>stateVersion: {state?.stateVersion ?? '...'}</div>
        <div>Клики ({role.toUpperCase()}): {state?.clicksByRole?.[role] ?? 0}</div>
        <div>
          PDF окно: {state?.pdfWindow?.visible ? 'открыто' : 'закрыто'} ·
          &nbsp;роль {state?.pdfWindow?.role || '-'} ·
          &nbsp;файл {state?.pdfWindow?.pdfFile || '-'}
        </div>
      </div>

      <div className="cards">
        {Array.from({ length: 8 }).map((_, i) => {
          const flipped = Boolean(flips[String(i)])
          return (
            <button key={i} className={`card ${flipped ? 'flipped' : ''}`} onClick={() => onCardClick(i)}>
              <span>{i + 1}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}