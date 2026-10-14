const TOKEN_KEY = 'postcards-studio-token'

export const session = {
  get token() { return localStorage.getItem(TOKEN_KEY) || '' },
  set token(value) { value ? localStorage.setItem(TOKEN_KEY, value) : localStorage.removeItem(TOKEN_KEY) },
}

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {})
  if (session.token) headers.set('Authorization', `Bearer ${session.token}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(path, { ...options, headers })
  const type = response.headers.get('content-type') || ''
  const value = type.includes('json') ? await response.json() : await response.text()
  if (!response.ok) {
    const detail = typeof value === 'object' ? value.detail : value
    const message = typeof detail === 'object' ? detail.message : detail
    const error = new Error(message || `HTTP ${response.status}`)
    error.status = response.status
    error.payload = value
    throw error
  }
  return value
}

export function authHeaders() {
  return session.token ? { Authorization: `Bearer ${session.token}` } : {}
}

export function websocketUrl(projectId) {
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${location.host}/ws/projects/${projectId}?token=${encodeURIComponent(session.token)}`
}

export function collaborationUrl() {
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${location.host}/collaboration`
}
