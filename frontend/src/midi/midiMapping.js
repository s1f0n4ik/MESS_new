const KEY = 'postcards_midi_map_v1';

// Формат записи: { channel: number|null, note: number, action: string, payload?: object }
// channel === null => «любой канал».
export const MIDI_ACTIONS = [
  'launch',          // advance_wave: следующий круг/шаг
  'open_all',        // force_open_all
  'reset_scenario',  // мягкий сброс
  'hard_reset',      // полный сброс
];

export function loadMapping() {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || '[]');
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

export function saveMapping(list) {
  localStorage.setItem(KEY, JSON.stringify(list || []));
}

// Поиск действия по входящей ноте: сначала точный канал, потом «любой».
export function matchAction(mapping, channel, note) {
  return (
    mapping.find((m) => m.note === note && m.channel === channel) ||
    mapping.find((m) => m.note === note && m.channel == null) ||
    null
  );
}