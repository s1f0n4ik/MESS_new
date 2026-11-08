import { useEffect, useState } from 'react'
import { api } from './api'

export function selectMediation(record) {
  window.parent.postMessage({ type: 'postcards:mediation', projectId: record.projectId, title: record.title }, '*')
  const query = new URLSearchParams(window.location.search)
  query.set('mediation', String(record.projectId))
  window.location.assign(`/?${query}`)
}

export default function Mediations({ user, onLogout }) {
  const [items, setItems] = useState([])
  const [title, setTitle] = useState(`Медиация ${new Date().toLocaleString('ru-RU')}`)
  const [credentials, setCredentials] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    api('/api/mediations').then(setItems).catch(e => setError(e.message))
    window.parent.postMessage({ type: 'postcards:mediation-state', busy: false }, '*')
  }, [])
  const create = async () => {
    setBusy(true); setError('')
    try {
      const record = await api('/api/mediations', { method: 'POST', body: JSON.stringify({ title,
        releaseId: new URLSearchParams(window.location.search).get('release') || '' }) })
      setCredentials(record); setItems(current => [record, ...current])
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <main className="mediation-list">
    <h1>Документ 4 · Медиации</h1>
    <p>У каждой медиации свой текст. Гости могут продолжить его по отдельному логину и паролю.</p>
    <p><a href="/">Общие документы</a> <button onClick={onLogout}>Выйти</button></p>
    {user.role !== 'mediation' && !credentials && <section>
      <label>Название медиации <input value={title} maxLength={160} onChange={e => setTitle(e.target.value)} /></label>
      <button className="primary" disabled={busy || !title.trim()} onClick={create}>{busy ? 'Создаём…' : 'Начать новую медиацию'}</button>
    </section>}
    {credentials && <section className="notice">
      <b>Доступ к этой медиации</b>
      <p>Сайт: {window.location.origin}</p>
      <p>Логин: <code>{credentials.login}</code></p><p>Пароль: <code>{credentials.password}</code></p>
      <p>Скопируйте пароль сейчас: повторно он не показывается. Этот доступ открывает только данную медиацию.</p>
      <button className="primary" onClick={() => selectMediation(credentials)}>Открыть документ</button>
      <button onClick={() => setCredentials(null)}>Пароль записан</button>
    </section>}
    {error && <p className="error-banner">{error}</p>}
    <h2>Сохранённые медиации</h2>
    {items.map(record => <section key={record.projectId}>
      <button onClick={() => selectMediation(record)}>{record.title} · версия {record.revision}</button>
      <small> Логин: {record.login} · {record.archive?.deliveryStatus === 'nas-sent' ? 'Архив отправлен на NAS' : 'Архив: по кнопке «Сохранить на NAS» в документе'}</small>
    </section>)}
    {!items.length && <p>Медиаций пока нет.</p>}
  </main>
}
