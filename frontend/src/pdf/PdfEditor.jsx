import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiUrl } from '../net/urls'
import { serverOrigin } from '../net/origin'

const emptyDocument = (slot) => ({ schemaVersion: 1, slot, revision: 0, updatedAt: null, updatedBy: null, pages: {} })
const makeId = () => `e${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`

export function usePdfEditor(slot, serverHost, externalRevision, updatedBy) {
  const [doc, setDoc] = useState(() => emptyDocument(slot))
  const [editMode, setEditMode] = useState(false)
  const [selected, setSelected] = useState(null)
  const [activePage, setActivePage] = useState(1)
  const [dirty, setDirty] = useState(false)
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [saveBlocked, setSaveBlocked] = useState(false)
  const [history, setHistory] = useState([])
  const [archiveDir, setArchiveDir] = useState('')
  const [archiveInput, setArchiveInput] = useState('')
  const [archiveSource, setArchiveSource] = useState('local')
  const savingRef = useRef(false)
  const docRef = useRef(doc)
  const dirtyRef = useRef(dirty)
  useEffect(() => { docRef.current = doc }, [doc])
  useEffect(() => { dirtyRef.current = dirty }, [dirty])

  const load = useCallback(async () => {
    if (!slot) return
    setStatus('loading')
    setError('')
    try {
      const response = await fetch(apiUrl(`/api/pdf-editor/${slot}`, serverHost))
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const value = await response.json()
      setDoc(value)
      setDirty(false)
      setSaveBlocked(false)
      setSelected(null)
      setStatus('saved')
    } catch (e) {
      setStatus('error')
      setError(`Редактор недоступен: ${e.message}`)
    }
  }, [slot, serverHost])

  useEffect(() => { setEditMode(false); setActivePage(1); load() }, [load])

  // Пока никто не редактирует, показываем сохранение с другого компьютера.
  useEffect(() => {
    if (!editMode && externalRevision != null && Number(externalRevision) !== Number(docRef.current.revision)) load()
  }, [externalRevision, editMode, load])

  const saveNow = useCallback(async () => {
    if (!slot || savingRef.current || !dirty) return true
    if (saveBlocked) return false
    savingRef.current = true
    setDirty(false)
    setStatus('saving')
    setError('')
    const sent = docRef.current
    try {
      const response = await fetch(apiUrl(`/api/pdf-editor/${slot}`, serverHost), {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseRevision: sent.revision, updatedBy, pages: sent.pages }),
      })
      const value = await response.json()
      if (response.status === 409) {
        setDirty(true)
        setSaveBlocked(true)
        throw new Error('Документ изменён на другом компьютере. Завершите работу там или нажмите «Обновить».')
      }
      if (!response.ok) throw new Error(value?.detail || `HTTP ${response.status}`)
      setDoc((current) => ({ ...current, revision: value.revision, updatedAt: value.updatedAt, updatedBy: value.updatedBy }))
      setStatus('saved')
      return true
    } catch (e) {
      setStatus('error')
      setError(e.message)
      return false
    } finally {
      savingRef.current = false
    }
  }, [dirty, saveBlocked, serverHost, slot, updatedBy])

  useEffect(() => {
    if (!editMode || !dirty || saveBlocked) return undefined
    const timer = setTimeout(saveNow, 900)
    return () => clearTimeout(timer)
  }, [dirty, editMode, saveBlocked, saveNow])

  // Нативное PDF-окно может закрыться MIDI-командой. keepalive-запрос
  // сохраняет последнюю правку даже при уничтожении WebView.
  useEffect(() => {
    const flush = () => {
      const current = docRef.current
      if (!dirtyRef.current || !slot || saveBlocked) return
      fetch(apiUrl(`/api/pdf-editor/${slot}`, serverHost), {
        method: 'PUT', keepalive: true, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseRevision: current.revision, updatedBy, pages: current.pages }),
      }).catch(() => {})
    }
    window.addEventListener('pagehide', flush)
    return () => { window.removeEventListener('pagehide', flush); flush() }
  }, [saveBlocked, serverHost, slot, updatedBy])

  const mutatePages = useCallback((fn) => {
    setDoc((current) => ({ ...current, pages: fn(current.pages || {}) }))
    setDirty(true)
    setError('')
  }, [])

  const add = useCallback((type, extra = {}) => {
    const item = {
      id: makeId(), type, x: 0.12, y: 0.12, w: type === 'text' ? 0.48 : 0.3,
      h: type === 'text' ? 0.12 : 0.25,
      ...(type === 'text' ? { text: 'Новый текст', fontSize: 28, color: '#111111', background: 'transparent', align: 'left', bold: false } : {}),
      ...(type === 'cover' ? { color: '#ffffff' } : {}), ...extra,
    }
    mutatePages((pages) => ({ ...pages, [activePage]: [...(pages[activePage] || []), item] }))
    setSelected({ page: activePage, id: item.id })
  }, [activePage, mutatePages])

  const update = useCallback((page, id, patch) => {
    setActivePage(Number(page))
    mutatePages((pages) => ({ ...pages, [page]: (pages[page] || []).map((item) => item.id === id ? { ...item, ...patch } : item) }))
  }, [mutatePages])

  const removeSelected = useCallback(() => {
    if (!selected) return
    mutatePages((pages) => ({ ...pages, [selected.page]: (pages[selected.page] || []).filter((item) => item.id !== selected.id) }))
    setSelected(null)
  }, [mutatePages, selected])

  const moveLayer = useCallback((direction) => {
    if (!selected) return
    mutatePages((pages) => {
      const list = [...(pages[selected.page] || [])]
      const index = list.findIndex((item) => item.id === selected.id)
      if (index < 0) return pages
      const target = direction > 0 ? Math.min(list.length - 1, index + 1) : Math.max(0, index - 1)
      const [item] = list.splice(index, 1)
      list.splice(target, 0, item)
      return { ...pages, [selected.page]: list }
    })
  }, [mutatePages, selected])

  useEffect(() => {
    if (!editMode) return undefined
    const onKey = (e) => {
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target?.tagName || '')) return
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); removeSelected() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [editMode, removeSelected])

  const uploadImage = useCallback(async (file) => {
    if (!file) return
    setStatus('uploading')
    try {
      const response = await fetch(apiUrl(`/api/pdf-editor/${slot}/assets?filename=${encodeURIComponent(file.name)}`, serverHost), {
        method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file,
      })
      const value = await response.json()
      if (!response.ok) throw new Error(value?.detail || `HTTP ${response.status}`)
      add('image', { src: value.url, fit: 'contain' })
      setStatus('changed')
    } catch (e) { setStatus('error'); setError(e.message) }
  }, [add, serverHost, slot])

  const loadHistory = useCallback(async () => {
    try {
      const response = await fetch(apiUrl(`/api/pdf-editor/${slot}/history`, serverHost))
      const value = await response.json()
      setHistory(value.items || [])
      setArchiveDir(value.archiveDir || '')
      setArchiveInput(value.archiveDir || '')
      setArchiveSource(value.archiveSource || 'local')
    } catch (e) { setError(e.message) }
  }, [serverHost, slot])

  const saveArchivePath = useCallback(async () => {
    try {
      const response = await fetch(apiUrl('/api/pdf-editor/config', serverHost), {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: archiveInput }),
      })
      const value = await response.json()
      if (!response.ok) throw new Error(value?.detail || `HTTP ${response.status}`)
      setArchiveDir(value.effectivePath || '')
      setArchiveInput(value.path || '')
      setArchiveSource(value.source || 'config')
      setError('')
    } catch (e) { setError(e.message) }
  }, [archiveInput, serverHost])

  const restore = useCallback(async (revision) => {
    const response = await fetch(apiUrl(`/api/pdf-editor/${slot}/history/${revision}`, serverHost))
    const value = await response.json()
    if (!response.ok) { setError(value?.detail || `HTTP ${response.status}`); return }
    setDoc((current) => ({ ...current, pages: value.pages || {} }))
    setSelected(null)
    setDirty(true)
  }, [serverHost, slot])

  const select = useCallback((page, id) => {
    if (page) setActivePage(Number(page))
    setSelected(id ? { page: Number(page), id } : null)
  }, [])

  const selectedItem = useMemo(() => selected ? (doc.pages?.[selected.page] || []).find((x) => x.id === selected.id) : null,
    [doc.pages, selected])

  const exitEdit = useCallback(async () => {
    const ok = await saveNow()
    if (ok) { setEditMode(false); setSelected(null) }
    return ok
  }, [saveNow])

  return {
    doc, editMode, setEditMode, selected, selectedItem, activePage, setActivePage,
    dirty, status, error, saveBlocked, add, update, removeSelected, moveLayer, uploadImage,
    saveNow, exitEdit, load, history, archiveDir, archiveInput, setArchiveInput,
    archiveSource, saveArchivePath, loadHistory, restore, select,
    assetOrigin: serverOrigin(serverHost),
  }
}

function dateLabel(value) {
  if (!value) return 'ещё не сохранялся'
  try { return new Date(value).toLocaleString('ru-RU') } catch { return value }
}

export function PdfEditorToolbar({ editor }) {
  const fileRef = useRef(null)
  const [showHistory, setShowHistory] = useState(false)
  const item = editor.selectedItem
  const updateItem = (patch) => item && editor.update(editor.selected.page, item.id, patch)

  if (!editor.editMode) {
    return (
      <div className="pdf-editor-bar">
        <button className="pdf-editor-primary" onClick={() => editor.setEditMode(true)}>✎ Изменить</button>
        <span>Версия {editor.doc.revision || 0} · {dateLabel(editor.doc.updatedAt)}</span>
        {editor.error && <span className="pdf-editor-error">{editor.error}</span>}
      </div>
    )
  }

  return (
    <>
      <div className="pdf-editor-bar pdf-editor-bar--editing">
        <button onClick={() => editor.add('text')}>＋ Текст</button>
        <button onClick={() => fileRef.current?.click()}>＋ Изображение</button>
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden
          onChange={(e) => { editor.uploadImage(e.target.files?.[0]); e.target.value = '' }} />
        <button onClick={() => editor.add('cover')} title="Белая область закрывает старый текст или изображение">▭ Скрыть фрагмент</button>
        <button onClick={() => editor.moveLayer(-1)} disabled={!item}>↓ Слой</button>
        <button onClick={() => editor.moveLayer(1)} disabled={!item}>↑ Слой</button>
        <button onClick={editor.removeSelected} disabled={!item}>Удалить</button>
        <button onClick={() => { setShowHistory((v) => !v); editor.loadHistory() }}>История</button>
        <span className={`pdf-editor-status pdf-editor-status--${editor.status}`}>
          {editor.status === 'saving' ? 'Сохраняем…' : editor.dirty ? 'Есть изменения…' : `Сохранено ${dateLabel(editor.doc.updatedAt)}`}
        </span>
        <button onClick={editor.exitEdit} className="pdf-editor-primary">Готово</button>
      </div>
      {item && (
        <div className="pdf-editor-properties">
          <b>{item.type === 'text' ? 'Текст' : item.type === 'image' ? 'Изображение' : 'Маска'}</b>
          {item.type === 'text' && <>
            <label>Размер <input type="number" min="6" max="240" value={item.fontSize || 28}
              onChange={(e) => updateItem({ fontSize: Number(e.target.value) })} /></label>
            <label>Цвет <input type="color" value={item.color || '#111111'} onChange={(e) => updateItem({ color: e.target.value })} /></label>
            <label>Фон <input type="color" value={item.background === 'transparent' ? '#ffffff' : item.background}
              onChange={(e) => updateItem({ background: e.target.value })} /></label>
            <button onClick={() => updateItem({ background: 'transparent' })}>Без фона</button>
            <button className={item.bold ? 'is-active' : ''} onClick={() => updateItem({ bold: !item.bold })}>Жирный</button>
            <select value={item.align || 'left'} onChange={(e) => updateItem({ align: e.target.value })}>
              <option value="left">По левому краю</option><option value="center">По центру</option><option value="right">По правому краю</option>
            </select>
          </>}
          {item.type === 'cover' && <label>Цвет <input type="color" value={item.color || '#ffffff'} onChange={(e) => updateItem({ color: e.target.value })} /></label>}
          {item.type === 'image' && <select value={item.fit || 'contain'} onChange={(e) => updateItem({ fit: e.target.value })}>
            <option value="contain">Вписать целиком</option><option value="cover">Заполнить область</option>
          </select>}
        </div>
      )}
      {showHistory && (
        <div className="pdf-editor-history">
          <b>Автоматические версии</b>
          <div className="pdf-editor-archive-config">
            <label>Папка архива / NAS
              <input value={editor.archiveInput} disabled={editor.archiveSource === 'environment'}
                placeholder={'Например: \\\\NAS\\Postcards\\versions'}
                onChange={(e) => editor.setArchiveInput(e.target.value)} />
            </label>
            <button disabled={editor.archiveSource === 'environment'} onClick={editor.saveArchivePath}>Сохранить путь</button>
          </div>
          <span className="pdf-editor-history__path">Фактически: {editor.archiveDir}</span>
          {editor.history.length ? editor.history.map((version) => (
            <button key={version.revision} onClick={() => editor.restore(version.revision)}>
              Версия {version.revision} · {dateLabel(version.updatedAt)} · {version.updatedBy}
            </button>
          )) : <span>Предыдущих версий пока нет</span>}
        </div>
      )}
      {editor.error && <div className="pdf-editor-error pdf-editor-error--block">{editor.error} <button onClick={editor.load}>Обновить</button></div>}
    </>
  )
}
