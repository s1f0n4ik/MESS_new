import { apiUrl } from '../net/urls'

/** Клиент сообщает координатору, что сделал — попадает в единый журнал. */
export function reportClient(serverHost, role, tag, extra = {}) {
  try {
    fetch(apiUrl('/api/log/client', serverHost), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role, tag, ...extra }),
      keepalive: true,
    }).catch(() => {})
  } catch {}
}