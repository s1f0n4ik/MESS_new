import { useEffect, useState } from 'react'
import { pdfUrl } from '../net/urls'
import { PdfDocument } from './PdfDocument'

// pdf2.pdf -> «Текст 2». Заказчик говорит «текстами», а не «пдфами».
function tabLabel(file) {
  const m = /^pdf(\d+)\.pdf$/i.exec(String(file || ''))
  return m ? `Текст ${m[1]}` : String(file || '').replace(/\.pdf$/i, '')
}

export function PdfWindowLayer({ state, myRole, serverHost = '' }) {
  const win = state?.pdfWindowsByRole?.[myRole]
  const token = win?.token || null
  const serverActive = win?.activeTab || null

  // Локальный выбор вкладки посетителем. Сервер задаёт только дефолт.
  const [override, setOverride] = useState(null)

  // Новая волна / новое оседание -> возвращаемся к серверной вкладке.
  useEffect(() => {
    setOverride(null)
  }, [token])

  if (!win || !win.visible) return null

  const tabs = Array.isArray(win.tabs) ? win.tabs : []
  const active = override && tabs.includes(override) ? override : serverActive
  const showTabs = tabs.length > 1

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        background: '#111',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {showTabs && (
        <div
          style={{
            flex: '0 0 auto',
            display: 'flex',
            gap: 4,
            padding: 6,
            background: '#222',
          }}
        >
          {tabs.map((t) => (
            <button
              key={t}
              onClick={() => setOverride(t)}
              style={{
                fontWeight: t === active ? 700 : 400,
                background: t === active ? '#2d6' : '#444',
                color: t === active ? '#000' : '#eee',
                border: 0,
                padding: '8px 16px',
                fontSize: 15,
                cursor: 'pointer',
                userSelect: 'none',
              }}
            >
              {tabLabel(t)}
            </button>
          ))}
        </div>
      )}

      <div style={{ flex: '1 1 auto', minHeight: 0 }}>
        {active ? (
          <PdfDocument
            key={active}
            url={pdfUrl(active, serverHost)}
            resetKey={token}
          />
        ) : null}
      </div>
    </div>
  )
}