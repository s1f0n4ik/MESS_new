import { useEffect, useState } from 'react'
import { apiUrl } from '../net/urls'

const MODES = [
  { value: 'exhibition', label: 'Выставка (MIDI, Reaper)' },
  { value: 'laptop', label: 'Ноутбуки (автономно, без MIDI)' },
]

export function InstallationModePanel({ serverHost }) {
  const [settings, setSettings] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch(apiUrl('/api/settings/global', serverHost))
      .then((r) => r.json())
      .then(setSettings)
      .catch(() => {})
  }, [serverHost])

  if (!settings) return null

  // Если бэкенд старый (exe без laptop-режима) — поля не будет, панель скажет об этом.
  if (!('installationMode' in settings)) {
    return (
      <div style={{ margin: '12px 0', padding: 12, border: '1px solid #a55', borderRadius: 8, color: '#e88' }}>
        Режим инсталляции: бэкенд не поддерживает installationMode —
        пересобери postcards-backend.exe (build-backend.bat).
      </div>
    )
  }

  const save = async (patch) => {
    const next = { ...settings, ...patch }
    setSettings(next)
    setSaving(true)
    try {
      await fetch(apiUrl('/api/settings/global', serverHost), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ margin: '12px 0', padding: 12, border: '1px solid #444', borderRadius: 8 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>
        Режим инсталляции {saving ? '…' : ''}
      </div>
      <select
        value={settings.installationMode}
        onChange={(e) => save({ installationMode: e.target.value })}
      >
        {MODES.map((m) => (
          <option key={m.value} value={m.value}>{m.label}</option>
        ))}
      </select>
      {settings.installationMode === 'laptop' && (
        <label style={{ display: 'inline-block', marginLeft: 16, fontSize: 13 }}>
          Шаг маятника, мс:{' '}
          <input
            type="number"
            min={100}
            step={100}
            value={settings.pendulumStepMs}
            onChange={(e) => save({ pendulumStepMs: Number(e.target.value) })}
            style={{ width: 90 }}
          />
        </label>
      )}
      <div style={{ marginTop: 6, fontSize: 12, opacity: 0.7 }}>
        Выставка — первый круг идёт по MIDI-нотам, финал по ноте 60.
        Ноутбуки — первый круг по таймеру, MIDI-вход выключен, финал закрывает
        медиатор (Launch force / hard reset).
      </div>
    </div>
  )
}