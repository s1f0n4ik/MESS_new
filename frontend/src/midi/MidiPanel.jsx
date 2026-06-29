import { useEffect, useRef, useState } from 'react'
import { parseMidi, noteName } from './midiNote'
import { loadMapping, saveMapping, matchAction, MIDI_ACTIONS } from './midiMapping'

export function MidiPanel({ sendAction }) {
  const [access, setAccess] = useState('init') // init|ok|denied|insecure|unsupported
  const [inputs, setInputs] = useState([])
  const [log, setLog] = useState([])
  const [mapping, setMapping] = useState(loadMapping())
  const [filterChannel, setFilterChannel] = useState(null) // null = слушать все
  const learnRef = useRef(null) // индекс строки, которая «обучается»

  const pushLog = (entry) => {
    setLog((prev) => [{ ...entry, at: Date.now() }, ...prev].slice(0, 50))
  }

  // Центральный обработчик входящего MIDI.
  const onMidi = (msg) => {
    const m = parseMidi(msg.data)
    if (m.kind !== 'noteOn') return // диспетчеризуем только noteOn

    // Режим обучения: подставляем канал+ноту в редактируемую строку.
    if (learnRef.current != null) {
      const idx = learnRef.current
      setMapping((prev) => {
        const next = [...prev]
        if (next[idx]) next[idx] = { ...next[idx], channel: m.channel, note: m.note }
        saveMapping(next)
        return next
      })
      learnRef.current = null
      pushLog({ ...m, note_name: noteName(m.note), tag: 'learned' })
      return
    }

    // Опциональный фильтр канала (по умолчанию выключен).
    if (filterChannel != null && m.channel !== filterChannel) {
      pushLog({ ...m, note_name: noteName(m.note), tag: 'filtered' })
      return
    }

    pushLog({ ...m, note_name: noteName(m.note), tag: 'in' })
    dispatch(m.channel, m.note)
  }

  // Перевод ноты в действие через существующий sendAction.
  const dispatch = (channel, note) => {
    const hit = matchAction(mapping, channel, note)
    if (!hit) return
    sendAction(hit.action, hit.payload || {})
    pushLog({ channel, note, note_name: noteName(note), tag: `→ ${hit.action}` })
  }

  useEffect(() => {
    if (!navigator.requestMIDIAccess) { setAccess('unsupported'); return }
    if (!window.isSecureContext && location.hostname !== 'localhost') {
      setAccess('insecure'); return
    }
    let midi = null
    const attach = (ma) => {
      midi = ma
      setAccess('ok')
      const refresh = () => {
        const list = []
        ma.inputs.forEach((i) => list.push({ id: i.id, name: i.name, state: i.state }))
        setInputs(list)
        ma.inputs.forEach((i) => { i.onmidimessage = onMidi })
      }
      refresh()
      ma.onstatechange = refresh
    }
    navigator.requestMIDIAccess({ sysex: false }).then(attach, () => setAccess('denied'))
    return () => {
      if (midi) midi.inputs.forEach((i) => { i.onmidimessage = null })
    }
    // onMidi пересоздаётся при смене mapping/filter — переподписка нужна
  }, [mapping, filterChannel])

  // --- редактор маппинга ---
  const addRow = () => {
    const next = [...mapping, { channel: null, note: 60, action: 'launch' }]
    setMapping(next); saveMapping(next)
  }
  const updateRow = (idx, patch) => {
    const next = mapping.map((r, i) => (i === idx ? { ...r, ...patch } : r))
    setMapping(next); saveMapping(next)
  }
  const removeRow = (idx) => {
    const next = mapping.filter((_, i) => i !== idx)
    setMapping(next); saveMapping(next)
  }

  return (
    <div style={{ border: '1px solid #444', padding: 12, marginTop: 12 }}>
      <h3>MIDI</h3>
      <div>
        Статус:{' '}
        {access === 'ok' && '✅ доступен'}
        {access === 'denied' && '⛔ отказано (разрешите доступ к MIDI)'}
        {access === 'insecure' && '⚠️ небезопасный контекст — заходи через localhost'}
        {access === 'unsupported' && '❌ Web MIDI не поддерживается (нужен Chrome)'}
        {access === 'init' && '… запрос доступа'}
      </div>

      <div style={{ marginTop: 8 }}>
        <strong>Входы:</strong>{' '}
        {inputs.length ? inputs.map((i) => `${i.name} (${i.state})`).join(', ') : '— нет —'}
      </div>

      <div style={{ marginTop: 8 }}>
        <label>
          <input
            type="checkbox"
            checked={filterChannel != null}
            onChange={(e) => setFilterChannel(e.target.checked ? 1 : null)}
          />{' '}
          фильтровать по каналу
        </label>
        {filterChannel != null && (
          <input
            type="number" min={1} max={16} value={filterChannel}
            onChange={(e) => setFilterChannel(Number(e.target.value))}
            style={{ width: 56, marginLeft: 8 }}
          />
        )}
      </div>

      <div style={{ marginTop: 12 }}>
        <strong>Маппинг (канал, нота → действие):</strong>
        <button onClick={addRow} style={{ marginLeft: 8 }}>+ строка</button>
        {mapping.map((r, idx) => (
          <div key={idx} style={{ display: 'flex', gap: 6, marginTop: 4, alignItems: 'center' }}>
            <input
              type="text" placeholder="любой"
              value={r.channel ?? ''} style={{ width: 56 }}
              onChange={(e) => {
                const v = e.target.value.trim()
                updateRow(idx, { channel: v === '' ? null : Number(v) })
              }}
            />
            <input
              type="number" value={r.note} style={{ width: 64 }}
              onChange={(e) => updateRow(idx, { note: Number(e.target.value) })}
            />
            <span style={{ width: 48 }}>{noteName(r.note)}</span>
            <select value={r.action} onChange={(e) => updateRow(idx, { action: e.target.value })}>
              {MIDI_ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <button onClick={() => { learnRef.current = idx }}>обучить</button>
            <button onClick={() => dispatch(r.channel ?? 1, r.note)}>тест ▶</button>
            <button onClick={() => removeRow(idx)}>✕</button>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 12 }}>
        <strong>Симуляторы (без живого MIDI):</strong>{' '}
        {MIDI_ACTIONS.map((a) => (
          <button key={a} onClick={() => { sendAction(a); pushLog({ tag: `sim → ${a}` }) }}
            style={{ marginLeft: 6 }}>{a}</button>
        ))}
      </div>

      <div style={{ marginTop: 12 }}>
        <strong>Лог:</strong>
        <div style={{ maxHeight: 180, overflow: 'auto', fontFamily: 'monospace', fontSize: 12 }}>
          {log.map((l, i) => (
            <div key={i}>
              {new Date(l.at).toLocaleTimeString()} · {l.tag}
              {l.channel != null && ` · ch${l.channel}`}
              {l.note != null && ` · ${l.note} ${l.note_name || ''}`}
              {l.velocity != null && ` · v${l.velocity}`}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}