const KEY = 'postcards_midi_map_v2'

export const MIDI_ACTIONS = [
  'launch',
  'toggle_force_open_all',
  'reset_scenario',
  'hard_reset',
  'minimize_all_windows',
  'open_pc1',
  'open_pc2',
  'open_pc3',
  'open_pc4',
  'close_pc1',
  'close_pc2',
  'close_pc3',
  'close_pc4',
]

export const LEGACY_CHANNEL = 2
export const LEGACY_OUTPUT_NOTE = 72
export const LEGACY_OUTPUT_VELOCITY = 100
export const LEGACY_OUTPUT_DURATION_MS = 180

export const LEGACY_MAPPING = [
  { channel: 2, note: 60, action: 'launch' },
  { channel: 2, note: 61, action: 'open_pc1' },
  { channel: 2, note: 62, action: 'close_pc1' },
  { channel: 2, note: 63, action: 'open_pc2' },
  { channel: 2, note: 64, action: 'close_pc2' },
  { channel: 2, note: 65, action: 'open_pc3' },
  { channel: 2, note: 66, action: 'close_pc3' },
  { channel: 2, note: 67, action: 'open_pc4' },
  { channel: 2, note: 68, action: 'close_pc4' },
  { channel: 2, note: 69, action: 'minimize_all_windows' },
]

export function defaultMapping() {
  return LEGACY_MAPPING.map((x) => ({ ...x }))
}

export function loadMapping() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || 'null')
    if (Array.isArray(raw) && raw.length) return raw
  } catch {}
  return defaultMapping()
}

export function saveMapping(list) {
  localStorage.setItem(KEY, JSON.stringify(list || []))
}

export function resetMappingToLegacy() {
  const next = defaultMapping()
  saveMapping(next)
  return next
}

export function matchAction(mapping, channel, note) {
  return (
    mapping.find((m) => m.note === note && m.channel === channel) ||
    mapping.find((m) => m.note === note && m.channel == null) ||
    null
  )
}

export function actionToSendSpec(action) {
  if (action === 'launch') return { type: 'launch', payload: {} }
  if (action === 'toggle_force_open_all') return { type: 'toggle_force_open_all', payload: {} }
  if (action === 'reset_scenario') return { type: 'reset_scenario', payload: {} }
  if (action === 'hard_reset') return { type: 'hard_reset', payload: {} }
  if (action === 'minimize_all_windows') return { type: 'minimize_all_windows', payload: {} }

  if (action === 'open_pc1') return { type: 'open_role_popup', payload: { role: 'pc1' } }
  if (action === 'open_pc2') return { type: 'open_role_popup', payload: { role: 'pc2' } }
  if (action === 'open_pc3') return { type: 'open_role_popup', payload: { role: 'pc3' } }
  if (action === 'open_pc4') return { type: 'open_role_popup', payload: { role: 'pc4' } }

  if (action === 'close_pc1') return { type: 'close_role_popup', payload: { role: 'pc1' } }
  if (action === 'close_pc2') return { type: 'close_role_popup', payload: { role: 'pc2' } }
  if (action === 'close_pc3') return { type: 'close_role_popup', payload: { role: 'pc3' } }
  if (action === 'close_pc4') return { type: 'close_role_popup', payload: { role: 'pc4' } }

  return null
}