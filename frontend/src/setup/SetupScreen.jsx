import { useEffect, useState } from 'react'

const ROLES = ['pc1', 'pc2', 'pc3', 'pc4']

export function SetupScreen() {
  const [role, setRole] = useState('pc1')
  const [serve, setServe] = useState(true)
  const [server, setServer] = useState('http://localhost:8787')
  const [admin, setAdmin] = useState(true)
  const [check, setCheck] = useState(null)
  const [busy, setBusy] = useState(false)

  // Координатор — это pc1 с сервером на localhost. Меняем одно — подстраиваем другое.
  useEffect(() => {
    if (serve) setServer('http://localhost:8787')
  }, [serve])

  const normalizedServer = () => {
    let s = server.trim()
    if (!/^https?:\/\//i.test(s)) s = `http://${s}`
    if (!/:\d+$/.test(s.replace(/\/+$/, ''))) s = `${s.replace(/\/+$/, '')}:8787`
    return s.replace(/\/+$/, '')
  }

  const testConnection = async () => {
    setCheck('…')
    try {
      const r = await fetch(`${normalizedServer()}/api/health`)
      setCheck(r.ok ? 'Координатор отвечает' : `HTTP ${r.status}`)
    } catch (e) {
      setCheck('Нет связи. Проверь адрес, сеть и файрвол на координаторе')
    }
  }

  const save = async () => {
    setBusy(true)
    const { invoke } = window.__TAURI__.core
    try {
      await invoke('save_launch_config', {
        config: { role, server: normalizedServer(), serve, admin, fullscreen: true },
      })
      await invoke('restart_app')
    } catch (e) {
      setBusy(false)
      setCheck(`Ошибка сохранения: ${e}`)
    }
  }

  const row = { display: 'flex', gap: 12, alignItems: 'center', margin: '14px 0' }
  const input = { fontSize: 18, padding: '8px 12px', background: '#222', color: '#eee', border: '1px solid #555' }

  return (
    <div style={{ position: 'fixed', inset: 0, background: '#111', color: '#eee',
      display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'system-ui' }}>
      <div style={{ width: 560 }}>
        <h1 style={{ fontWeight: 400 }}>Настройка этой машины</h1>
        <p style={{ color: '#aaa' }}>Выбор сохраняется и больше не спрашивается. Изменить можно из меню (M).</p>

        <div style={row}>
          <span style={{ width: 200 }}>Роль</span>
          <select value={role} onChange={(e) => setRole(e.target.value)} style={input}>
            {ROLES.map((r) => <option key={r} value={r}>{r.toUpperCase()}</option>)}
          </select>
        </div>

        <label style={row}>
          <input type="checkbox" checked={serve} onChange={(e) => setServe(e.target.checked)} />
          Эта машина — координатор (запускает сервер, к ней подключаются остальные)
        </label>

        <div style={row}>
          <span style={{ width: 200 }}>Адрес координатора</span>
          <input value={server} disabled={serve} onChange={(e) => setServer(e.target.value)}
            placeholder="192.168.1.50" style={{ ...input, flex: 1 }} />
          <button onClick={testConnection} style={input}>Проверить</button>
        </div>
        {check && <div style={{ color: '#ccc', marginLeft: 212 }}>{check}</div>}

        <label style={row}>
          <input type="checkbox" checked={admin} onChange={(e) => setAdmin(e.target.checked)} />
          Показывать меню администратора по клавише M
        </label>

        <button onClick={save} disabled={busy}
          style={{ ...input, marginTop: 24, background: '#2d6', color: '#000', fontWeight: 700, padding: '12px 24px' }}>
          {busy ? 'Перезапуск…' : 'Сохранить и запустить'}
        </button>
      </div>
    </div>
  )
}