import { useEffect } from 'react'

const invoke = (cmd, args) => window.__TAURI__?.core?.invoke?.(cmd, args)

export const minimizeThisPdfWindow = () => invoke('minimize_this_window')
export const togglePdfWindows = () => invoke('toggle_pdf_windows')
export const restorePdfWindows = () => invoke('restore_pdf_windows')
export const minimizePdfWindows = () => invoke('minimize_pdf_windows')

/**
 * P (KeyP, любая раскладка) работает в ОБОИХ окнах:
 *  - в главном — сворачивает/возвращает PDF-окна этой машины;
 *  - в PDF-окне — сворачивает их (окно после открытия держит фокус,
 *    и без этого нажатие в него просто терялось).
 * Esc в PDF-окне сворачивает только его.
 */
export function usePdfWindowHotkeys(isPdfWindow) {
  useEffect(() => {
    if (!window.__TAURI__) return
    const onKey = (e) => {
      if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return
      if (e.ctrlKey || e.altKey || e.metaKey) return
      if (e.code === 'KeyP') {
        e.preventDefault()
        const p = isPdfWindow ? minimizePdfWindows() : togglePdfWindows()
        Promise.resolve(p).then((r) => console.log('[pdf-hotkey] P →', r))
        return
      }
      if (isPdfWindow && e.key === 'Escape') {
        e.preventDefault()
        minimizeThisPdfWindow()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isPdfWindow])
}

/** Кнопка в углу PDF-окна. В браузере (dev без Tauri) не рендерится. */
export function PdfMinimizeButton() {
  if (!window.__TAURI__) return null
  return (
    <>
      <div style={{
        position: 'fixed', top: 8, right: 52, zIndex: 999, pointerEvents: 'none',
        height: 28, display: 'flex', alignItems: 'center', padding: '0 10px',
        borderRadius: 6, background: 'rgba(0,0,0,.45)', color: '#fff',
        font: '600 13px Arial, sans-serif', opacity: 0.72,
      }}>Inheritance</div>
      <button
        onClick={minimizeThisPdfWindow}
        title="Свернуть (Esc или P). Вернуть — клавиша P"
        style={{
          position: 'fixed', top: 8, right: 8, zIndex: 1000,
          width: 34, height: 28, lineHeight: '24px', fontSize: 18,
          background: 'rgba(0,0,0,.45)', color: '#fff', border: '1px solid rgba(255,255,255,.35)',
          borderRadius: 6, cursor: 'pointer', opacity: 0.55,
        }}
        onMouseEnter={(e) => (e.currentTarget.style.opacity = 1)}
        onMouseLeave={(e) => (e.currentTarget.style.opacity = 0.55)}
      >
        —
      </button>
    </>
  )
}
