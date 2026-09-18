import { useEffect, useState } from 'react'
import { apiUrl } from '../net/urls'

export function CoordinatorAddressPanel({ serverHost }) {
  const [info, setInfo] = useState(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState('')

  const load = () => {
    setError('')
    fetch(apiUrl('/api/net/info', serverHost))
      .then((r) => {
        if (r.status === 404) throw new Error('бэкенд без /api/net/info — пересобери postcards-backend.exe')
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(setInfo)
      .catch((e) => setError(e.message || String(e)))
  }
  useEffect(load, [serverHost])

  const copy = async (text) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(text)
      setTimeout(() => setCopied(''), 1500)
    } catch {
      window.prompt('Скопируй адрес:', text)
    }
  }

  const isLocal = !serverHost || /^(https?:\/\/)?(localhost|127\.0\.0\.1)/i.test(serverHost)
  const box = { margin: '12px 0', padding: 12, border: '1px solid #444', borderRadius: 8 }

  if (error) {
    return <div style={{ ...box, borderColor: '#a55', color: '#e88' }}>Адрес координатора: {error}</div>
  }
  if (!info) return null

  // Совместимость со старым бэкендом, где addresses — массив строк.
  const list = (info.addresses || []).map((a) => (typeof a === 'string' ? { ip: a, kind: 'other', label: '' } : a))
  const others = list.filter((a) => a.ip !== info.primary)

  return (
    <div style={box}>
      <div style={{ fontWeight: 700, marginBottom: 6 }}>
        {isLocal ? 'Адрес этой машины (координатора)' : 'Координатор, к которому подключена эта машина'}
        <button onClick={load} style={{ marginLeft: 8 }}>обновить</button>
      </div>

      {info.primary ? (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <code style={{ fontSize: 26, letterSpacing: 1 }}>{info.primary}</code>
            <button onClick={() => copy(info.primary)}>
              {copied === info.primary ? '✓ скопировано' : 'копировать'}
            </button>
          </div>
          {info.primaryReason && (
            <div style={{ fontSize: 12, opacity: 0.6 }}>выбран {info.primaryReason}</div>
          )}
        </>
      ) : (
        <div style={{ color: '#e88' }}>Адрес не определён — машина не в сети?</div>
      )}

      <div style={{ fontSize: 13, marginTop: 6, opacity: 0.85 }}>
        Вводится на pc2–pc4 в поле «Адрес координатора» — голым, без http:// и порта.
        Проверка с любой машины: <code>http://{info.primary || 'IP'}:{info.port}/api/health</code>
      </div>

      {others.length > 0 && (
        <div style={{ fontSize: 12, marginTop: 8, opacity: 0.75 }}>
          Остальные адаптеры — если клиенты не подключаются, попробуй один из них:
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 4 }}>
            {others.map((a) => (
              <button
                key={a.ip}
                onClick={() => copy(a.ip)}
                title="копировать"
                style={{ fontFamily: 'monospace', opacity: a.kind === 'vpn' ? 0.5 : 1 }}
              >
                {a.ip}{a.label ? ` · ${a.label}` : ''}{copied === a.ip ? ' ✓' : ''}
              </button>
            ))}
          </div>
        </div>
      )}
      <div style={{ fontSize: 12, marginTop: 4, opacity: 0.5 }}>хост: {info.hostname}</div>
    </div>
  )
}