// Разбор MIDI-сообщения в удобный объект.
// status: старший ниббл = тип, младший = канал (0..15 -> ch 1..16).
const NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];

export function noteName(num) {
  if (num == null) return '';
  const n = NOTE_NAMES[num % 12];
  const oct = Math.floor(num / 12) - 1; // C4 = 60
  return `${n}${oct}`;
}

export function parseMidi(data) {
  const status = data[0];
  const type = status & 0xf0;
  const channel = (status & 0x0f) + 1; // 1..16
  const d1 = data[1];
  const d2 = data[2];
  let kind = 'other';
  if (type === 0x90 && d2 > 0) kind = 'noteOn';
  else if (type === 0x80 || (type === 0x90 && d2 === 0)) kind = 'noteOff';
  else if (type === 0xb0) kind = 'cc';
  return { kind, channel, note: d1, velocity: d2, raw: status };
}

// Ключ маппинга: "ch:note" либо "*:note" для «любой канал».
export function mapKey(channel, note) {
  return `${channel == null ? '*' : channel}:${note}`;
}