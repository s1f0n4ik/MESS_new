import { getLocalSetting, saveLocalSettings } from '../settings/localSettings'

const VALID = /^pc[1-4]$/

export function getRole() {
  const stored = getLocalSetting('role', '')
  if (VALID.test(stored || '')) return stored

  const q = new URLSearchParams(location.search).get('role')
  if (VALID.test(q || '')) return q

  return 'pc1'
}

export function setRole(role) {
  if (!VALID.test(role)) return
  saveLocalSettings({ role })
  location.reload()
}

export const ROLES_LIST = ['pc1', 'pc2', 'pc3', 'pc4']