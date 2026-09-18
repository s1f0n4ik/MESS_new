// Разбор MIDI-сообщения в удобный объект.
// status: старший ниббл = тип, младший = канал (0..15 -> ch 1..16).
const NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];

export function noteName(num) {
  if (num == null) return '';
  const n = NOTE_NAMES[num % 12];
  const oct = Math.floor(num / 12) - 1; // C4 = 60
  return `${n}${oct}`;
}
