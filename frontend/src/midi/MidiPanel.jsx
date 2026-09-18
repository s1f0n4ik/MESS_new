import { useCallback, useEffect, useRef, useState } from 'react'
import { noteName } from './midiNote'
import { MIDI_ACTIONS, LEGACY_CHANNEL, LEGACY_OUTPUT_NOTE } from './midiMapping'
import { apiUrl } from '../net/urls'

const POLL_MS = 1000

function fmtTimeMs(ts) {
  const d = new Date(ts * 1000)
  return `${d.toLocaleTimeString()}.${String(d.getMilliseconds()).padStart(3, '0')}`
}

function fmtRaw(e) {
  const parts = [e.port || '?', e.type]
  if (e.channel != null) parts.push(`ch${e.channel}`)
  if (e.note != null) parts.push(`${e.note} ${noteName(e.note)}`)
  if (e.velocity != null) parts.push(`vel ${e.velocity}`)
  if (e.control != null) parts.push(`cc${e.control}=${e.value}`)
  if (e.program != null) parts.push(`pgm ${e.program}`)
  if (e.pitch != null) parts.push(`pitch ${e.pitch}`)
  if (e.len != null) parts.push(`${e.len} байт`)
  return parts.join(' · ')
}

export function MidiPanel({ serverHost }) {
  const [status, setStatus] = useState(null)
  const [draft, setDraft] = useState(null)   // локальные правки маппинга
  const [busy, setBusy] = useState('')
  const [simNote, setSimNote] = useState(60)
  const [now, setNow] = useState(Date.now() / 1000)
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

  const refresh = useCallback(() => call('/status').then(setStatus).catch(() => {}), [call])

  // Поллинг статуса. WS не используем: MIDI-лог не часть игрового состояния,
  // незачем гнать его всем четырём ПК в каждом broadcast.
  // Скрытая вкладка поллинг останавливает — иначе админка забивает
  // лог координатора 60 запросами в минуту.
  useEffect(() => {
    let stopped = false
    let id = null

    const tick = async () => {
      if (document.hidden) return
      try {
        const s = await call('/status')
        if (stopped) return
        setStatus(s)
        setNow(Date.now() / 1000)
        // Не перетираем то, что оператор сейчас правит.
        if (draftRef.current == null) setDraft(s.settings.mapping)
      } catch {}
    }

    const start = () => {
      if (id) return
      tick()
      id = setInterval(tick, POLL_MS)
    }
    const stop = () => { clearInterval(id); id = null }

    const onVis = () => (document.hidden ? stop() : start())
    document.addEventListener('visibilitychange', onVis)
    start()

    return () => {
      stopped = true
      stop()
      document.removeEventListener('visibilitychange', onVis)
    }
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

  // Режим ноутбуков: MIDI сознательно выключен, это не ошибка.
  const midiOff = status.midiAllowed === false
  // Старый exe без монитора — подскажем, а не будем падать на undefined.
  const monitorSupported = 'rawLog' in status

  const st = status.settings
  const inputs = status.ports?.inputs || []
  const outputs = status.ports?.outputs || []
  const mapping = draft || []
  const dirty = JSON.stringify(mapping) !== JSON.stringify(st.mapping)

  const updateRow = (idx, p) =>
    setDraft(mapping.map((r, i) => (i === idx ? { ...r, ...p } : r)))

  const rawLog = status.rawLog || []
  const ago = status.lastMessageAt ? Math.max(0, Math.round(now - status.lastMessageAt)) : null
  const fresh = ago != null && ago <= 2

  return (
    <div style={{ border: '1px solid #444', padding: 12, marginTop: 12, opacity: midiOff ? 0.85 : 1 }}>
      <h3>MIDI (backend)</h3>

      {midiOff && (
        <div
          style={{
            background: '#332',
            border: '1px solid #885',
            color: '#dc6',
            padding: '6px 10px',
            marginBottom: 8,
            fontSize: 13,
          }}
        >
          MIDI выключен: режим «Ноутбуки». Порт не открывается, входящие ноты
          игнорируются. Переключить режим — панель «Режим инсталляции».
        </div>
      )}

      <div style={{ fontSize: 13, lineHeight: 1.7 }}>
        <div>
          Порт:{' '}
          {midiOff
            ? <b style={{ color: '#dc6' }}>⏸ выключен режимом</b>
            : status.inputOpen
              ? <b style={{ color: '#6d6' }}>🟢 {status.inputPort}</b>
              : <b style={{ color: '#d66' }}>🔴 закрыт</b>}
        </div>
        {status.lastError && !midiOff && (
          <div style={{ color: '#e88' }}>error: {status.lastError}</div>
        )}
        <div style={{ opacity: 0.75 }}>
          входы: {inputs.length ? inputs.join(' · ') : '— нет —'}
        </div>
        <div style={{ opacity: 0.75 }}>
          выходы: {outputs.length ? outputs.join(' · ') : '— нет —'}
        </div>
      </div>

      {/* ---------- Монитор входящих ---------- */}
      <div
        style={{
          marginTop: 10, padding: 8, borderRadius: 6,
          border: `1px solid ${fresh ? '#4a4' : '#555'}`,
          background: fresh ? '#1a2a1a' : 'transparent',
          transition: 'background .3s, border-color .3s',
        }}
      >
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <strong>
            <span style={{ color: fresh ? '#6d6' : '#666' }}>●</span> Монитор входящих
          </strong>
          {monitorSupported ? (
            <>
              <span style={{ fontSize: 13 }}>
                сообщений: <b>{status.msgCount}</b>
                {status.noisyCount ? (
                  <span style={{ opacity: 0.6 }}> (+{status.noisyCount} служебных: clock и т.п.)</span>
                ) : null}
              </span>
              <span style={{ fontSize: 13 }}>
                {ago == null
                  ? <span style={{ opacity: 0.6 }}>ничего не приходило</span>
                  : <>последнее: <b>{ago} с назад</b> с «{status.lastMessagePort}»</>}
              </span>
              <label style={{ fontSize: 13, marginLeft: 'auto' }}>
                <input
                  type="checkbox"
                  checked={!!status.monitorAll}
                  onChange={(e) => call('/monitor', { enabled: e.target.checked }).then(refresh)}
                />{' '}
                слушать все входы
              </label>
              <button onClick={() => call('/clear-log', {}).then(refresh)}>очистить</button>
            </>
          ) : (
            <span style={{ color: '#e88', fontSize: 13 }}>
              бэкенд без монитора — пересобери postcards-backend.exe
            </span>
          )}
        </div>

        {monitorSupported && status.monitorAll && (
          <div style={{ fontSize: 12, opacity: 0.7, marginTop: 4 }}>
            дополнительно слушаю: {status.monitorPorts?.length ? status.monitorPorts.join(' · ') : '— других входов нет —'}.
            Ноты с них только показываются (курсивом), исполняется только основной порт.
          </div>
        )}

        {monitorSupported && (
          <div style={{ maxHeight: 200, overflow: 'auto', fontFamily: 'monospace', fontSize: 12, marginTop: 6 }}>
            {rawLog.map((e, i) => {
              const isNoteOn = e.type === 'note_on' && e.velocity > 0
              return (
                <div
                  key={`${e.at}-${i}`}
                  style={{
                    fontStyle: e.monitor || e.port === 'simulate' ? 'italic' : 'normal',
                    opacity: e.monitor ? 0.7 : 1,
                    color: isNoteOn ? '#dfd' : '#bbb',
                  }}
                >
                  {fmtTimeMs(e.at)} · {fmtRaw(e)}
                  {e.monitor ? ' · [только монитор]' : ''}
                </div>
              )
            })}
            {!rawLog.length && (
              <div style={{ opacity: 0.6 }}>
                — пусто — {status.inputOpen
                  ? 'порт открыт, но с него ничего не пришло. Проверь сессию rtpMIDI и выход трека в Reaper.'
                  : 'порт закрыт.'}
              </div>
            )}
          </div>
        )}
      </div>

      <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <label>
          <input
            type="checkbox"
            checked={!!st.enabled}
            disabled={midiOff}
            onChange={(e) => patch({ enabled: e.target.checked })}
          />{' '}
          MIDI включён
        </label>
        <button disabled={midiOff} onClick={() => call('/reopen').then((r) => setStatus(r.status || r))}>
          переоткрыть порт
        </button>
      </div>

      <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <label style={{ fontSize: 13 }}>
          input{' '}
          <select
            value={st.inputName || ''}
            disabled={midiOff}
            onChange={(e) => patch({ inputName: e.target.value })}
          >
            <option value="">— выбрать —</option>
            {!inputs.includes(st.inputName) && st.inputName && (
              <option value={st.inputName}>{st.inputName} (нет в системе)</option>
            )}
            {inputs.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label style={{ fontSize: 13 }}>
          output{' '}
          <select
            value={st.outputName || ''}
            disabled={midiOff}
            onChange={(e) => patch({ outputName: e.target.value })}
          >
            <option value="">— выбрать —</option>
            {!outputs.includes(st.outputName) && st.outputName && (
              <option value={st.outputName}>{st.outputName} (нет в системе)</option>
            )}
            {outputs.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <button disabled={midiOff} onClick={() => call('/test-note', {})}>
          test out {LEGACY_OUTPUT_NOTE}
        </button>
      </div>

      <div style={{ marginTop: 8 }}>
        <label>
          <input
            type="checkbox"
            checked={!!st.filterEnabled}
            disabled={midiOff}
            onChange={(e) => patch({ filterEnabled: e.target.checked })}
          />{' '}
          фильтровать по каналу
        </label>
        <input
          type="number" min={1} max={16}
          value={st.filterChannel}
          disabled={midiOff}
          onChange={(e) => patch({ filterChannel: Number(e.target.value) })}
          style={{ width: 56, marginLeft: 8 }}
        />
        <span style={{ marginLeft: 8, fontSize: 12, opacity: 0.7 }}>
          legacy: ch{LEGACY_CHANNEL}
        </span>
      </div>

      {/* Имитация ноты: тот же путь, что реальный вход (монитор + дедуп + фильтр + маппинг).
          В laptop-режиме нота дойдёт до _handle и отсеется как ignored_laptop_mode —
          кнопки не блокируем, это удобный способ убедиться, что гейт работает. */}
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
          {midiOff && ' В режиме «Ноутбуки» любая нота отсеется как ignored_laptop_mode.'}
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
        <strong>Лог решений бэкенда:</strong>
        <div style={{ maxHeight: 220, overflow: 'auto', fontFamily: 'monospace', fontSize: 12 }}>
          {(status.log || []).map((l, i) => (
            <div key={i}>
              {fmtTimeMs(l.at)} · {l.tag}
              {l.port ? ` · ${l.port}` : ''}
              {l.channel != null ? ` · ch${l.channel}` : ''}
              {l.note != null ? ` · ${l.note} ${noteName(l.note)}` : ''}
              {l.action ? ` · ${l.action}` : ''}
              {l.type ? ` → ${l.type}` : ''}
              {l.reason ? ` (${l.reason})` : ''}
              {l.error ? ` · ${l.error}` : ''}
              {l.available ? ` · доступны: ${l.available.join(', ') || 'нет'}` : ''}
            </div>
          ))}
          {!(status.log || []).length && <div style={{ opacity: 0.6 }}>— пусто —</div>}
        </div>
      </div>
    </div>
  )
}