const LOCAL_SETTINGS_KEY = 'postcards_local_settings_v1'

const DEFAULTS = {
  role: 'pc1',
  serverHost: '',
  midiInputId: '',
  midiOutputId: '',
  midiFilterEnabled: true,
  midiFilterChannel: 2,
}

function normalize(raw = {}) {
  return {
    role: typeof raw.role === 'string' ? raw.role : DEFAULTS.role,
    serverHost: typeof raw.serverHost === 'string' ? raw.serverHost : DEFAULTS.serverHost,
    midiInputId: typeof raw.midiInputId === 'string' ? raw.midiInputId : DEFAULTS.midiInputId,
    midiOutputId: typeof raw.midiOutputId === 'string' ? raw.midiOutputId : DEFAULTS.midiOutputId,
    midiFilterEnabled:
      typeof raw.midiFilterEnabled === 'boolean'
        ? raw.midiFilterEnabled
        : DEFAULTS.midiFilterEnabled,
    midiFilterChannel: Number.isFinite(Number(raw.midiFilterChannel))
      ? Number(raw.midiFilterChannel)
      : DEFAULTS.midiFilterChannel,
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