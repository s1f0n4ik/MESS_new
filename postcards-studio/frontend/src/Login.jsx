import { useState } from 'react'
import { api, session } from './api'

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('admin@mess-studio.ru')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const value = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
      session.token = value.token
      onLogin(value.user)
    } catch (reason) { setError(reason.message) } finally { setBusy(false) }
  }

  return <main className="login-shell">
    <form className="login-card" onSubmit={submit}>
      <div className="brand-mark">P</div>
      <h1>Postcards Studio</h1>
      <p>Общий редактор документов инсталляции</p>
      <label>Электронная почта<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
      <label>Пароль<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
      {error && <div className="alert">{error}</div>}
      <button className="primary" disabled={busy}>{busy ? 'Входим…' : 'Войти'}</button>
    </form>
  </main>
}

