import { useEffect, useState } from 'react'
import { api, session } from './api'
import Editor from './Editor'
import Login from './Login'
import Mediations from './Mediations'

export default function App() {
  const [user, setUser] = useState(null)
  const [project, setProject] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(Boolean(session.token))
  const mediation = new URLSearchParams(window.location.search).get('mediation')
  const loadProject = async (projects) => {
    const requested = /^\d+$/.test(mediation || '') ? Number(mediation) : projects[0]?.id
    if (requested) setProject(await api(`/api/projects/${requested}`))
  }

  useEffect(() => {
    if (!session.token) return
    Promise.all([api('/api/me'), api('/api/projects')]).then(async ([person, projects]) => {
      setUser(person); await loadProject(projects)
    }).catch(e => { if (e.status === 401) { session.token = ''; setUser(null) } else setError(e.message) }).finally(() => setLoading(false))
  }, [])

  const loggedIn = async (person) => {
    setUser(person)
    try { const projects = await api('/api/projects'); await loadProject(projects) }
    catch (e) { setError(e.message) }
  }
  const logout = () => { session.token = ''; setUser(null); setProject(null); setError('') }
  if (loading) return <div className="empty-state">Открываем Postcards Studio…</div>
  if (!user) return <Login onLogin={loggedIn} />
  if (error) return <main className="login-shell"><div className="login-card"><p>{error}</p><p>Проверьте, что вошли под учётной записью нужной медиации.</p><button onClick={logout}>Войти под другой учётной записью</button><a href="/">Открыть свои документы</a></div></main>
  if (mediation === 'list' || mediation === 'desktop') return <Mediations user={user} onLogout={logout} />
  if (!project) return <div className="empty-state">Загружаем проект…</div>
  return <Editor project={project} user={user} onLogout={logout} />
}

