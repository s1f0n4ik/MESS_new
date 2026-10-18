import { useEffect, useRef, useState } from 'react'
import { api, downloadFile, websocketUrl } from './api'
import { useCollaboration } from './collaboration'
import PdfPages from './PdfPages'
import UserDialog from './UserDialog'
import { STROKE_STYLE_OPTIONS } from './strokeStyles'

const newId = () => `e${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
const FONT_OPTIONS = [['Times New Roman', 'Times New Roman'], ['Arial', 'Arial'], ['Georgia', 'Georgia'], ['Courier New', 'Courier New']]
const SPREAD_SCANS = [
  [[1, '1'], [null, '1.1']], [[17, '1.21'], [9, '1.2']],
  [[2, '2'], [null, '2.1']], [[18, '2.21'], [10, '2.2']],
  [[3, '3'], [11, '3.1']], [[4, '4'], [null, '4.1']],
  [[null, '4.21'], [12, '4.2']], [[5, '5'], [13, '5.1']],
  [[6, '6'], [null, '6.1']], [[19, '6.21'], [14, '6.2']],
  [[7, '7'], [null, '7.1']], [[20, '7.21'], [15, '7.2']],
  [[8, '8'], [null, '8.1']], [[21, '8.21'], [16, '8.2']],
]

function editableLayout(pageCount = 28) {
  const pages = {}
  for (let page = 1; page <= pageCount; page += 1) {
    const items = [
      { id: `background-${page}`, type: 'page-background', x: 0, y: 0, w: 1, h: 1, color: '#ffffff', locked: true },
      { id: `divider-${page}`, type: 'shape', shape: 'vertical-line', x: .498, y: 0, w: .004, h: 1,
        fill: 'transparent', stroke: '#231f20', strokeWidth: 1, strokeStyle: 'solid', locked: true, role: 'divider' },
    ]
    for (let column = 0; column < 2; column += 1) {
      const cardIndex = Math.floor((page - 1) / 2) * 2 + column + 1
      const [sequence, scanCode] = SPREAD_SCANS[Math.floor((page - 1) / 2)][column]
      const x = column ? .511904 : .023809
      items.push(
        { id: `outline-${page}-${column}`, type: 'shape', shape: 'horizontal-frame', x, y: .03367, w: .464287, h: .93266,
          fill: 'transparent', stroke: '#231f20', strokeWidth: .5, strokeStyle: 'illustrator-dashed', locked: true, role: 'outline', cardIndex },
        { id: `outline-left-${page}-${column}`, type: 'shape', shape: 'vertical-line', x: x - .002, y: .03367, w: .004, h: .93266,
          fill: 'transparent', stroke: '#231f20', strokeWidth: .5, strokeStyle: 'illustrator-dashed', locked: true, role: 'outline-vertical', side: 'left', cardIndex },
        { id: `outline-right-${page}-${column}`, type: 'shape', shape: 'vertical-line', x: x + .462287, y: .03367, w: .004, h: .93266,
          fill: 'transparent', stroke: '#231f20', strokeWidth: .5, strokeStyle: 'illustrator-dashed', locked: true, role: 'outline-vertical', side: 'right', cardIndex },
      )
      if (page % 2) items.push(
        { id: `scan-${page}-${column}`, type: 'image', x: x + .058, y: .034, w: .358, h: .337, src: '', fit: 'contain',
          locked: true, role: 'scan', sequence, scanCode, missing: sequence == null, cardIndex },
        { id: `scan-divider-${page}-${column}`, type: 'shape', shape: 'line', x, y: .40104, w: .464287, h: .006,
          fill: 'transparent', stroke: '#231f20', strokeWidth: .5, strokeStyle: 'illustrator-dashed', locked: true, role: 'scan-divider', cardIndex },
        { id: `caption-${page}-${column}`, type: 'text', x: x + .005, y: .393, w: .462, h: .078, text: '',
          placeholder: '', fontSize: 16, fontFamily: 'Times New Roman', color: '#111111',
          background: 'transparent', align: 'right', bold: false, italic: false, locked: true, role: 'caption', cardIndex },
        { id: `caption-divider-${page}-${column}`, type: 'shape', shape: 'line', x, y: .473, w: .464287, h: .006,
          fill: 'transparent', stroke: '#231f20', strokeWidth: .5, strokeStyle: 'illustrator-dashed', locked: true, role: 'caption-divider', cardIndex },
        { id: `body-${page}-${column}`, type: 'text', x: x + .005, y: .489, w: .462, h: .473, text: '',
          placeholder: '', fontSize: 15, fontFamily: 'Times New Roman', color: '#111111',
          background: 'transparent', align: 'left', bold: false, italic: false, locked: true, role: 'body', cardIndex },
      )
      else items.push({ id: `body-${page}-${column}`, type: 'text', x: x + .005, y: .025, w: .462, h: .935, text: '',
        placeholder: '', fontSize: 15, fontFamily: 'Times New Roman', color: '#111111',
        background: 'transparent', align: 'left', bold: false, italic: false, locked: true, role: 'body', cardIndex })
    }
    pages[page] = items
  }
  return pages
}

export default function Editor({ project, user, onLogout }) {
  const [slot, setSlot] = useState('pdf1')
  const [documents, setDocuments] = useState(project.documents)
  const [selected, setSelected] = useState(null)
  const [activePage, setActivePage] = useState(1)
  const [error, setError] = useState('')
  const [publishing, setPublishing] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [lastRelease, setLastRelease] = useState(null)
  const [history, setHistory] = useState(null)
  const [usersOpen, setUsersOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const [templateSaving, setTemplateSaving] = useState(false)
  const [revision, setRevision] = useState(project.documents.find((value) => value.slot === slot)?.revision || 0)
  const [templateRevision, setTemplateRevision] = useState(project.templateRevision || 0)
  const fileRef = useRef(null)
  const replaceImageRef = useRef(null)
  const docxRef = useRef(null)
  const collaboration = useCollaboration(project.id, slot, user, templateRevision)

  useEffect(() => {
    setDocuments(project.documents)
  }, [project.documents])

  useEffect(() => {
    setSelected(null); setError(''); setRevision(documents.find((value) => value.slot === slot)?.revision || 0)
  }, [documents, slot])

  useEffect(() => {
    const socket = new WebSocket(websocketUrl(project.id))
    socket.onopen = () => socket.send('ready')
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data)
      if (message.type === 'document.saved') {
        if (message.slot === slot) setRevision(message.revision)
        setDocuments((current) => current.map((entry) => entry.slot === message.slot
          ? { ...entry, revision: message.revision, updatedBy: message.updatedBy } : entry))
      }
      if (message.type === 'document.renamed') setDocuments((current) => current.map((entry) => (
        entry.slot === message.slot ? { ...entry, title: message.title, updatedBy: message.updatedBy } : entry
      )))
      if (message.type === 'release.published') setLastRelease(message.release)
      if (message.type === 'template.updated') {
        setTemplateRevision(message.templateRevision)
        setNotice('Общий шаблон обновлён. Макет синхронизирован во всех документах.')
      }
    }
    return () => socket.close()
  }, [project.id, slot])

  const select = (page, id) => { setActivePage(page); setSelected(id ? { page, id } : null) }
  const change = (page, id, patch) => collaboration.changeLayout(page, id, patch)
  const add = (type, extra = {}) => {
    const item = {
      id: newId(), type, x: .1, y: .1, w: type === 'text' ? .48 : .3, h: type === 'text' ? .13 : .25,
      ...(type === 'text' ? { text: 'Новый текст', fontSize: 28, fontFamily: 'Times New Roman', color: '#111111', background: 'transparent', align: 'left', bold: false, italic: false } : {}),
      ...(type === 'cover' ? { color: '#ffffff' } : {}),
      ...(type === 'shape' ? { shape: 'rectangle', fill: 'transparent', stroke: '#111111', strokeWidth: 2, strokeStyle: 'solid' } : {}),
      ...extra,
    }
    collaboration.add(activePage, item); setSelected({ page: activePage, id: item.id })
  }
  const remove = () => {
    if (!selected || item?.locked) return
    collaboration.remove(selected.page, selected.id); setSelected(null)
  }
  const item = selected ? (collaboration.pages?.[selected.page] || []).find((value) => value.id === selected.id) : null
  const adjustableHorizontal = item?.type === 'shape' && ['scan-divider', 'caption-divider'].includes(item.role)
  const adjustableVertical = item?.type === 'shape' && item.shape === 'vertical-line' && ['divider', 'outline-vertical'].includes(item.role)
  const adjustableLine = adjustableHorizontal || adjustableVertical
  const pageBackground = (collaboration.pages?.[activePage] || []).find((value) => value.type === 'page-background')

  const duplicate = () => {
    if (!item || item.locked) return
    const copy = { ...item, id: newId(), x: Math.min(Math.max(0, 1 - item.w), item.x + .025), y: Math.min(Math.max(0, 1 - item.h), item.y + .025) }
    collaboration.add(selected.page, copy); setSelected({ page: selected.page, id: copy.id })
  }

  useEffect(() => {
    const onKeyDown = (event) => {
      const editing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target?.tagName) || event.target?.isContentEditable
      if (editing) return
      if ((event.key === 'Delete' || event.key === 'Backspace') && item && !item.locked) { event.preventDefault(); remove() }
      else if (event.key === 'Escape') setSelected(null)
      else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault(); event.shiftKey ? collaboration.redo() : collaboration.undo()
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'y') {
        event.preventDefault(); collaboration.redo()
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'd' && item && !item.locked) {
        event.preventDefault(); duplicate()
      } else if (item && !item.locked && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
        if (adjustableHorizontal && !['ArrowUp', 'ArrowDown'].includes(event.key)) return
        if (adjustableVertical && !['ArrowLeft', 'ArrowRight'].includes(event.key)) return
        event.preventDefault()
        const step = event.shiftKey ? .02 : .005
        const patch = {}
        if (event.key === 'ArrowLeft') patch.x = Math.max(0, item.x - step)
        if (event.key === 'ArrowRight') patch.x = Math.min(1 - item.w, item.x + step)
        if (event.key === 'ArrowUp') patch.y = Math.max(0, item.y - step)
        if (event.key === 'ArrowDown') patch.y = Math.min(1 - item.h, item.y + step)
        change(selected.page, item.id, patch)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  const upload = async (file) => {
    if (!file) return
    const target = replaceImageRef.current
    replaceImageRef.current = null
    const data = new FormData(); data.append('file', file)
    try {
      const value = await api(`/api/projects/${project.id}/assets`, { method: 'POST', body: data })
      if (target) change(target.page, target.id, { src: value.url })
      else add('image', { src: value.url, fit: 'contain' })
    } catch (reason) { setError(reason.message) }
  }

  const createLayout = () => {
    if (!window.confirm('Создать редактируемый макет на 28 страниц? Текущее состояние можно вернуть через «Отменить» или историю.')) return
    collaboration.replace(editableLayout())
    setSelected(null); setNotice('Создан макет с фиксированными полями и единым шрифтом Times New Roman')
  }

  const importWordTable = async (file) => {
    if (!file) return
    const data = new FormData(); data.append('file', file)
    setError(''); setNotice('Загружаем таблицу и расставляем изображения…')
    try {
      const imported = await api(`/api/projects/${project.id}/assets/import-docx`, { method: 'POST', body: data })
      const current = structuredClone(collaboration.snapshot())
      let slots = Object.values(current).flat().filter((value) => value.type === 'image' && value.role === 'scan')
      const pages = slots.length ? current : editableLayout()
      slots = Object.values(pages).flat().filter((value) => value.type === 'image' && value.role === 'scan')
      for (const slotValue of slots) { slotValue.src = ''; slotValue.sourceLabel = '' }
      imported.assets.forEach((asset) => {
        const slotValue = slots.find((candidate) => Number(candidate.sequence) === Number(asset.number))
        if (!slotValue) return
        slotValue.src = asset.url
        slotValue.sourceLabel = asset.label
      })
      collaboration.replace(pages); setSelected(null)
      setNotice(`Импортировано ${imported.count} изображений из последней таблицы и расставлено по утверждённой нумерации`)
    } catch (reason) { setError(reason.message); setNotice('') }
  }

  const saveTemplate = async ({ confirm = true, lineLocked = false } = {}) => {
    if (confirm && !window.confirm('Сохранить текущую вёрстку как общий шаблон? Геометрия и стили будут применены ко всем 28 страницам и всем 4 документам; тексты и изображения сохранятся.')) return
    setTemplateSaving(true); setError('')
    try {
      const value = await api(`/api/projects/${project.id}/documents/${slot}/template`, {
        method: 'PUT', body: JSON.stringify({ pages: collaboration.snapshot() }),
      })
      if (value.pages) collaboration.replace(value.pages)
      setTemplateRevision(value.templateRevision)
      setNotice(lineLocked
        ? 'Линия зафиксирована и синхронизирована на всех разворотах и во всех 4 документах.'
        : 'Общий шаблон сохранён и применён ко всем 4 документам. Тексты и изображения сохранены.')
    } catch (reason) { setError(reason.message) }
    finally { setTemplateSaving(false) }
  }

  const toggleItemLock = async () => {
    if (!item || templateSaving) return
    const lockingLine = adjustableLine && !item.locked
    change(selected.page, item.id, { locked: !item.locked })
    if (lockingLine) await saveTemplate({ confirm: false, lineLocked: true })
  }

  const applyTemplate = async () => {
    if (!window.confirm('Вернуть геометрию общего шаблона? Тексты и изображения не изменятся.')) return
    try {
      const value = await api(`/api/projects/${project.id}/documents/${slot}/template`)
      collaboration.replace(value.pages); setSelected(null); setNotice('Общий шаблон применён, содержимое сохранено')
    } catch (reason) { setError(reason.message) }
  }

  const blankPage = () => {
    if (!window.confirm(`Очистить страницу ${activePage} и скрыть исходный PDF-фон?`)) return
    collaboration.blankPage(activePage); setSelected(null)
  }
  const resetPage = () => {
    if (!window.confirm(`Удалить все изменения со страницы ${activePage} и вернуть исходный шаблон?`)) return
    collaboration.resetPage(activePage); setSelected(null)
  }
  const blankDocument = () => {
    if (!window.confirm('Создать пустой документ? Все 28 страниц станут белыми, а текущие объекты можно будет вернуть через «Отменить» или историю версий.')) return
    collaboration.blankDocument(28); setSelected(null)
  }

  const publish = async () => {
    setPublishing(true); setError('')
    try {
      const saved = await api(`/api/projects/${project.id}/documents/${slot}/collaboration-snapshot`, {
        method: 'POST', body: JSON.stringify({ pages: collaboration.snapshot(), checkpoint: true }),
      })
      setRevision(saved.revision)
      const value = await api(`/api/projects/${project.id}/publish`, { method: 'POST' })
      setLastRelease(value)
    } catch (reason) { setError(reason.message) } finally { setPublishing(false) }
  }

  const exportPdf = async () => {
    setExporting(true); setError('')
    try {
      const saved = await api(`/api/projects/${project.id}/documents/${slot}/collaboration-snapshot`, {
        method: 'POST', body: JSON.stringify({ pages: collaboration.snapshot(), checkpoint: true }),
      })
      setRevision(saved.revision)
      const title = documents.find((value) => value.slot === slot)?.title || slot
      const safeTitle = title.replace(/[\\/:*?"<>|]+/g, '-').trim() || slot
      await downloadFile(`/api/projects/${project.id}/documents/${slot}/export.pdf`, `${safeTitle}.pdf`)
    } catch (reason) { setError(reason.message) } finally { setExporting(false) }
  }

  const renameDocument = async (entry) => {
    const value = window.prompt('Новое название документа', entry.title)
    if (value === null) return
    const title = value.trim().replace(/\s+/g, ' ')
    if (!title || title === entry.title) return
    try {
      const renamed = await api(`/api/projects/${project.id}/documents/${entry.slot}/title`, {
        method: 'PATCH', body: JSON.stringify({ title }),
      })
      setDocuments((current) => current.map((item) => item.slot === entry.slot ? { ...item, ...renamed } : item))
      setNotice(`Документ переименован: ${renamed.title}`)
    } catch (reason) { setError(reason.message) }
  }

  const openHistory = async () => {
    try { setHistory(await api(`/api/projects/${project.id}/documents/${slot}/history`)) }
    catch (reason) { setError(reason.message) }
  }
  const restore = async (historyRevision) => {
    if (!window.confirm(`Восстановить версию ${historyRevision}? Текущее состояние останется в истории.`)) return
    try {
      const value = await api(`/api/projects/${project.id}/documents/${slot}/history/${historyRevision}`)
      collaboration.replace(value.pages)
      setSelected(null); setHistory(null)
    } catch (reason) { setError(reason.message) }
  }

  const people = Array.from(new Map(collaboration.people.map((person) => [person.email, person])).values())
  return <div className="app-shell">
    <header className="topbar"><div><b>Postcards Studio</b><span>{project.name}</span></div><div>
      <div className="presence" title={people.map((person) => person.name).join(', ')}>{people.map((person) => <i key={person.email} style={{ background: person.color }}>{person.name?.[0] || '?'}</i>)}<span>{people.length} в документе</span></div>
      <span>{user.name} · {user.role}</span>{user.role === 'admin' && <button onClick={() => setUsersOpen(true)}>Медиаторы</button>}<button onClick={onLogout}>Выйти</button>
    </div></header>
    <aside className="sidebar">
      <h2>Документы</h2>
      {documents.map((entry) => <div key={entry.slot} className={`document-nav ${slot === entry.slot ? 'active' : ''}`}>
        <button className="document-select" onClick={() => setSlot(entry.slot)}>
          <b>{entry.title}</b><small>{slot === entry.slot ? `Версия ${revision} · совместно` : `Версия ${entry.revision}`}</small>
        </button>
        {(user.role === 'publisher' || user.role === 'admin') && <button className="document-rename"
          aria-label={`Переименовать ${entry.title}`} title="Переименовать"
          onClick={() => renameDocument(entry)}>✎</button>}
      </div>)}
      <div className="publish-card"><b>Публикация</b><p>В приложение попадает только опубликованный комплект.</p>
        {(user.role === 'publisher' || user.role === 'admin') && <button className="primary" onClick={publish} disabled={publishing || !collaboration.ready}>{publishing ? 'Собираем PDF…' : 'Опубликовать 4 PDF'}</button>}
        {lastRelease && <small>Последний релиз: {lastRelease.releaseId}</small>}</div>
    </aside>
    <main className="workspace">
      <div className="toolbar">
        <button title="Отменить (Ctrl+Z)" onClick={collaboration.undo} disabled={!collaboration.canUndo}>↶</button>
        <button title="Повторить (Ctrl+Y)" onClick={collaboration.redo} disabled={!collaboration.canRedo}>↷</button>
        <span className="toolbar-divider" />
        <button onClick={() => add('text')} disabled={!collaboration.ready}>＋ Текст</button>
        <button onClick={() => { replaceImageRef.current = null; fileRef.current?.click() }} disabled={!collaboration.ready}>＋ Изображение</button>
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(event) => { upload(event.target.files?.[0]); event.target.value = '' }} />
        <button onClick={() => docxRef.current?.click()} disabled={!collaboration.ready}>Импорт таблицы Word</button>
        <input ref={docxRef} type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" hidden
          onChange={(event) => { importWordTable(event.target.files?.[0]); event.target.value = '' }} />
        <select className="toolbar-select" value="" aria-label="Добавить фигуру" onChange={(event) => { if (event.target.value) add('shape', { shape: event.target.value, w: .28, h: event.target.value === 'line' ? .03 : .2 }); event.target.value = '' }}>
          <option value="">＋ Фигура</option><option value="rectangle">Прямоугольник</option><option value="ellipse">Эллипс</option><option value="line">Линия</option>
        </select>
        <button onClick={() => add('cover')} disabled={!collaboration.ready}>＋ Маска</button>
        <span className="toolbar-divider" />
        <button onClick={duplicate} disabled={!item || item.locked} title={item?.locked ? 'Сначала разблокируйте положение' : 'Ctrl+D'}>Дублировать</button>
        <button className="danger-button" onClick={remove} disabled={!item || item.locked} title={item?.locked ? 'Сначала разблокируйте положение' : 'Delete'}>Удалить</button>
        <select className="toolbar-select" value="" aria-label="Очистка документа" onChange={(event) => { const action = event.target.value; event.target.value = ''; if (action === 'blank-page') blankPage(); if (action === 'reset-page') resetPage(); if (action === 'blank-document') blankDocument() }}>
          <option value="">Очистить…</option><option value="blank-page">Текущую страницу до белого листа</option><option value="reset-page">Вернуть шаблон на странице</option><option value="blank-document">Создать пустой документ</option>
        </select>
        <button onClick={createLayout} disabled={!collaboration.ready}>Новый редактируемый макет</button>
        <button onClick={applyTemplate} disabled={!collaboration.ready}>Вернуть общий шаблон</button>
        {(user.role === 'publisher' || user.role === 'admin') && <button onClick={() => saveTemplate()} disabled={!collaboration.ready || templateSaving}>{templateSaving ? 'Синхронизация…' : 'Сохранить общий шаблон'}</button>}
        {pageBackground && <label className="page-color" title="Цвет чистой страницы">Фон <input type="color" value={pageBackground.color || '#ffffff'} onChange={(event) => change(activePage, pageBackground.id, { color: event.target.value })} /></label>}
        <button onClick={openHistory}>История</button>
        <button onClick={exportPdf} disabled={exporting || !collaboration.ready}>{exporting ? 'Готовим PDF…' : 'Скачать PDF'}</button>
        {(user.role === 'publisher' || user.role === 'admin') && <button className="primary" onClick={publish} disabled={publishing || !collaboration.ready}>{publishing ? 'Собираем PDF…' : 'Опубликовать'}</button>}
        <span className="toolbar-spacer" /><span className={`status ${collaboration.status.includes('Офлайн') ? 'dirty' : ''}`}>{collaboration.status}</span>
      </div>
      {item && <div className="properties"><b>{item.type === 'text' ? 'Текст' : item.type === 'image' ? 'Изображение' : adjustableHorizontal ? 'Горизонтальная линия' : adjustableVertical ? 'Вертикальная линия' : item.type === 'shape' ? 'Фигура' : 'Маска'}</b>
        {item.type === 'text' && <>
          <label>Единый шрифт<select value={item.fontFamily || 'Times New Roman'} onChange={(event) => collaboration.changeAllText({ fontFamily: event.target.value })}>{FONT_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>Размер<input type="number" min="6" max="240" value={item.fontSize} onChange={(event) => change(selected.page, item.id, { fontSize: Number(event.target.value) })} /></label>
          <label title="Цвет текста">Текст<input type="color" value={item.color} onChange={(event) => change(selected.page, item.id, { color: event.target.value })} /></label>
          <button className={item.bold ? 'active-tool' : ''} onClick={() => change(selected.page, item.id, { bold: !item.bold })}><b>Ж</b></button>
          <button className={item.italic ? 'active-tool' : ''} onClick={() => change(selected.page, item.id, { italic: !item.italic })}><i>К</i></button>
          <label>Выравнивание<select value={item.align || 'left'} onChange={(event) => change(selected.page, item.id, { align: event.target.value })}><option value="left">Слева</option><option value="center">По центру</option><option value="right">Справа</option><option value="justify">По ширине</option></select></label>
          <label title="Фон текстового блока">Подложка<input type="color" value={item.background === 'transparent' ? '#ffffff' : item.background} onChange={(event) => change(selected.page, item.id, { background: event.target.value })} /></label>
          <button onClick={() => change(selected.page, item.id, { background: 'transparent' })}>Без подложки</button>
        </>}
        {item.type === 'image' && <>
          <span>Позиция {item.scanCode || item.sequence || item.cardIndex}{item.sourceLabel ? ` · ${item.sourceLabel}` : ''}</span>
          <label>Размещение<select value={item.fit || 'contain'} onChange={(event) => change(selected.page, item.id, { fit: event.target.value })}><option value="contain">Вписать</option><option value="cover">Заполнить</option></select></label>
          <button onClick={() => { replaceImageRef.current = selected; fileRef.current?.click() }}>Заменить файл</button>
        </>}
        {item.type === 'shape' && <>
          {!adjustableLine && <label>Фигура<select value={item.shape || 'rectangle'} onChange={(event) => change(selected.page, item.id, { shape: event.target.value })}><option value="rectangle">Прямоугольник</option><option value="ellipse">Эллипс</option><option value="line">Линия</option></select></label>}
          {!['line', 'vertical-line'].includes(item.shape) && <label>Заливка<input type="color" value={item.fill === 'transparent' ? '#ffffff' : item.fill} onChange={(event) => change(selected.page, item.id, { fill: event.target.value })} /></label>}
          {!['line', 'vertical-line'].includes(item.shape) && <button onClick={() => change(selected.page, item.id, { fill: 'transparent' })}>Без заливки</button>}
          <label>Контур<input type="color" value={item.stroke || '#111111'} onChange={(event) => change(selected.page, item.id, { stroke: event.target.value })} /></label>
          <label>Толщина<input type="number" min="0.25" max="20" step="0.25" value={item.strokeWidth ?? 1} onChange={(event) => change(selected.page, item.id, { strokeWidth: Number(event.target.value) })} /></label>
          <label>Вид штриха<select value={item.strokeStyle || 'solid'} onChange={(event) => change(selected.page, item.id, { strokeStyle: event.target.value })}>{STROKE_STYLE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          {adjustableHorizontal && <span className="property-hint">Перетаскивание двигает линию вверх/вниз; круглые маркеры меняют её длину. Изменение повторяется на всех разворотах.</span>}
          {adjustableVertical && <span className="property-hint">Перетаскивание двигает линию влево/вправо; круглые маркеры меняют её длину. Изменение повторяется на всех разворотах.</span>}
        </>}
        {item.type === 'cover' && <label>Цвет маски<input type="color" value={item.color} onChange={(event) => change(selected.page, item.id, { color: event.target.value })} /></label>}
        {item.type !== 'page-background' && <button onClick={toggleItemLock} disabled={templateSaving}>{adjustableLine ? (item.locked ? 'Разблокировать и перемещать' : (templateSaving ? 'Синхронизация…' : 'Зафиксировать и синхронизировать')) : (item.locked ? 'Разблокировать положение' : 'Закрепить положение')}</button>}
      </div>}
      {(error || collaboration.error) && <div className="error-banner">{error || collaboration.error}</div>}
      {notice && !error && !collaboration.error && <div className="notice-banner">{notice}</div>}
      {collaboration.ready ? <PdfPages pages={collaboration.pages} selected={selected} onSelect={select} onChange={change} /> : <div className="empty-state">Подключаем совместный документ…</div>}
    </main>
    {history && <div className="dialog-backdrop" onMouseDown={() => setHistory(null)}><section className="dialog history-dialog" onMouseDown={(event) => event.stopPropagation()}><header><div><h2>История документа</h2><p>Восстановление станет общим для всех медиаторов</p></div><button onClick={() => setHistory(null)}>Закрыть</button></header><div className="history-list">{history.length ? history.map((entry) => <button key={entry.revision} onClick={() => restore(entry.revision)}><b>Версия {entry.revision}</b><span>{new Date(entry.createdAt).toLocaleString('ru-RU')}</span><small>{entry.createdBy}</small></button>) : <p>Сохранённых версий пока нет.</p>}</div></section></div>}
    {usersOpen && <UserDialog currentUser={user} onClose={() => setUsersOpen(false)} />}
  </div>
}
