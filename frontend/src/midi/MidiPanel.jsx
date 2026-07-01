import { useEffect, useMemo, useRef, useState } from 'react'
import { parseMidi, noteName } from './midiNote'
import {
  loadMapping,
  saveMapping,
  matchAction,
  MIDI_ACTIONS,
  LEGACY_CHANNEL,
  LEGACY_OUTPUT_NOTE,
  LEGACY_OUTPUT_VELOCITY,
  LEGACY_OUTPUT_DURATION_MS,
  resetMappingToLegacy,
  actionToSendSpec,
} from './midiMapping'

const INPUT_KEY = 'postcards_midi_input_v1'
const OUTPUT_KEY = 'postcards_midi_output_v1'
const FILTER_ENABLED_KEY = 'postcards_midi_filter_enabled_v1'
const FILTER_CHANNEL_KEY = 'postcards_midi_filter_channel_v1'

const DEDUPE_WINDOW_MS = 180

function loadBool(key, fallback = false) {
  try {
    const v = localStorage.getItem(key)
    if (v == null) return fallback
    return v === '1'
  } catch {
    return fallback
  }
}

function saveBool(key, value) {
  try {
    localStorage.setItem(key, value ? '1' : '0')
  } catch {}
}

function loadNum(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    if (raw == null || raw === '') return fallback
    const n = Number(raw)
    return Number.isFinite(n) ? n : fallback
  } catch {
    return fallback
  }
}

function saveNum(key, value) {
  try {
    localStorage.setItem(key, String(value))
  } catch {}
}

function loadText(key, fallback = '') {
  try {
    return localStorage.getItem(key) || fallback
  } catch {
    return fallback
  }
}

function saveText(key, value) {
  try {
    localStorage.setItem(key, value || '')
  } catch {}
}

function preferPc10(list) {
  if (!list.length) return ''
  const exact = list.find((x) => x.name === 'PC-10' && x.state === 'connected')
  if (exact) return exact.id
  const fuzzy = list.find((x) => (x.name || '').toLowerCase().includes('pc-10') && x.state === 'connected')
  if (fuzzy) return fuzzy.id
  const firstConnected = list.find((x) => x.state === 'connected')
  return firstConnected?.id || list[0]?.id || ''
}

function sendMidiNote(output, channel, note, velocity, durationMs) {
  if (!output) return false
  const statusOn = 0x90 + (channel - 1)
  const statusOff = 0x80 + (channel - 1)
  try {
    output.send([statusOn, note, velocity])
    window.setTimeout(() => {
      try {
        output.send([statusOff, note, 0])
      } catch {}
    }, durationMs)
    return true
  } catch {
    return false
  }
}

export function MidiPanel({ sendAction }) {
  const [access, setAccess] = useState('init')
  const [inputs, setInputs] = useState([])
  const [outputs, setOutputs] = useState([])
  const [selectedInputId, setSelectedInputId] = useState(() => loadText(INPUT_KEY, ''))
  const [selectedOutputId, setSelectedOutputId] = useState(() => loadText(OUTPUT_KEY, ''))
  const [log, setLog] = useState([])
  const [mapping, setMapping] = useState(loadMapping())
  const [filterEnabled, setFilterEnabled] = useState(() => loadBool(FILTER_ENABLED_KEY, true))
  const [filterChannel, setFilterChannel] = useState(() => loadNum(FILTER_CHANNEL_KEY, LEGACY_CHANNEL))

  const midiRef = useRef(null)
  const learnRef = useRef(null)
  const dedupeRef = useRef(new Map())

  const pushLog = (entry) => {
    setLog((prev) => [{ ...entry, at: Date.now() }, ...prev].slice(0, 80))
  }

  const selectedInput = useMemo(
    () => inputs.find((i) => i.id === selectedInputId) || null,
    [inputs, selectedInputId]
  )

  const selectedOutput = useMemo(
    () => outputs.find((o) => o.id === selectedOutputId) || null,
    [outputs, selectedOutputId]
  )

  const dispatchAction = (action, channel, note) => {
    const spec = actionToSendSpec(action)
    if (!spec) {
      pushLog({ tag: `no-dispatch:${action}`, channel, note, note_name: noteName(note) })
      return
    }
    sendAction(spec.type, spec.payload || {})
    pushLog({ tag: `→ ${spec.type}`, channel, note, note_name: noteName(note) })
  }

  const onMidiRef = useRef(null)
  onMidiRef.current = (msg, inputMeta) => {
    const m = parseMidi(msg.data)
    if (m.kind !== 'noteOn') return

    const inputName = inputMeta?.name || ''
    const dedupeKey = `${inputMeta?.id || 'unknown'}:${m.channel}:${m.note}`
    const lastAt = dedupeRef.current.get(dedupeKey) || 0
    const now = Date.now()
    if (now - lastAt < DEDUPE_WINDOW_MS) {
      pushLog({ ...m, inputName, note_name: noteName(m.note), tag: 'deduped' })
      return
    }
    dedupeRef.current.set(dedupeKey, now)

    if (learnRef.current != null) {
      const idx = learnRef.current
      setMapping((prev) => {
        const next = [...prev]
        if (next[idx]) next[idx] = { ...next[idx], channel: m.channel, note: m.note }
        saveMapping(next)
        return next
      })
      learnRef.current = null
      pushLog({ ...m, inputName, note_name: noteName(m.note), tag: 'learned' })
      return
    }

    if (filterEnabled && m.channel !== filterChannel) {
      pushLog({ ...m, inputName, note_name: noteName(m.note), tag: 'filtered' })
      return
    }

    pushLog({ ...m, inputName, note_name: noteName(m.note), tag: 'in' })

    const hit = matchAction(mapping, m.channel, m.note)
    if (!hit) {
      pushLog({ ...m, inputName, note_name: noteName(m.note), tag: 'unmapped' })
      return
    }

    dispatchAction(hit.action, m.channel, m.note)
  }

  useEffect(() => {
    if (!navigator.requestMIDIAccess) {
      setAccess('unsupported')
      return
    }
    if (!window.isSecureContext && location.hostname !== 'localhost') {
      setAccess('insecure')
      return
    }

    let cancelled = false

    const attachSelectedInput = (ma, inputId) => {
      ma.inputs.forEach((input) => {
        input.onmidimessage = null
      })
      if (!inputId) return
      const input = ma.inputs.get(inputId)
      if (!input) return
      input.onmidimessage = (msg) => onMidiRef.current?.(msg, { id: input.id, name: input.name })
    }

    const refresh = (ma) => {
      const nextInputs = []
      const nextOutputs = []
      ma.inputs.forEach((i) => nextInputs.push({ id: i.id, name: i.name, state: i.state }))
      ma.outputs.forEach((o) => nextOutputs.push({ id: o.id, name: o.name, state: o.state }))
      setInputs(nextInputs)
      setOutputs(nextOutputs)

      let nextInputId = selectedInputId
      if (!nextInputId || !nextInputs.some((x) => x.id === nextInputId)) {
        nextInputId = preferPc10(nextInputs)
        if (nextInputId !== selectedInputId) {
          setSelectedInputId(nextInputId)
          saveText(INPUT_KEY, nextInputId)
        }
      }

      let nextOutputId = selectedOutputId
      if (!nextOutputId || !nextOutputs.some((x) => x.id === nextOutputId)) {
        nextOutputId = preferPc10(nextOutputs)
        if (nextOutputId !== selectedOutputId) {
          setSelectedOutputId(nextOutputId)
          saveText(OUTPUT_KEY, nextOutputId)
        }
      }

      attachSelectedInput(ma, nextInputId)
    }

    navigator.requestMIDIAccess({ sysex: false }).then(
      (ma) => {
        if (cancelled) return
        midiRef.current = ma
        setAccess('ok')
        refresh(ma)
        ma.onstatechange = () => refresh(ma)
      },
      () => setAccess('denied')
    )

    return () => {
      cancelled = true
      const ma = midiRef.current
      if (ma) {
        ma.inputs.forEach((input) => {
          input.onmidimessage = null
        })
        ma.onstatechange = null
      }
    }
  }, [selectedInputId, selectedOutputId, filterEnabled, filterChannel, mapping])

  const updateRow = (idx, patch) => {
    const next = mapping.map((row, i) => (i === idx ? { ...row, ...patch } : row))
    setMapping(next)
    saveMapping(next)
  }

  const addRow = () => {
    const next = [...mapping, { channel: LEGACY_CHANNEL, note: 60, action: 'launch' }]
    setMapping(next)
    saveMapping(next)
  }

  const removeRow = (idx) => {
    const next = mapping.filter((_, i) => i !== idx)
    setMapping(next)
    saveMapping(next)
  }

  const resetLegacy = () => {
    const next = resetMappingToLegacy()
    setMapping(next)
    pushLog({ tag: 'mapping_reset_legacy' })
  }

  const testOutput = () => {
    const ma = midiRef.current
    if (!ma || !selectedOutputId) {
      pushLog({ tag: 'output_missing' })
      return
    }
    const out = ma.outputs.get(selectedOutputId)
    const ok = sendMidiNote(out, LEGACY_CHANNEL, LEGACY_OUTPUT_NOTE, LEGACY_OUTPUT_VELOCITY, LEGACY_OUTPUT_DURATION_MS)
    pushLog({
      tag: ok ? 'output_test_sent' : 'output_test_failed',
      channel: LEGACY_CHANNEL,
      note: LEGACY_OUTPUT_NOTE,
      note_name: noteName(LEGACY_OUTPUT_NOTE),
      velocity: LEGACY_OUTPUT_VELOCITY,
    })
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

      <div style={{ marginTop: 6 }}>
        <label>
          input:{' '}
          <select
            value={selectedInputId}
            onChange={(e) => {
              const v = e.target.value
              setSelectedInputId(v)
              saveText(INPUT_KEY, v)
            }}
          >
            <option value="">— выбрать —</option>
            {inputs.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name} ({i.state})
              </option>
            ))}
          </select>
        </label>
        <span style={{ marginLeft: 8, fontSize: 12, opacity: 0.8 }}>
          active: {selectedInput?.name || '—'}
        </span>
      </div>

      <div style={{ marginTop: 6 }}>
        <label>
          output:{' '}
          <select
            value={selectedOutputId}
            onChange={(e) => {
              const v = e.target.value
              setSelectedOutputId(v)
              saveText(OUTPUT_KEY, v)
            }}
          >
            <option value="">— выбрать —</option>
            {outputs.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name} ({o.state})
              </option>
            ))}
          </select>
        </label>
        <button onClick={testOutput} style={{ marginLeft: 8 }}>
          test output 72
        </button>
        <span style={{ marginLeft: 8, fontSize: 12, opacity: 0.8 }}>
          active: {selectedOutput?.name || '—'}
        </span>
      </div>

      <div style={{ marginTop: 8 }}>
        <label>
          <input
            type="checkbox"
            checked={filterEnabled}
            onChange={(e) => {
              setFilterEnabled(e.target.checked)
              saveBool(FILTER_ENABLED_KEY, e.target.checked)
            }}
          />{' '}
          фильтровать по каналу
        </label>
        <input
          type="number"
          min={1}
          max={16}
          value={filterChannel}
          onChange={(e) => {
            const v = Number(e.target.value)
            setFilterChannel(v)
            saveNum(FILTER_CHANNEL_KEY, v)
          }}
          style={{ width: 56, marginLeft: 8 }}
        />
        <span style={{ marginLeft: 8, fontSize: 12, opacity: 0.8 }}>
          legacy: ch{LEGACY_CHANNEL}
        </span>
      </div>

      <div style={{ marginTop: 12 }}>
        <strong>Маппинг (канал, нота → действие):</strong>
        <button onClick={addRow} style={{ marginLeft: 8 }}>+ строка</button>
        <button onClick={resetLegacy} style={{ marginLeft: 8 }}>reset legacy</button>

        {mapping.map((r, idx) => (
          <div key={idx} style={{ display: 'flex', gap: 6, marginTop: 4, alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              type="text"
              placeholder="любой"
              value={r.channel ?? ''}
              style={{ width: 56 }}
              onChange={(e) => {
                const v = e.target.value.trim()
                updateRow(idx, { channel: v === '' ? null : Number(v) })
              }}
            />
            <input
              type="number"
              value={r.note}
              style={{ width: 64 }}
              onChange={(e) => updateRow(idx, { note: Number(e.target.value) })}
            />
            <span style={{ width: 52 }}>{noteName(r.note)}</span>
            <select value={r.action} onChange={(e) => updateRow(idx, { action: e.target.value })}>
              {MIDI_ACTIONS.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
            <button onClick={() => { learnRef.current = idx }}>обучить</button>
            <button onClick={() => dispatchAction(r.action, r.channel ?? LEGACY_CHANNEL, r.note)}>тест ▶</button>
            <button onClick={() => removeRow(idx)}>✕</button>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 12 }}>
        <strong>Симуляторы:</strong>{' '}
        {MIDI_ACTIONS.map((a) => (
          <button
            key={a}
            onClick={() => {
              dispatchAction(a, LEGACY_CHANNEL, 0)
              pushLog({ tag: `sim → ${a}` })
            }}
            style={{ marginLeft: 6, marginTop: 4 }}
          >
            {a}
          </button>
        ))}
      </div>

      <div style={{ marginTop: 12 }}>
        <strong>Лог:</strong>
        <div style={{ maxHeight: 220, overflow: 'auto', fontFamily: 'monospace', fontSize: 12 }}>
          {log.map((l, i) => (
            <div key={i}>
              {new Date(l.at).toLocaleTimeString()} · {l.tag}
              {l.inputName ? ` · ${l.inputName}` : ''}
              {l.channel != null ? ` · ch${l.channel}` : ''}
              {l.note != null ? ` · ${l.note} ${l.note_name || ''}` : ''}
              {l.velocity != null ? ` · v${l.velocity}` : ''}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}