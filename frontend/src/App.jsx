import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import { PdfWindowLayer } from './pdf/PdfWindowLayer'
import { getRole, setRole, ROLES_LIST } from './role/role'
import { MidiPanel } from './midi/MidiPanel'
import { loadLocalSettings, saveLocalSettings } from './settings/localSettings'
import { CardScene } from './CardScene'
import { audioEngine } from './audio/audioEngine'

const role = getRole()
const isController = role === 'pc1'

function normalizeServerHost(value) {
  return String(value || '').trim()
}

function httpBase(serverHost) {
  const host = normalizeServerHost(serverHost)
  if (!host) return ''
  const proto = window.location.protocol
  if (/^https?:\/\//i.test(host)) return host
  return `${proto}//${host}`
}

function wsUrl(serverHost) {
  const host = normalizeServerHost(serverHost)
  if (!host) {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    return `${proto}://${window.location.host}/ws`
  }
  if (/^wss?:\/\//i.test(host)) return `${host.replace(/\/+$/, '')}/ws`
  if (/^https?:\/\//i.test(host)) {
    const base = new URL(host)
    base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${base.toString().replace(/\/+$/, '')}/ws`
  }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${host}/ws`
}

function apiUrl(path, serverHost) {
  const base = httpBase(serverHost)
  return `${base}${path}`
}

function agoLabel(lastSeenAt) {
  if (!lastSeenAt) return ''
  const sec = Math.max(0, Math.round(Date.now() / 1000 - lastSeenAt))
  return `${sec}s`
}

export default function App() {
  const [state, setState] = useState(null)
  const [connected, setConnected] = useState(false)
  const [, forceTick] = useState(0) // чтобы «Ns назад» обновлялось
  const wsRef = useRef(null)
  const prevClicksRef = useRef(0)

  const initialLocalSettings = loadLocalSettings()
  const [localSettings, setLocalSettings] = useState({
    serverHost: initialLocalSettings.serverHost || '',
    audioEnabled: initialLocalSettings.audioEnabled !== false, // по умолчанию вкл
  })

  const [globalSettings, setGlobalSettings] = useState({
    returnDelaySeconds: '',
    dwellSeconds: '',
  })
  const [settingsSaving, setSettingsSaving] = useState(false)

  // ==== Overlay-меню: только при ?admin=1, тоггл по M / Ь, закрытие по Esc ====
  const adminAllowed = new URLSearchParams(window.location.search).has('admin')
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    if (!adminAllowed) return
    const onKey = (e) => {
      if (e.key === 'm' || e.key === 'M' || e.key === 'ь' || e.key === 'Ь') {
        setMenuOpen((v) => !v)
      }
      if (e.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [adminAllowed])

  // тик раз в секунду — освежаем relative-время в Devices
  useEffect(() => {
    const id = setInterval(() => forceTick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [])

  // Инициализация аудио-движка: разблокировка автоплея + keep-alive.
  useEffect(() => {
    audioEngine.setEnabled(localSettings.audioEnabled !== false)
    audioEngine.bindUnlock()
    audioEngine.startKeepAliveLoop()
    return () => audioEngine.stopKeepAliveLoop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Звук клика: играем при приросте счётчика МОЕЙ роли.
  // Счётчик растёт только на click_card, поэтому reason не нужен.
  useEffect(() => {
    const next = Number(state?.clicksByRole?.[role] || 0)
    const prev = prevClicksRef.current
    if (next > prev) {
      audioEngine.play(role, next) // клампится до 16 внутри движка
    }
    prevClicksRef.current = next
  }, [state?.clicksByRole])

  const loadGlobalSettings = async () => {
    try {
      const res = await fetch(apiUrl('/api/settings/global', localSettings.serverHost))
      const data = await res.json()
      setGlobalSettings({
        returnDelaySeconds: String(data?.returnDelaySeconds ?? ''),
        dwellSeconds: String(data?.dwellSeconds ?? ''),
      })
    } catch {}
  }

  useEffect(() => {
    loadGlobalSettings()
  }, [localSettings.serverHost])

  useEffect(() => {
    let stopped = false
    let pingTimer = null
    let reconnectTimer = null

    const clearTimers = () => {
      if (pingTimer) { clearInterval(pingTimer); pingTimer = null }
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    }

    const connect = () => {
      if (stopped) return
      const ws = new WebSocket(wsUrl(localSettings.serverHost))
      wsRef.current = ws

      ws.onopen = () => {
        if (stopped) { try { ws.close() } catch {} return }
        setConnected(true)
        ws.send(JSON.stringify({
          type: 'identify',
          payload: { role, hostName: window.location.hostname },
        }))
        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }))
          }
        }, 10000)
      }

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg?.type === 'state' && msg?.payload) setState(msg.payload)
        } catch {}
      }

      ws.onclose = () => {
        setConnected(false)
        if (pingTimer) { clearInterval(pingTimer); pingTimer = null }
        if (!stopped) reconnectTimer = setTimeout(connect, 1500)
      }

      ws.onerror = () => {}
    }

    connect()

    return () => {
      stopped = true
      clearTimers()
      const ws = wsRef.current
      if (ws) {
        ws.onopen = ws.onmessage = ws.onerror = null
        ws.onclose = null
        try { ws.close() } catch {}
      }
      wsRef.current = null
    }
  }, [localSettings.serverHost])

  const flips = useMemo(() => state?.flippedCardsByRole?.[role] || {}, [state])

  const sendAction = (type, payload = {}) => {
    const ws = wsRef.current
    const body = { type, payload: { role, ...payload } }
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'action', payload: body }))
    } else {
      fetch(apiUrl('/api/action', localSettings.serverHost), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    }
  }

  const saveGlobalSettings = async () => {
    setSettingsSaving(true)
    try {
      await fetch(apiUrl('/api/settings/global', localSettings.serverHost), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          returnDelaySeconds: Number(globalSettings.returnDelaySeconds || 0),
          dwellSeconds: Number(globalSettings.dwellSeconds || 0),
        }),
      })
    } finally {
      setSettingsSaving(false)
    }
  }

  const saveLocalAndReconnect = () => {
    const next = saveLocalSettings({
      serverHost: localSettings.serverHost,
      audioEnabled: localSettings.audioEnabled,
    })
    setLocalSettings({
      serverHost: next.serverHost || '',
      audioEnabled: next.audioEnabled !== false,
    })
  }

  const openPdfManual = () => {
    sendAction('open_role_popup', { role })
  }

  const closePdfManual = () => {
    sendAction('close_role_popup', { role })
  }

  const devices = state?.connectedDevices || {}

  return (
    <div className="app">
      {/* ===== Сцена всегда на фоне (zIndex: 0) ===== */}
      <div style={{ position: 'fixed', inset: 0, zIndex: 0 }}>
        <CardScene
          onCardClick={(cardIndex) => sendAction('click_card', { role, cardIndex })}
        />
      </div>

      {/* PDF-слой — на всех ролях, это и есть «дисплей» */}
      <PdfWindowLayer state={state} myRole={role} />

      {/* ===== Служебное меню — оверлей поверх сцены =====
          Только при ?admin=1 и по хоткею M / Ь (Esc — закрыть). */}
      {adminAllowed && menuOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 100,
            overflow: 'auto',
            background: 'rgba(20,20,20,0.95)',
            color: '#eee',
            padding: 20,
          }}
        >
          <h1>
            Postcards — {isController ? 'CONTROLLER (pc1)' : `DISPLAY (${role})`}
          </h1>

          {/* Диагностическая шапка */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span>role: <b>{role}</b></span>
            <label style={{ fontSize: 13 }}>
              сменить:{' '}
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                {ROLES_LIST.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </label>
            <span>ws: {connected ? '🟢 online' : '🔴 offline'}</span>
          </div>

          <div style={{ margin: '8px 0', fontSize: 14 }}>
            Devices:{' '}
            {ROLES_LIST.map((r) => {
              const d = devices[r]
              const mark = d ? (d.online ? '🟢' : '⚪') : '·'
              const ago = d ? agoLabel(d.lastSeenAt) : ''
              return (
                <span key={r} style={{ marginRight: 12 }}>
                  {mark} {r}{ago ? ` (${ago})` : ''}
                </span>
              )
            })}
          </div>

          {/* Тумблер звука — доступен на всех ролях */}
          <label style={{ fontSize: 13, display: 'block', margin: '8px 0' }}>
            <input
              type="checkbox"
              checked={localSettings.audioEnabled !== false}
              onChange={(e) => {
                const audioEnabled = e.target.checked
                const next = saveLocalSettings({
                  serverHost: localSettings.serverHost,
                  audioEnabled,
                })
                setLocalSettings((s) => ({ ...s, audioEnabled: next.audioEnabled !== false }))
                audioEngine.setEnabled(audioEnabled)
              }}
            />{' '}
            Звук кликов
          </label>

          {/* ================= CONTROLLER-ONLY (pc1) ================= */}
          {isController && (
            <>
              <div>stateVersion: {state?.stateVersion ?? '...'}</div>
              <div>Clicks ({role}): {state?.clicksByRole?.[role] ?? 0}</div>
              <div>
                Scenario: {state?.scenario?.active ? 'active' : 'idle'} · currentRole:{' '}
                {state?.scenario?.currentRole || '-'}
              </div>

              <div className="toolbar">
                <button onClick={openPdfManual}>Open PDF (local)</button>
                <button onClick={closePdfManual}>Close PDF (local)</button>
                <button onClick={() => sendAction('launch')}>Launch (advance wave)</button>
                <button onClick={() => sendAction('toggle_force_open_all')}>Force open all</button>
                <button onClick={() => sendAction('reset_scenario')}>Reset scenario</button>
                <button onClick={() => sendAction('hard_reset')}>Hard reset</button>
              </div>

              <div className="toolbar" style={{ marginTop: 8 }}>
                {ROLES_LIST.map((r) => (
                  <button key={r} onClick={() => sendAction('open_role_popup', { role: r })}>
                    open {r}
                  </button>
                ))}
                {ROLES_LIST.map((r) => (
                  <button key={r} onClick={() => sendAction('close_role_popup', { role: r })}>
                    close {r}
                  </button>
                ))}
              </div>

              <div style={{ marginTop: 8 }}>
                <button onClick={() => sendAction('start_pendulum')}>Start pendulum</button>
                <button onClick={() => sendAction('debug_set_final_hold')}>Debug final_hold</button>
              </div>

              <div style={{ margin: '8px 0', fontSize: 13, fontFamily: 'monospace', lineHeight: 1.5 }}>
                {'phase: '}{state?.scenario?.phase ?? '—'}
                {' · pendulumStep: '}{String(state?.scenario?.pendulumStep ?? '—')}
                {' · wave: '}{state?.scenario?.waveIndex ?? 0}
                {' · settled: '}{String(state?.scenario?.waveSettled ?? false)}
                {' · active: '}{String(state?.scenario?.active ?? false)}
                {' · current: '}{state?.scenario?.currentRole ?? '—'}
                {' · open: '}
                {ROLES_LIST.filter((r) => state?.scenario?.openRoles?.[r]).join(',') || '—'}
                {' · epoch: '}{state?.scenario?.popupEpoch ?? 0}
                <br />
                {'dwellNextAt: '}{state?.scenario?.dwellNextAt ?? '—'}
                {' · returnDelaySeconds: '}{state?.scenario?.returnDelaySeconds ?? '—'}
                {' · dwellSeconds: '}{state?.scenario?.dwellSeconds ?? '—'}
              </div>

              {/* Local settings */}
              <div style={{ margin: '12px 0', padding: 12, border: '1px solid #444', borderRadius: 8 }}>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>Local settings</div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                  <label style={{ fontSize: 13 }}>
                    serverHost{' '}
                    <input
                      type="text"
                      placeholder="например: 192.168.1.50:8787"
                      value={localSettings.serverHost}
                      onChange={(e) =>
                        setLocalSettings((s) => ({ ...s, serverHost: e.target.value }))
                      }
                      style={{ width: 220 }}
                    />
                  </label>
                  <button onClick={saveLocalAndReconnect}>Save & reconnect</button>
                  <button
                    onClick={() => {
                      const next = saveLocalSettings({ serverHost: '', audioEnabled: localSettings.audioEnabled })
                      setLocalSettings((s) => ({ ...s, serverHost: next.serverHost || '' }))
                    }}
                  >
                    Use current host
                  </button>
                  <span style={{ fontSize: 12, opacity: 0.8 }}>
                    active host: {localSettings.serverHost || window.location.host}
                  </span>
                </div>
              </div>

              {/* Global settings */}
              <div style={{ margin: '12px 0', padding: 12, border: '1px solid #444', borderRadius: 8 }}>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>Global settings</div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                  <label style={{ fontSize: 13 }}>
                    returnDelaySeconds{' '}
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      value={globalSettings.returnDelaySeconds}
                      onChange={(e) =>
                        setGlobalSettings((s) => ({ ...s, returnDelaySeconds: e.target.value }))
                      }
                      style={{ width: 90 }}
                    />
                  </label>
                  <label style={{ fontSize: 13 }}>
                    dwellSeconds{' '}
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      value={globalSettings.dwellSeconds}
                      onChange={(e) =>
                        setGlobalSettings((s) => ({ ...s, dwellSeconds: e.target.value }))
                      }
                      style={{ width: 90 }}
                    />
                  </label>
                  <button onClick={saveGlobalSettings} disabled={settingsSaving}>
                    {settingsSaving ? 'Saving...' : 'Save settings'}
                  </button>
                  <button onClick={loadGlobalSettings}>Reload settings</button>
                </div>
              </div>

              <MidiPanel sendAction={sendAction} />
            </>
          )}

          <div style={{ marginTop: 16, fontSize: 12, opacity: 0.6 }}>
            Меню: M / Ь — открыть/закрыть · Esc — закрыть
          </div>
        </div>
      )}
    </div>
  )
}