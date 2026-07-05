import { useEffect, useState } from 'react'

export function PdfWindowLayer({ state, myRole }) {
  const [override, setOverride] = useState(null) // локальный выбор вкладки
  const win = state?.pdfWindowsByRole?.[myRole]
  const token = win?.token

  // сброс локального выбора при смене token (новая волна/оседание)
  useEffect(() => {
    setOverride(null)
  }, [token])

  if (!win || !win.visible) return null

  const tabs = win.tabs || []
  const active = override || win.activeTab

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 50, background: '#111' }}>
      {tabs.length > 1 && (
        <div style={{ display: 'flex', gap: 4, padding: 6, background: '#222' }}>
          {tabs.map((t) => (
            <button
              key={t}
              onClick={() => setOverride(t)}
              style={{
                fontWeight: t === active ? 700 : 400,
                background: t === active ? '#2d6' : '#444',
                color: t === active ? '#000' : '#eee',
                border: 0,
                padding: '6px 12px',
                cursor: 'pointer',
              }}
            >
              {String(t).replace('.pdf', '')}
            </button>
          ))}
        </div>
      )}
      {active ? (
        <iframe
          key={active}
          src={`/pdfs/${active}`}
          title={active}
          style={{
            width: '100%',
            height: tabs.length > 1 ? 'calc(100% - 44px)' : '100%',
            border: 0,
          }}
        />
      ) : null}
    </div>
  )
}