import { useCallback, useEffect, useRef, useState } from 'react'
import { noteName } from './midiNote'
import { MIDI_ACTIONS, LEGACY_CHANNEL, LEGACY_OUTPUT_NOTE } from './midiMapping'
import { apiUrl } from '../net/urls'

const POLL_MS = 1000

export function MidiPanel({ serverHost }) {
  const [status, setStatus] = useState(null)
  const [draft, setDraft] = useState(null)   // локальные правки маппинга
  const [busy, setBusy] = useState('')
  const [simNote, setSimNote] = useState(60)
  const draftRef = useRef(null)
  draftRef.current = draft

  const call = useCallback(
    async (path, body) => {
      const res = await fetch(apiUrl(`/api/midi${path}`, serverHost), {
        method: body ? 'POST' : 'GET',
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      })
      return res.json()
    },
    [serverHost]
  )

  // Поллинг статуса. WS не используем: MIDI-лог не часть игрового состояния,
  // незачем гнать его всем четырём ПК в каждом broadcast.
  useEffect(() => {
    let stopped = false
    const tick = async () => {
      try {
        const s = await call('/status')
        if (stopped) return
        setStatus(s)
        // Не перетираем то, что оператор сейчас правит.
        if (draftRef.current == null) setDraft(s.settings.mapping)
      } catch {}
    }
    tick()
    const id = setInterval(tick, POLL_MS)
    return () => { stopped = true; clearInterval(id) }
  }, [call])

  const patch = async (body) => {
    setBusy('settings')
    try {
      const r = await call('/settings', body)
      setStatus((s) => (s ? { ...s, settings: r.settings } : s))
      setDraft(r.settings.mapping)
    } finally {
      setBusy('')
    }
  }

  if (!status) {
    return (
      <div style={{ border: '1px solid #444', padding: 12, marginTop: 12 }}>
        <h3>MIDI</h3>
        <div style={{ opacity: 0.7 }}>… запрос статуса с бэкенда</div>
      </div>
    )
  }

  const st = status.settings
  const inputs = status.ports?.inputs || []
  const outputs = status.ports?.outputs || []
  const mapping = draft || []
  const dirty = JSON.stringify(mapping) !== JSON.stringify(st.mapping)

  const updateRow = (idx, p) =>
    setDraft(mapping.map((r, i) => (i === idx ? { ...r, ...p } : r)))

  return (
    <div style={{ border: '1px solid #444', padding: 12, marginTop: 12 }}>
      <h3>MIDI (backend)</h3>

      <div style={{ fontSize: 13, lineHeight: 1.7 }}>
        <div>
          Порт:{' '}
          {status.inputOpen
            ? <b style={{ color: '#6d6' }}>🟢 {status.inputPort}</b>
            : <b style={{ color: '#d66' }}>🔴 закрыт</b>}
        </div>
        {status.lastError && (
          <div style={{ color: '#e88' }}>error: {status.lastError}</div>
        )}
        <div style={{ opacity: 0.75 }}>
          входы: {inputs.length ? inputs.join(' · ') : '— нет —'}
        </div>
        <div style={{ opacity: 0.75 }}>
          выходы: {outputs.length ? outputs.join(' · ') : '— нет —'}
        </div>
      </div>

      <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <label>
          <input
            type="checkbox"
            checked={!!st.enabled}
            onChange={(e) => patch({ enabled: e.target.checked })}
          />{' '}
          MIDI включён
        </label>
        <button onClick={() => call('/reopen').then(setStatus)}>переоткрыть порт</button>
      </div>

      <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <label style={{ fontSize: 13 }}>
          input{' '}
          <select value={st.inputName || ''} onChange={(e) => patch({ inputName: e.target.value })}>
            <option value="">— выбрать —</option>
            {!inputs.includes(st.inputName) && st.inputName && (
              <option value={st.inputName}>{st.inputName} (нет в системе)</option>
            )}
            {inputs.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label style={{ fontSize: 13 }}>
          output{' '}
          <select value={st.outputName || ''} onChange={(e) => patch({ outputName: e.target.value })}>
            <option value="">— выбрать —</option>
            {!outputs.includes(st.outputName) && st.outputName && (
              <option value={st.outputName}>{st.outputName} (нет в системе)</option>
            )}
            {outputs.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <button onClick={() => call('/test-note', {})}>
          test out {LEGACY_OUTPUT_NOTE}
        </button>
      </div>

      <div style={{ marginTop: 8 }}>
        <label>
          <input
            type="checkbox"
            checked={!!st.filterEnabled}
            onChange={(e) => patch({ filterEnabled: e.target.checked })}
          />{' '}
          фильтровать по каналу
        </label>
        <input
          type="number" min={1} max={16}
          value={st.filterChannel}
          onChange={(e) => patch({ filterChannel: Number(e.target.value) })}
          style={{ width: 56, marginLeft: 8 }}
        />
        <span style={{ marginLeft: 8, fontSize: 12, opacity: 0.7 }}>
          legacy: ch{LEGACY_CHANNEL}
        </span>
      </div>

      {/* Имитация ноты: тот же путь, что реальный вход (дедуп + фильтр + маппинг) */}
      <div style={{ marginTop: 12, padding: 8, border: '1px dashed #555', borderRadius: 6 }}>
        <strong>Имитация входящей ноты</strong>
        <div style={{ marginTop: 6, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="number" value={simNote}
            onChange={(e) => setSimNote(Number(e.target.value))}
            style={{ width: 70 }}
          />
          <span style={{ width: 46 }}>{noteName(simNote)}</span>
          <button onClick={() => call('/simulate', { note: simNote })}>отправить ▶</button>
          {[60, 69].map((n) => (
            <button key={n} onClick={() => call('/simulate', { note: n })}>
              {n} {n === 60 ? '(launch)' : '(minimizeAll)'}
            </button>
          ))}
        </div>
        <div style={{ marginTop: 4, fontSize: 12, opacity: 0.65 }}>
          Идёт через дедуп и фильтр канала, как настоящая нота. Нота 60 даёт эффект
          только в фазе final_hold — в остальных фазах попадёт в лог как launch_ignored.
        </div>
      </div>

      <div style={{ marginTop: 12 }}>
        <strong>Маппинг (канал, нота → действие):</strong>
        <button
          onClick={() => setDraft([...mapping, { channel: LEGACY_CHANNEL, note: 60, action: 'launch' }])}
          style={{ marginLeft: 8 }}
        >
          + строка
        </button>
        <button
          onClick={() => patch({ mapping })}
          disabled={!dirty || busy === 'settings'}
          style={{ marginLeft: 8, fontWeight: dirty ? 700 : 400 }}
        >
          {dirty ? 'сохранить ●' : 'сохранено'}
        </button>
        <button onClick={() => setDraft(st.mapping)} style={{ marginLeft: 8 }}>
          отменить правки
        </button>

        {mapping.map((r, idx) => (
          <div key={idx} style={{ display: 'flex', gap: 6, marginTop: 4, alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              type="text" placeholder="любой" style={{ width: 56 }}
              value={r.channel ?? ''}
              onChange={(e) => {
                const v = e.target.value.trim()
                updateRow(idx, { channel: v === '' ? null : Number(v) })
              }}
            />
            <input
              type="number" style={{ width: 64 }} value={r.note}
              onChange={(e) => updateRow(idx, { note: Number(e.target.value) })}
            />
            <span style={{ width: 46 }}>{noteName(r.note)}</span>
            <select value={r.action} onChange={(e) => updateRow(idx, { action: e.target.value })}>
              {MIDI_ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <button onClick={() => call('/simulate', { note: r.note, channel: r.channel ?? undefined })}>
              тест ▶
            </button>
            <button onClick={() => setDraft(mapping.filter((_, i) => i !== idx))}>✕</button>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 12 }}>
        <strong>Лог бэкенда:</strong>
        <div style={{ maxHeight: 220, overflow: 'auto', fontFamily: 'monospace', fontSize: 12 }}>
          {(status.log || []).map((l, i) => (
            <div key={i}>
              {new Date(l.at * 1000).toLocaleTimeString()} · {l.tag}
              {l.port ? ` · ${l.port}` : ''}
              {l.channel != null ? ` · ch${l.channel}` : ''}
              {l.note != null ? ` · ${l.note} ${noteName(l.note)}` : ''}
              {l.action ? ` · ${l.action}` : ''}
              {l.type ? ` → ${l.type}` : ''}
              {l.reason ? ` (${l.reason})` : ''}
              {l.error ? ` · ${l.error}` : ''}
            </div>
          ))}
          {!(status.log || []).length && <div style={{ opacity: 0.6 }}>— пусто —</div>}
        </div>
      </div>
    </div>
  )
}