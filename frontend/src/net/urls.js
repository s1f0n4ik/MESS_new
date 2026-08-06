// Внутри Tauri протокол страницы — tauri:, прокси нет, поэтому
// относительные пути и window.location.protocol использовать нельзя.
function isTauri() {
  return typeof window !== 'undefined' && !!window.__TAURI__
}

function pageProtocol() {
  const p = typeof window !== 'undefined' ? window.location.protocol : 'http:'
  return p === 'http:' || p === 'https:' ? p : 'http:'
}

export const DEFAULT_SERVER_HOST = 'http://localhost:8787'

export function normalizeServerHost(value) {
  const host = String(value || '').trim()
  if (host) return host
  // Браузер: пусто = относительные пути через vite-прокси (dev как раньше).
  // Tauri: прокси нет — нужен абсолютный адрес координатора.
  return isTauri() ? DEFAULT_SERVER_HOST : ''
}

export function httpBase(serverHost) {
  const host = normalizeServerHost(serverHost)
  if (!host) return ''
  if (/^https?:\/\//i.test(host)) return host.replace(/\/+$/, '')
  return `${pageProtocol()}//${host}`
}

export function apiUrl(path, serverHost) {
  return `${httpBase(serverHost)}${path}`
}

export function wsUrl(serverHost) {
  const host = normalizeServerHost(serverHost)
  const proto = pageProtocol() === 'https:' ? 'wss' : 'ws'
  if (!host) return `${proto}://${window.location.host}/ws`
  if (/^wss?:\/\//i.test(host)) return `${host.replace(/\/+$/, '')}/ws`
  if (/^https?:\/\//i.test(host)) {
    const base = new URL(host)
    base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${base.toString().replace(/\/+$/, '')}/ws`
  }
  return `${proto}://${host}/ws`
}

export function pdfUrl(file, serverHost, version) {
  const base = httpBase(serverHost)
  const v = version ? `?v=${encodeURIComponent(version)}` : ''
  return `${base}/pdfs/${encodeURIComponent(file)}${v}`
}