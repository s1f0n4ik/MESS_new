import { useEffect, useRef, useState } from 'react'
import { apiUrl } from '../net/urls'

const SKIP = new Set(['at', 'src', 'tag'])

function fmt(r) {
  const t = String(r.at || '').slice(11, 23)
  const rest = Object.entries(r)
    .filter(([k]) => !SKIP.has(k))
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`)
    .join(' ')
  return `${t} ${String(r.src || '').padEnd(9)} ${String(r.tag || '').padEnd(22)} ${rest}`
}

/** Единый журнал координатора. Открывается по L на любой машине, без admin. */
export function LogPanel({ serverHost, role, onClose }) {
  const [rows, setRows] = useState([])
  const [err, setErr] = useState('')
  const [filter, setFilter] = useState('')
  const [paused, setPaused] = useState(false)
  const [copied, setCopied] = useState(false)
  const boxRef = useRef(null)

  useEffect(() => {
    let stop = false
    const tick = async () => {
      if (stop || paused || document.hidden) return
      try {
        const r = await fetch(apiUrl('/api/log/tail?n=600', serverHost))
        if (r.status === 404) throw new Error('бэкенд без /api/log — пересобери postcards-backend.exe')
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        setRows((await r.json()).slice().reverse()) // tail отдаёт новые первыми
        setErr('')
      } catch (e) {
        setErr(e.message || String(e))
      }
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => { stop = true; clearInterval(id) }
  }, [serverHost, paused])

  useEffect(() => {
    if (!paused && boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight
  }, [rows, paused])

  const lines = rows.map(fmt).filter((l) => !filter || l.toLowerCase().includes(filter.toLowerCase()))

  const copyAll = async () => {
    const text = `# role=${role} host=${serverHost || location.host} ${new Date().toISOString()}\n${lines.join('\n')}`
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500) }
    catch { window.prompt('Скопируй:', text) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(0,0,0,0.92)', color: '#ddd',
      display: 'flex', flexDirection: 'column', fontFamily: 'monospace', fontSize: 12 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '8px 12px', borderBottom: '1px solid #333' }}>
        <b>Журнал стенда</b>
        <span style={{ opacity: 0.6 }}>файл на координаторе: data\logs\scenario-ГГГГ-ММ-ДД.log</span>
        <input placeholder="фильтр: midi / pc3 / window / click" value={filter}
          onChange={(e) => setFilter(e.target.value)} style={{ marginLeft: 'auto', width: 260 }} />
        <button onClick={() => setPaused((p) => !p)}>{paused ? '▶ обновлять' : '⏸ пауза'}</button>
        <button onClick={copyAll}>{copied ? '✓ скопировано' : 'копировать всё'}</button>
        <button onClick={onClose}>✕ (L / Esc)</button>
      </div>
      {err && <div style={{ color: '#e88', padding: '6px 12px' }}>{err}</div>}
      <pre ref={boxRef} style={{ flex: 1, margin: 0, padding: 12, overflow: 'auto', whiteSpace: 'pre', lineHeight: 1.5 }}>
        {lines.join('\n')}
      </pre>
      <div style={{ padding: '4px 12px', opacity: 0.5, borderTop: '1px solid #333' }}>
        {lines.length} строк · src: midi — ноты, scenario — решения, presence — соединения, pc1..pc4 — что сделал клиент со своим окном
      </div>
    </div>
  )
}