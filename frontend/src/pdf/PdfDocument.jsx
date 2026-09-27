import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import * as pdfjs from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

// Vite сам положит воркер в бандл и отдаст правильный путь.
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

// Ограничиваем DPR: на 4K rendering в 3x съедает память без видимой пользы.
const MAX_DPR = 2

function EditableItem({ item, selected, editMode, assetOrigin, onSelect, onChange }) {
  const dragRef = useRef(null)

  const beginPointer = (event, mode) => {
    if (!editMode) return
    event.preventDefault()
    event.stopPropagation()
    onSelect(item.id)
    dragRef.current = {
      mode, startX: event.clientX, startY: event.clientY,
      x: item.x, y: item.y, w: item.w, h: item.h,
      pageW: event.currentTarget.parentElement.clientWidth,
      pageH: event.currentTarget.parentElement.clientHeight,
    }
    const move = (e) => {
      const d = dragRef.current
      if (!d) return
      const dx = (e.clientX - d.startX) / d.pageW
      const dy = (e.clientY - d.startY) / d.pageH
      if (d.mode === 'resize') {
        onChange(item.id, { w: Math.max(0.02, Math.min(1 - d.x, d.w + dx)), h: Math.max(0.02, Math.min(1 - d.y, d.h + dy)) })
      } else {
        onChange(item.id, { x: Math.max(0, Math.min(1 - d.w, d.x + dx)), y: Math.max(0, Math.min(1 - d.h, d.y + dy)) })
      }
    }
    const up = () => {
      dragRef.current = null
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const common = {
    position: 'absolute', left: `${item.x * 100}%`, top: `${item.y * 100}%`,
    width: `${item.w * 100}%`, height: `${item.h * 100}%`, boxSizing: 'border-box',
    outline: selected && editMode ? '3px solid #16a3ff' : 'none',
    cursor: editMode ? 'move' : 'default', overflow: 'hidden',
    pointerEvents: editMode ? 'auto' : 'none',
  }

  return (
    <div style={common} onPointerDown={(e) => beginPointer(e, 'move')} onClick={(e) => { e.stopPropagation(); onSelect(item.id) }}>
      {item.type === 'text' && (editMode && selected ? (
        <textarea
          value={item.text || ''}
          onPointerDown={(e) => e.stopPropagation()}
          onChange={(e) => onChange(item.id, { text: e.target.value })}
          style={{ width: '100%', height: '100%', resize: 'none', boxSizing: 'border-box', border: 0,
            padding: 4, fontSize: item.fontSize || 28, color: item.color || '#111',
            background: item.background || 'transparent', textAlign: item.align || 'left',
            fontWeight: item.bold ? 700 : 400, fontFamily: 'Arial, sans-serif' }}
        />
      ) : (
        <div style={{ width: '100%', height: '100%', padding: 4, boxSizing: 'border-box', whiteSpace: 'pre-wrap',
          overflow: 'hidden', fontSize: item.fontSize || 28, color: item.color || '#111',
          background: item.background || 'transparent', textAlign: item.align || 'left',
          fontWeight: item.bold ? 700 : 400, fontFamily: 'Arial, sans-serif' }}>{item.text}</div>
      ))}
      {item.type === 'image' && (
        <img src={`${assetOrigin}${item.src}`} alt="" draggable={false}
          style={{ width: '100%', height: '100%', display: 'block', objectFit: item.fit || 'cover', pointerEvents: 'none' }} />
      )}
      {item.type === 'cover' && <div style={{ width: '100%', height: '100%', background: item.color || '#fff' }} />}
      {selected && editMode && (
        <>
          <div onPointerDown={(e) => beginPointer(e, 'move')} title="Переместить"
            style={{ position: 'absolute', left: 0, top: 0, width: 24, height: 24,
              background: '#16a3ff', cursor: 'move', border: '2px solid white', boxSizing: 'border-box' }} />
          <div onPointerDown={(e) => beginPointer(e, 'resize')} title="Изменить размер"
            style={{ position: 'absolute', right: 0, bottom: 0, width: 20, height: 20,
              background: '#16a3ff', cursor: 'nwse-resize', border: '2px solid white', boxSizing: 'border-box' }} />
        </>
      )}
    </div>
  )
}

function PdfPage({ page, containerWidth, editor }) {
  const canvasRef = useRef(null)
  const wrapRef = useRef(null)
  const taskRef = useRef(null)
  const [visible, setVisible] = useState(false)
  const [rendered, setRendered] = useState(false)

  const base = page.getViewport({ scale: 1 })
  const scale = containerWidth > 0 ? containerWidth / base.width : 1
  const cssW = Math.floor(base.width * scale)
  const cssH = Math.floor(base.height * scale)

  // Наблюдаем за попаданием в кадр с запасом в один экран.
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setVisible(true)
        }
      },
      { root: el.closest('[data-pdf-scroll]'), rootMargin: '100% 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    if (!visible || containerWidth <= 0) return
    const canvas = canvasRef.current
    if (!canvas) return

    const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR)
    const viewport = page.getViewport({ scale: scale * dpr })

    canvas.width = Math.floor(viewport.width)
    canvas.height = Math.floor(viewport.height)

    const ctx = canvas.getContext('2d', { alpha: false })

    // Отменяем предыдущий рендер: без этого при resize pdf.js бросает
    // "Cannot use the same canvas during multiple render operations".
    if (taskRef.current) {
      try { taskRef.current.cancel() } catch (_e) {}
    }

    const task = page.render({ canvasContext: ctx, viewport })
    taskRef.current = task

    task.promise
      .then(() => setRendered(true))
      .catch((err) => {
        if (err?.name !== 'RenderingCancelledException') {
          console.warn('[pdf] render failed:', err?.message)
        }
      })

    return () => {
      try { task.cancel() } catch (_e) {}
    }
  }, [visible, page, scale, containerWidth])

  return (
    <div
      ref={wrapRef}
      style={{
        position: 'relative',
        width: cssW,
        height: cssH,
        margin: '0 auto',
        background: '#fff',
        // Плейсхолдер держит высоту до рендера — скролл не дёргается.
        boxShadow: rendered ? 'none' : 'inset 0 0 0 1px #333',
      }}
    >
      <canvas
        ref={canvasRef}
        style={{ display: 'block', width: '100%', height: '100%' }}
      />
      <div style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}
        onClick={() => editor?.onSelect?.(null)}>
        {(editor?.items || []).map((item) => (
          <EditableItem key={item.id} item={item} editMode={editor.editMode}
            selected={editor.selectedId === item.id} assetOrigin={editor.assetOrigin || ''}
            onSelect={editor.onSelect} onChange={editor.onChange} />
        ))}
      </div>
    </div>
  )
}

export function PdfDocument({ url, resetKey, editor = null }) {
  const scrollRef = useRef(null)
  const [pages, setPages] = useState([])
  const [width, setWidth] = useState(0)
  const [error, setError] = useState(null)

  // Ширина контейнера -> масштаб «вписать по ширине».
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      // 24px — вертикальный скроллбар и воздух по бокам.
      setWidth(Math.max(0, el.clientWidth - 24))
    })
    ro.observe(el)
    setWidth(Math.max(0, el.clientWidth - 24))
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    let cancelled = false
    let doc = null
    setPages([])
    setError(null)

    const task = pdfjs.getDocument({
      url,
      withCredentials: false,
      // Без этого pdf.js тянет CMap'ы из CDN — в изолированной сети это провал.
      cMapUrl: undefined,
      isEvalSupported: false,
    })

    task.promise
      .then(async (d) => {
        if (cancelled) { d.destroy(); return }
        doc = d
        const list = []
        for (let i = 1; i <= d.numPages; i += 1) {
          list.push(await d.getPage(i))
        }
        if (!cancelled) setPages(list)
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || String(err))
        console.warn('[pdf] load failed:', url, err?.message)
      })

    return () => {
      cancelled = true
      try { task.destroy() } catch (_e) {}
      if (doc) { try { doc.destroy() } catch (_e) {} }
    }
  }, [url])

  // Требование ТЗ: новый круг — документ с начала.
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0
  }, [resetKey, url])

  return (
    <div
      ref={scrollRef}
      data-pdf-scroll=""
      style={{
        width: '100%',
        height: '100%',
        overflowY: 'auto',
        overflowX: 'hidden',
        background: '#fff',
        padding: 0,
      }}
    >
      {error ? (
        <div style={{ color: '#f66', fontFamily: 'monospace', padding: 20 }}>
          PDF load error: {error}
        </div>
      ) : (
        pages.map((p) => (
          <PdfPage key={p.pageNumber} page={p} containerWidth={width}
            editor={editor ? { ...editor, items: editor.pages?.[String(p.pageNumber)] || [], pageNumber: p.pageNumber,
              selectedId: Number(editor.selected?.page) === p.pageNumber ? editor.selected.id : null,
              onSelect: (id) => editor.onSelect(p.pageNumber, id),
              onChange: (id, patch) => editor.onChange(p.pageNumber, id, patch) } : null} />
        ))
      )}
    </div>
  )
}
