import { useEffect, useRef, useState } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { authHeaders } from './api'

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl

function PdfPage({ pdf, number, items, selected, onSelect, onChange }) {
  const canvasRef = useRef(null)
  const pageRef = useRef(null)
  const [ratio, setRatio] = useState(1.414)

  useEffect(() => {
    let cancelled = false
    pdf.getPage(number).then((page) => {
      if (cancelled) return
      const viewport = page.getViewport({ scale: 1 })
      const width = Math.min(1120, pageRef.current?.clientWidth || 920)
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

  const pointerStart = (event, item, mode) => {
    event.preventDefault(); event.stopPropagation(); onSelect(number, item.id)
    const bounds = pageRef.current.getBoundingClientRect()
    const start = { x: event.clientX, y: event.clientY, item: { ...item } }
    const move = (next) => {
      const dx = (next.clientX - start.x) / bounds.width
      const dy = (next.clientY - start.y) / bounds.height
      if (mode === 'move') onChange(number, item.id, { x: Math.max(0, Math.min(1 - item.w, start.item.x + dx)), y: Math.max(0, Math.min(1 - item.h, start.item.y + dy)) })
      else onChange(number, item.id, { w: Math.max(.03, Math.min(1 - item.x, start.item.w + dx)), h: Math.max(.03, Math.min(1 - item.y, start.item.h + dy)) })
    }
    const stop = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', stop)
  }

  return <section className="pdf-page-wrap">
    <div className="page-label">{number}</div>
    <div className="pdf-page" ref={pageRef} style={{ aspectRatio: `1 / ${ratio}` }} onPointerDown={() => onSelect(number, null)}>
      <canvas ref={canvasRef} />
      {[...(items || [])].sort((a, b) => (a.type === 'page-background' ? -1 : 0) - (b.type === 'page-background' ? -1 : 0)).map((item) => {
        const active = selected?.page === number && selected?.id === item.id
        const style = { left: `${item.x * 100}%`, top: `${item.y * 100}%`, width: `${item.w * 100}%`, height: `${item.h * 100}%` }
        if (item.type === 'page-background' || (item.type === 'shape' && item.locked)) style.pointerEvents = 'none'
        return <div key={item.id} className={`editor-item ${active ? 'selected' : ''} ${item.locked ? 'locked' : ''} item-${item.type}`} style={style}
          onPointerDown={(event) => { if (item.locked) { event.stopPropagation(); onSelect(number, item.id) } }}>
          {item.type === 'text' && <textarea value={item.text} placeholder={item.placeholder || ''} onFocus={() => onSelect(number, item.id)}
            onChange={(e) => onChange(number, item.id, { text: e.target.value })}
            style={{ fontSize: `${Math.max(10, item.fontSize * .55)}px`, color: item.color, background: item.background,
                     fontFamily: item.fontFamily || 'Times New Roman, serif', fontWeight: item.bold ? 700 : 400,
                     fontStyle: item.italic ? 'italic' : 'normal', textAlign: item.align === 'justify' ? 'justify' : item.align }} />}
          {item.type === 'image' && (item.missing
            ? <div className="missing-scan" title={`Оборот ${item.scanCode || ''} в архиве не сохранился`} />
            : item.src
            ? <img src={item.src} draggable="false" style={{ objectFit: item.fit || 'contain' }} />
            : <div className="image-placeholder"><b>Скан {item.scanCode || item.sequence || item.cardIndex || ''}</b><span>Выберите слот и загрузите файл</span></div>)}
          {item.type === 'cover' && <div className="cover" style={{ background: item.color || '#fff' }} />}
          {item.type === 'page-background' && <div className="page-background" style={{ background: item.color || '#fff' }} />}
          {item.type === 'shape' && <div className={`shape shape-${item.shape || 'rectangle'}`} style={{
            '--shape-fill': item.fill || 'transparent', '--shape-stroke': item.stroke || '#111111',
            '--shape-width': `${item.strokeWidth || 2}px`, '--shape-style': item.strokeStyle || 'solid',
          }} />}
          {item.type !== 'page-background' && !item.locked && <div className="drag-surface" onPointerDown={(e) => pointerStart(e, item, 'move')} />}
          {active && item.type !== 'page-background' && !item.locked && <button className="resize-handle" aria-label="Изменить размер" onPointerDown={(e) => pointerStart(e, item, 'resize')} />}
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
