import { useEffect, useRef, useState } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { authHeaders } from './api'
import { STROKE_DASHARRAYS } from './strokeStyles'
import { pdfTextPreviewStyle } from './textPreview'

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl

const TEMPLATE_WIDTH_PT = 1190.55
const TEMPLATE_HEIGHT_PT = 841.89

function PdfPage({ pdf, number, items, selected, onSelect, onChange }) {
  const canvasRef = useRef(null)
  const pageRef = useRef(null)
  const [ratio, setRatio] = useState(1.414)
  const [pageWidth, setPageWidth] = useState(TEMPLATE_WIDTH_PT)

  useEffect(() => {
    let cancelled = false
    pdf.getPage(number).then((page) => {
      if (cancelled) return
      const viewport = page.getViewport({ scale: 1 })
      const width = Math.min(1120, pageRef.current?.clientWidth || 920)
      setPageWidth(width)
      const scale = width / viewport.width
      const renderViewport = page.getViewport({ scale })
      setRatio(renderViewport.height / renderViewport.width)
      const canvas = canvasRef.current
      canvas.width = Math.round(renderViewport.width)
      canvas.height = Math.round(renderViewport.height)
      canvas.style.width = `${renderViewport.width}px`
      canvas.style.height = `${renderViewport.height}px`
      page.render({ canvasContext: canvas.getContext('2d'), viewport: renderViewport })
    })
    return () => { cancelled = true }
  }, [number, pdf])

  useEffect(() => {
    if (!pageRef.current || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(([entry]) => setPageWidth(entry.contentRect.width))
    observer.observe(pageRef.current)
    return () => observer.disconnect()
  }, [])

  const pointerStart = (event, item, mode) => {
    event.preventDefault(); event.stopPropagation(); onSelect(number, item.id)
    const pointerTarget = event.currentTarget
    pointerTarget.setPointerCapture?.(event.pointerId)
    document.body.classList.add('line-pointer-active')
    const bounds = pageRef.current.getBoundingClientRect()
    const start = { x: event.clientX, y: event.clientY, item: { ...item } }
    const adjustableHorizontal = item.type === 'shape' && ['scan-divider', 'caption-divider'].includes(item.role)
    const adjustableVertical = item.type === 'shape' && item.shape === 'vertical-line' && ['divider', 'outline-vertical'].includes(item.role)
    const move = (next) => {
      next.preventDefault()
      const dx = (next.clientX - start.x) / bounds.width
      const dy = (next.clientY - start.y) / bounds.height
      if (mode === 'move' && adjustableHorizontal) onChange(number, item.id, { y: Math.max(0, Math.min(1 - item.h, start.item.y + dy)) })
      else if (mode === 'move' && adjustableVertical) onChange(number, item.id, { x: Math.max(0, Math.min(1 - item.w, start.item.x + dx)) })
      else if (mode === 'line-start' && adjustableHorizontal) {
        const nextX = Math.max(0, Math.min(start.item.x + start.item.w - .02, start.item.x + dx))
        onChange(number, item.id, { x: nextX, w: start.item.w + start.item.x - nextX })
      } else if (mode === 'line-end' && adjustableHorizontal) {
        onChange(number, item.id, { w: Math.max(.02, Math.min(1 - start.item.x, start.item.w + dx)) })
      } else if (mode === 'line-start' && adjustableVertical) {
        const nextY = Math.max(0, Math.min(start.item.y + start.item.h - .02, start.item.y + dy))
        onChange(number, item.id, { y: nextY, h: start.item.h + start.item.y - nextY })
      } else if (mode === 'line-end' && adjustableVertical) {
        onChange(number, item.id, { h: Math.max(.02, Math.min(1 - start.item.y, start.item.h + dy)) })
      }
      else if (mode === 'move') onChange(number, item.id, { x: Math.max(0, Math.min(1 - item.w, start.item.x + dx)), y: Math.max(0, Math.min(1 - item.h, start.item.y + dy)) })
      else onChange(number, item.id, { w: Math.max(.03, Math.min(1 - item.x, start.item.w + dx)), h: Math.max(.03, Math.min(1 - item.y, start.item.h + dy)) })
    }
    const stop = (next) => {
      next?.preventDefault()
      document.body.classList.remove('line-pointer-active')
      if (pointerTarget.hasPointerCapture?.(event.pointerId)) pointerTarget.releasePointerCapture(event.pointerId)
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop)
      window.removeEventListener('pointercancel', stop)
    }
    window.addEventListener('pointermove', move, { passive: false }); window.addEventListener('pointerup', stop, { passive: false })
    window.addEventListener('pointercancel', stop, { passive: false })
  }

  const startIndentedParagraph = (event, item) => {
    if (item.role !== 'body' || event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return
    event.preventDefault()
    const target = event.currentTarget
    const start = target.selectionStart
    const end = target.selectionEnd
    const next = `${item.text.slice(0, start)}\n\u2003${item.text.slice(end)}`
    onChange(number, item.id, { text: next })
    requestAnimationFrame(() => { target.selectionStart = target.selectionEnd = start + 2 })
  }

  const pasteFormattedText = (event, item) => {
    if (item.role !== 'body') return
    event.preventDefault()
    const target = event.currentTarget
    const start = target.selectionStart
    const end = target.selectionEnd
    const pasted = event.clipboardData.getData('text/plain').replace(/\r\n?/g, '\n')
    const formatted = pasted.split('\n').map((line) => !line.trim() || line.startsWith('\u2003') ? line : `\u2003${line.trimStart()}`).join('\n')
    onChange(number, item.id, { text: `${item.text.slice(0, start)}${formatted}${item.text.slice(end)}` })
    requestAnimationFrame(() => { target.selectionStart = target.selectionEnd = start + formatted.length })
  }

  return <section className="pdf-page-wrap">
    <div className="page-label">{number}</div>
    <div className="pdf-page" ref={pageRef} style={{ aspectRatio: `1 / ${ratio}` }} onPointerDown={() => onSelect(number, null)}>
      <canvas ref={canvasRef} />
      {[...(items || [])].sort((a, b) => (a.type === 'page-background' ? -1 : 0) - (b.type === 'page-background' ? -1 : 0)).map((item) => {
        const active = selected?.page === number && selected?.id === item.id
        const adjustableHorizontal = item.type === 'shape' && ['scan-divider', 'caption-divider'].includes(item.role)
        const adjustableVertical = item.type === 'shape' && item.shape === 'vertical-line' && ['divider', 'outline-vertical'].includes(item.role)
        const adjustableLine = adjustableHorizontal || adjustableVertical
        const style = { left: `${item.x * 100}%`, top: `${item.y * 100}%`, width: `${item.w * 100}%`, height: `${item.h * 100}%` }
        const shapeWidth = Math.max(.001, Number(item.w || 0) * TEMPLATE_WIDTH_PT)
        const shapeHeight = Math.max(.001, Number(item.h || 0) * TEMPLATE_HEIGHT_PT)
        if (item.type === 'page-background' || (item.type === 'shape' && item.locked && !adjustableLine)) style.pointerEvents = 'none'
        return <div key={item.id} className={`editor-item ${active ? 'selected' : ''} ${item.locked ? 'locked' : ''} ${adjustableHorizontal ? 'adjustable-horizontal' : ''} ${adjustableVertical ? 'adjustable-vertical' : ''} item-${item.type}`} style={style}
          onPointerDown={(event) => { if (item.locked) { event.stopPropagation(); onSelect(number, item.id) } }}>
          {item.type === 'text' && <textarea value={item.text} placeholder={item.placeholder || ''} onFocus={() => {
            onSelect(number, item.id)
            if (item.role === 'body' && !item.text) onChange(number, item.id, { text: '\u2003' })
          }}
            onChange={(e) => onChange(number, item.id, { text: e.target.value })}
            onKeyDown={(e) => startIndentedParagraph(e, item)}
            onPaste={(e) => pasteFormattedText(e, item)}
            style={pdfTextPreviewStyle(item, pageWidth)} />}
          {item.type === 'image' && (item.missing
            ? <div className="missing-scan" title={`Оборот ${item.scanCode || ''} в архиве не сохранился`} />
            : item.src
            ? <img src={item.src} draggable="false" style={{ objectFit: item.fit || 'contain' }} />
            : <div className="image-placeholder"><b>Скан {item.scanCode || item.sequence || item.cardIndex || ''}</b><span>Выберите слот и загрузите файл</span></div>)}
          {item.type === 'cover' && <div className="cover" style={{ background: item.color || '#fff' }} />}
          {item.type === 'page-background' && <div className="page-background" style={{ background: item.color || '#fff' }} />}
          {item.type === 'shape' && ['line', 'vertical-line', 'horizontal-frame'].includes(item.shape)
            ? <svg className="shape shape-svg" viewBox={`0 0 ${shapeWidth} ${shapeHeight}`} preserveAspectRatio="none" aria-hidden="true">
              {item.shape === 'horizontal-frame' ? <>
                <line x1="0" y1="0" x2={shapeWidth} y2="0" stroke={item.stroke || '#111111'} strokeWidth={item.strokeWidth ?? 1} strokeDasharray={STROKE_DASHARRAYS[item.strokeStyle || 'solid']} />
                <line x1="0" y1={shapeHeight} x2={shapeWidth} y2={shapeHeight} stroke={item.stroke || '#111111'} strokeWidth={item.strokeWidth ?? 1} strokeDasharray={STROKE_DASHARRAYS[item.strokeStyle || 'solid']} />
              </> : <line x1={item.shape === 'vertical-line' ? shapeWidth / 2 : 0} y1={item.shape === 'vertical-line' ? 0 : shapeHeight / 2}
                  x2={item.shape === 'vertical-line' ? shapeWidth / 2 : shapeWidth} y2={item.shape === 'vertical-line' ? shapeHeight : shapeHeight / 2}
                  stroke={item.stroke || '#111111'} strokeWidth={item.strokeWidth ?? 1}
                  strokeDasharray={STROKE_DASHARRAYS[item.strokeStyle || 'solid']} />}
            </svg>
            : item.type === 'shape' && <div className={`shape shape-${item.shape || 'rectangle'}`} style={{
              '--shape-fill': item.fill || 'transparent', '--shape-stroke': item.stroke || '#111111',
              '--shape-width': `${item.strokeWidth ?? 2}px`, '--shape-style': item.strokeStyle || 'solid',
            }} />}
          {item.type !== 'page-background' && !item.locked && <div className="drag-surface" onPointerDown={(e) => pointerStart(e, item, 'move')} />}
          {active && !item.locked && adjustableLine && <>
            <button className="line-handle line-handle-start" aria-label="Сократить линию с начала" draggable="false" onDragStart={(e) => e.preventDefault()} onPointerDown={(e) => pointerStart(e, item, 'line-start')} />
            <button className="line-handle line-handle-end" aria-label="Сократить линию с конца" draggable="false" onDragStart={(e) => e.preventDefault()} onPointerDown={(e) => pointerStart(e, item, 'line-end')} />
          </>}
          {active && item.type !== 'page-background' && !item.locked && !adjustableLine && <button className="resize-handle" aria-label="Изменить размер" onPointerDown={(e) => pointerStart(e, item, 'resize')} />}
        </div>
      })}
    </div>
  </section>
}

export default function PdfPages({ pages, selected, onSelect, onChange }) {
  const [pdf, setPdf] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let cancelled = false
    const task = pdfjsLib.getDocument({ url: '/api/template', httpHeaders: authHeaders() })
    task.promise.then((value) => { if (!cancelled) { setError(''); setPdf(value) } })
      .catch((reason) => { if (!cancelled) setError(reason.message) })
    return () => { cancelled = true; task.destroy() }
  }, [])
  if (error) return <div className="empty-state">Не удалось открыть шаблон: {error}</div>
  if (!pdf) return <div className="empty-state">Загружаем 28 страниц…</div>
  return <div className="pages-list">{Array.from({ length: pdf.numPages }, (_, index) =>
    <PdfPage key={index + 1} pdf={pdf} number={index + 1} items={pages[index + 1] || []}
      selected={selected} onSelect={onSelect} onChange={onChange} />)}</div>
}
