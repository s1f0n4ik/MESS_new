import { loadLocalSettings, saveLocalSettings } from './localSettings'

/**
 * Аргументы командной строки (--role, --server) приходят в query главного окна.
 * Приоритет у них выше сохранённых настроек: ярлык на стенде — источник истины,
 * иначе после переноса машины останется старый адрес координатора.
 */
export function bootstrapFromArgs() {
  const qs = new URLSearchParams(window.location.search)
  const role = qs.get('role')
  const server = qs.get('server')
  if (!role && !server) return

  const current = loadLocalSettings()
  const next = { ...current }
  if (role) next.role = role
  if (server) next.serverHost = server

  if (next.role !== current.role || next.serverHost !== current.serverHost) {
    saveLocalSettings(next)
    console.log('[bootstrap] role=%s server=%s', next.role, next.serverHost)
  }
}