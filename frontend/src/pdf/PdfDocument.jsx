import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import * as pdfjs from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

// Vite сам положит воркер в бандл и отдаст правильный путь.
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

// Ограничиваем DPR: на 4K rendering в 3x съедает память без видимой пользы.
const MAX_DPR = 2

function PdfPage({ page, containerWidth }) {
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
        width: cssW,
        height: cssH,
        margin: '0 auto 12px',
        background: '#fff',
        // Плейсхолдер держит высоту до рендера — скролл не дёргается.
        boxShadow: rendered ? 'none' : 'inset 0 0 0 1px #333',
      }}
    >
      <canvas
        ref={canvasRef}
        style={{ display: 'block', width: '100%', height: '100%' }}
      />
    </div>
  )
}

export function PdfDocument({ url, resetKey }) {
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
        background: '#1a1a1a',
        padding: '12px 0',
      }}
    >
      {error ? (
        <div style={{ color: '#f66', fontFamily: 'monospace', padding: 20 }}>
          PDF load error: {error}
        </div>
      ) : (
        pages.map((p) => (
          <PdfPage key={p.pageNumber} page={p} containerWidth={width} />
        ))
      )}
    </div>
  )
}