const LOCAL_SETTINGS_KEY = 'postcards_local_settings_v1'

const DEFAULTS = {
  role: 'pc1',
  serverHost: '',
  audioEnabled: true,
  audioMonitorSinkId: '',
  audioVibroSinkId: '',
  vibroEnabled: false,
}

function normalize(raw = {}) {
  return {
    role: typeof raw.role === 'string' ? raw.role : DEFAULTS.role,
    serverHost: typeof raw.serverHost === 'string' ? raw.serverHost : DEFAULTS.serverHost,
    audioEnabled: typeof raw.audioEnabled === 'boolean' ? raw.audioEnabled : DEFAULTS.audioEnabled,
    audioMonitorSinkId:
      typeof raw.audioMonitorSinkId === 'string'
        ? raw.audioMonitorSinkId
        : DEFAULTS.audioMonitorSinkId,
    audioVibroSinkId:
      typeof raw.audioVibroSinkId === 'string'
        ? raw.audioVibroSinkId
        : DEFAULTS.audioVibroSinkId,
    vibroEnabled:
      typeof raw.vibroEnabled === 'boolean' ? raw.vibroEnabled : DEFAULTS.vibroEnabled,
  }
}

export function loadLocalSettings() {
  try {
    const raw = localStorage.getItem(LOCAL_SETTINGS_KEY)
    if (!raw) return { ...DEFAULTS }
    return normalize(JSON.parse(raw))
  } catch {
    return { ...DEFAULTS }
  }
}

export function saveLocalSettings(patch) {
  const prev = loadLocalSettings()
  const next = normalize({ ...prev, ...(patch || {}) })
  try {
    localStorage.setItem(LOCAL_SETTINGS_KEY, JSON.stringify(next))
  } catch {}
  return next
}

export function getLocalSetting(key, fallback = undefined) {
  const settings = loadLocalSettings()
  return settings[key] ?? fallback
}