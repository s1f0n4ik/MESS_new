import { useEffect, useState } from 'react'
import { api, session } from './api'
import Editor from './Editor'
import Login from './Login'

export default function App() {
  const [user, setUser] = useState(null)
  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(Boolean(session.token))

  useEffect(() => {
    if (!session.token) return
    Promise.all([api('/api/me'), api('/api/projects')]).then(async ([person, projects]) => {
      setUser(person); setProject(await api(`/api/projects/${projects[0].id}`))
    }).catch(() => { session.token = ''; setUser(null) }).finally(() => setLoading(false))
  }, [])

  const loggedIn = async (person) => {
    setUser(person); const projects = await api('/api/projects'); setProject(await api(`/api/projects/${projects[0].id}`))
  }
  const logout = () => { session.token = ''; setUser(null); setProject(null) }
  if (loading) return <div className="empty-state">Открываем Postcards Studio…</div>
  if (!user) return <Login onLogin={loggedIn} />
  if (!project) return <div className="empty-state">Загружаем проект…</div>
  return <Editor project={project} user={user} onLogout={logout} />
}

