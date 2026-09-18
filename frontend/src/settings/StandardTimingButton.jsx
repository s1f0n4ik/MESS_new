import { useEffect, useState } from 'react'
import { apiUrl } from '../net/urls'

export function StandardTimingButton({ serverHost, onReset, style }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [defaults, setDefaults] = useState(null)

  useEffect(() => {
    fetch(apiUrl('/api/settings/global/defaults', serverHost))
      .then((r) => (r.ok ? r.json() : null))
      .then(setDefaults)
      .catch(() => {})
  }, [serverHost])

  const reset = async () => {
    setBusy(true)
    try {
      const r = await fetch(apiUrl('/api/settings/global/reset-timings', serverHost), { method: 'POST' })
      const data = await r.json().catch(() => ({}))
      if (r.status === 404) throw new Error('бэкенд без reset-timings — пересобери postcards-backend.exe')
      if (!r.ok || !data.ok) throw new Error(data.detail || `HTTP ${r.status}`)
      // Остальные панели (режим инсталляции и т.п.) обновляются по этому событию.
      window.dispatchEvent(new CustomEvent('postcards:global-settings', { detail: data.settings }))
      onReset?.(data.settings)
      setMsg('✓ боевой тайминг')
    } catch (e) {
      setMsg(`ошибка: ${e.message || e}`)
    } finally {
      setBusy(false)
      setTimeout(() => setMsg(''), 3000)
    }
  }

  const title = defaults
    ? `шаг ${defaults.stepSeconds} с · удержание ${defaults.holdSeconds} с · пауза между кругами ${defaults.gapSeconds} с` +
      (defaults.pendulumStepMs != null ? ` · шаг маятника ${defaults.pendulumStepMs / 1000} с` : '')
    : 'Вернуть боевые значения таймингов'

  return (
    <span style={style}>
      <button onClick={reset} disabled={busy} title={title}>
        {busy ? '…' : '↺ Стандартный тайминг'}
      </button>
      {msg && <span style={{ marginLeft: 8, fontSize: 13, opacity: 0.8 }}>{msg}</span>}
    </span>
  )
}