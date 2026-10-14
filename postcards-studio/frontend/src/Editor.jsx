import { useEffect, useRef, useState } from 'react'
import { api, websocketUrl } from './api'
import { useCollaboration } from './collaboration'
import PdfPages from './PdfPages'
import UserDialog from './UserDialog'

const newId = () => `e${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`

export default function Editor({ project, user, onLogout }) {
  const [slot, setSlot] = useState('pdf1')
  const [selected, setSelected] = useState(null)
  const [activePage, setActivePage] = useState(1)
  const [error, setError] = useState('')
  const [publishing, setPublishing] = useState(false)
  const [lastRelease, setLastRelease] = useState(null)
  const [history, setHistory] = useState(null)
  const [usersOpen, setUsersOpen] = useState(false)
  const [revision, setRevision] = useState(project.documents.find((value) => value.slot === slot)?.revision || 0)
  const fileRef = useRef(null)
  const collaboration = useCollaboration(project.id, slot, user)

  useEffect(() => {
    setSelected(null); setError(''); setRevision(project.documents.find((value) => value.slot === slot)?.revision || 0)
  }, [project.documents, slot])

  useEffect(() => {
    const socket = new WebSocket(websocketUrl(project.id))
    socket.onopen = () => socket.send('ready')
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data)
      if (message.type === 'document.saved' && message.slot === slot) setRevision(message.revision)
      if (message.type === 'release.published') setLastRelease(message.release)
    }
    return () => socket.close()
  }, [project.id, slot])

  const select = (page, id) => { setActivePage(page); setSelected(id ? { page, id } : null) }
  const change = (page, id, patch) => collaboration.change(page, id, patch)
  const add = (type, extra = {}) => {
    const item = { id: newId(), type, x: .1, y: .1, w: type === 'text' ? .48 : .3, h: type === 'text' ? .13 : .25,
      ...(type === 'text' ? { text: 'Новый текст', fontSize: 28, color: '#111111', background: 'transparent', align: 'left', bold: false } : {}),
      ...(type === 'cover' ? { color: '#ffffff' } : {}), ...extra }
    collaboration.add(activePage, item); setSelected({ page: activePage, id: item.id })
  }
  const remove = () => { if (!selected) return; collaboration.remove(selected.page, selected.id); setSelected(null) }
  const item = selected ? (collaboration.pages?.[selected.page] || []).find((value) => value.id === selected.id) : null

  const upload = async (file) => {
    if (!file) return
    const data = new FormData(); data.append('file', file)
    try { const value = await api(`/api/projects/${project.id}/assets`, { method: 'POST', body: data }); add('image', { src: value.url, fit: 'contain' }) }
    catch (reason) { setError(reason.message) }
  }

  const publish = async () => {
    setPublishing(true); setError('')
    try {
      const saved = await api(`/api/projects/${project.id}/documents/${slot}/collaboration-snapshot`, {
        method: 'POST', body: JSON.stringify({ pages: collaboration.snapshot() }),
      })
      setRevision(saved.revision)
      const value = await api(`/api/projects/${project.id}/publish`, { method: 'POST' })
      setLastRelease(value)
    } catch (reason) { setError(reason.message) } finally { setPublishing(false) }
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
      {project.documents.map((entry) => <button key={entry.slot} className={slot === entry.slot ? 'active' : ''}
        onClick={() => setSlot(entry.slot)}><b>{entry.title}</b><small>{slot === entry.slot ? `Версия ${revision} · совместно` : `Версия ${entry.revision}`}</small></button>)}
      <div className="publish-card"><b>Публикация</b><p>В приложение попадает только опубликованный комплект.</p>
        {(user.role === 'publisher' || user.role === 'admin') && <button className="primary" onClick={publish} disabled={publishing || !collaboration.ready}>{publishing ? 'Собираем PDF…' : 'Опубликовать 4 PDF'}</button>}
        {lastRelease && <small>Последний релиз: {lastRelease.releaseId}</small>}</div>
    </aside>
    <main className="workspace">
      <div className="toolbar">
        <button onClick={() => add('text')} disabled={!collaboration.ready}>＋ Текст</button><button onClick={() => fileRef.current?.click()} disabled={!collaboration.ready}>＋ Изображение</button>
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(event) => { upload(event.target.files?.[0]); event.target.value = '' }} />
        <button onClick={() => add('cover')} disabled={!collaboration.ready}>＋ Маска</button><button onClick={remove} disabled={!item}>Удалить</button><button onClick={openHistory}>История</button>
        {(user.role === 'publisher' || user.role === 'admin') && <button className="primary" onClick={publish} disabled={publishing || !collaboration.ready}>{publishing ? 'Собираем PDF…' : 'Опубликовать'}</button>}
        <span className="toolbar-spacer" /><span className={`status ${collaboration.status.includes('Офлайн') ? 'dirty' : ''}`}>{collaboration.status}</span>
      </div>
      {item && <div className="properties"><b>{item.type === 'text' ? 'Текст' : item.type === 'image' ? 'Изображение' : 'Маска'}</b>
        {item.type === 'text' && <><label>Размер<input type="number" min="6" max="240" value={item.fontSize} onChange={(event) => change(selected.page, item.id, { fontSize: Number(event.target.value) })} /></label><label>Цвет<input type="color" value={item.color} onChange={(event) => change(selected.page, item.id, { color: event.target.value })} /></label><button onClick={() => change(selected.page, item.id, { bold: !item.bold })}>Жирный</button></>}
        {item.type === 'image' && <select value={item.fit} onChange={(event) => change(selected.page, item.id, { fit: event.target.value })}><option value="contain">Вписать</option><option value="cover">Заполнить</option></select>}
        {item.type === 'cover' && <input type="color" value={item.color} onChange={(event) => change(selected.page, item.id, { color: event.target.value })} />}
      </div>}
      {(error || collaboration.error) && <div className="error-banner">{error || collaboration.error}</div>}
      {collaboration.ready ? <PdfPages pages={collaboration.pages} selected={selected} onSelect={select} onChange={change} /> : <div className="empty-state">Подключаем совместный документ…</div>}
    </main>
    {history && <div className="dialog-backdrop" onMouseDown={() => setHistory(null)}><section className="dialog history-dialog" onMouseDown={(event) => event.stopPropagation()}><header><div><h2>История документа</h2><p>Восстановление станет общим для всех медиаторов</p></div><button onClick={() => setHistory(null)}>Закрыть</button></header><div className="history-list">{history.length ? history.map((entry) => <button key={entry.revision} onClick={() => restore(entry.revision)}><b>Версия {entry.revision}</b><span>{new Date(entry.createdAt).toLocaleString('ru-RU')}</span><small>{entry.createdBy}</small></button>) : <p>Сохранённых версий пока нет.</p>}</div></section></div>}
    {usersOpen && <UserDialog onClose={() => setUsersOpen(false)} />}
  </div>
}
