import { useEffect, useState } from 'react'
import { api } from './api'

export default function UserDialog({ currentUser, onClose }) {
  const [users, setUsers] = useState([])
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'editor' })
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState(null)
  const load = () => api('/api/users').then(setUsers).catch((reason) => setError(reason.message))
  useEffect(() => { load() }, [])
  const create = async (event) => {
    event.preventDefault(); setError('')
    try {
      await api('/api/users', { method: 'POST', body: JSON.stringify(form) })
      setForm({ name: '', email: '', password: '', role: 'editor' }); load()
    } catch (reason) { setError(reason.message) }
  }
  const remove = async (user) => {
    if (!window.confirm(`Удалить пользователя «${user.name}» (${user.email})? Он сразу потеряет доступ к редактору.`)) return
    setDeleting(user.id); setError('')
    try {
      await api(`/api/users/${user.id}`, { method: 'DELETE' })
      setUsers((current) => current.filter((value) => value.id !== user.id))
    } catch (reason) { setError(reason.message) } finally { setDeleting(null) }
  }
  return <div className="dialog-backdrop" onMouseDown={onClose}><section className="dialog" onMouseDown={(e) => e.stopPropagation()}>
    <header><div><h2>Медиаторы</h2><p>Доступ к общему проекту</p></div><button onClick={onClose}>Закрыть</button></header>
    <div className="user-list">{users.map((user) => <div key={user.id}><b>{user.name}</b><span>{user.email}</span><small>{user.role}</small>
      {user.id === currentUser?.id
        ? <button disabled title="Нельзя удалить текущую учётную запись">Вы</button>
        : <button className="user-delete" disabled={deleting === user.id} onClick={() => remove(user)}>{deleting === user.id ? 'Удаляем…' : 'Удалить'}</button>}
    </div>)}</div>
    <form onSubmit={create} className="user-form"><h3>Добавить пользователя</h3>
      <input placeholder="Имя" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
      <input type="email" placeholder="Почта" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
      <input type="password" placeholder="Пароль — минимум 10 символов" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} minLength="10" required />
      <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}><option value="editor">Медиатор</option><option value="publisher">Может публиковать</option><option value="admin">Администратор</option></select>
      <button className="primary">Создать</button>
    </form>{error && <div className="alert">{error}</div>}
  </section></div>
}
