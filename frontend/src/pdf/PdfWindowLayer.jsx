import { useEffect, useMemo, useState } from 'react'
import { pdfUrl } from '../net/urls'
import { usePdfMeta } from './pdfMeta'
import { PdfDocument } from './PdfDocument'
import { PdfEditorToolbar, usePdfEditor } from './PdfEditor'

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
  const [editingFile, setEditingFile] = useState(null)

  // Новая волна / новое оседание -> возвращаемся к серверной вкладке.
  useEffect(() => {
    setOverride(null)
  }, [token])

  // mtime файлов — для cache-buster. Ключ обновления — token,
  // то есть мета перечитывается на каждое открытие/переключение круга.
  const meta = usePdfMeta(serverHost, token)

  const tabs = Array.isArray(win?.tabs) ? win.tabs : []
  const active = editingFile || (override && tabs.includes(override) ? override : serverActive)
  const slot = String(active || '').replace(/\.pdf$/i, '')
  const editorRevision = state?.pdfEditor?.[slot]?.revision
  const editor = usePdfEditor(slot || null, serverHost, editorRevision, myRole)
  const visibleEditor = {
    ...editor,
    setEditMode: (enabled) => {
      if (enabled) setEditingFile(active)
      else setEditingFile(null)
      editor.setEditMode(enabled)
    },
    exitEdit: async () => {
      const ok = await editor.exitEdit()
      if (ok) setEditingFile(null)
      return ok
    },
  }

  // useMemo обязателен: если бы v вычислялся заново на каждый рендер
  // (например, через Date.now()), PdfDocument перезагружал бы файл бесконечно.
  const activeUrl = useMemo(() => {
    if (!active) return null
    const base = pdfUrl(active, serverHost)
    const v = meta?.[active]?.mtime
    return v ? `${base}?v=${v}` : base
  }, [active, serverHost, meta])

  if (!win || !win.visible) return null

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
              onClick={() => !editor.editMode && setOverride(t)}
              disabled={editor.editMode}
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

      {active && <PdfEditorToolbar editor={visibleEditor} />}

      <div style={{ flex: '1 1 auto', minHeight: 0 }}>
        {activeUrl ? (
          <PdfDocument key={active} url={activeUrl} resetKey={token}
            editor={{ pages: editor.doc.pages, editMode: editor.editMode, selected: editor.selected,
              assetOrigin: editor.assetOrigin, onSelect: editor.select, onChange: editor.update }} />
        ) : null}
      </div>
    </div>
  )
}
