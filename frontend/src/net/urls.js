export function normalizeServerHost(value) {
  return String(value || '').trim()
}

export function httpBase(serverHost) {
  const host = normalizeServerHost(serverHost)
  if (!host) return ''
  if (/^https?:\/\//i.test(host)) return host.replace(/\/+$/, '')
  return `${window.location.protocol}//${host}`
}

export function apiUrl(path, serverHost) {
  return `${httpBase(serverHost)}${path}`
}

export function wsUrl(serverHost) {
  const host = normalizeServerHost(serverHost)
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  if (!host) return `${proto}://${window.location.host}/ws`
  if (/^wss?:\/\//i.test(host)) return `${host.replace(/\/+$/, '')}/ws`
  if (/^https?:\/\//i.test(host)) {
    const base = new URL(host)
    base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${base.toString().replace(/\/+$/, '')}/ws`
  }
  return `${proto}://${host}/ws`
}

// Просмотрщик без своего интерфейса — для инсталляции обязательно.
const PDF_VIEW_PARAMS = 'toolbar=0&navpanes=0&scrollbar=0&view=FitH'

export function pdfUrl(file, serverHost) {
  if (!file) return ''
  return `${httpBase(serverHost)}/pdfs/${encodeURIComponent(file)}#${PDF_VIEW_PARAMS}`
}