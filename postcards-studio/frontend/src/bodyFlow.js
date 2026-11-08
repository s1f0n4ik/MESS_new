import { alignTemplateText } from './layoutGeometry.js'

export function bodyPairs(pages) {
  const result = []
  for (const [number, values] of Object.entries(pages)) {
    const page = Number(number)
    if (page % 2 === 0) continue
    const following = alignTemplateText(pages[page + 1] || [])
    for (const first of alignTemplateText(values)) {
      if (first.role !== 'body') continue
      const second = following.find((value) => value.role === 'body' && value.cardIndex === first.cardIndex)
      if (second) result.push({ key: `${page}:${first.cardIndex}`, page, first, second })
    }
  }
  return result
}

export function flowBox(item) {
  return { w: item.w, h: item.h, fontSize: item.fontSize, fontFamily: item.fontFamily,
    bold: !!item.bold, italic: !!item.italic }
}

export function flowFingerprint(pair) {
  return JSON.stringify([pair.first.id, pair.first.text || '', flowBox(pair.first),
    pair.second.id, pair.second.text || '', flowBox(pair.second)])
}

export function continuationSelection(pair, fields, id, start, end) {
  if (![pair.first.id, pair.second.id].includes(id)) return null
  const offset = id === pair.second.id ? (pair.first.text || '').length : 0
  const absoluteEnd = offset + end
  const firstLength = fields[0].text.length
  const index = absoluteEnd > firstLength || (absoluteEnd === firstLength && id === pair.second.id && fields[1].text.length > 0) ? 1 : 0
  const base = index ? firstLength : 0
  return { ...fields[index], start: Math.max(0, Math.min(fields[index].text.length, offset + start - base)),
    end: Math.max(0, Math.min(fields[index].text.length, absoluteEnd - base)) }
}
