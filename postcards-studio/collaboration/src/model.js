import * as Y from 'yjs'

const primitiveKeys = [
  'id', 'type', 'x', 'y', 'w', 'h', 'fontSize', 'fontFamily', 'color', 'background',
  'align', 'bold', 'italic', 'src', 'fit', 'shape', 'fill', 'stroke', 'strokeWidth', 'strokeStyle',
  'locked', 'role', 'placeholder', 'sequence', 'cardIndex', 'sourceLabel', 'scanCode', 'missing',
]

export function elementFromJson(value) {
  const element = new Y.Map()
  for (const key of primitiveKeys) {
    if (value[key] !== undefined) element.set(key, value[key])
  }
  if (value.type === 'text') {
    const text = new Y.Text()
    text.insert(0, String(value.text || ''))
    element.set('text', text)
  }
  return element
}

export function replacePages(document, rawPages = {}) {
  const pages = document.getMap('pages')
  document.transact(() => {
    for (const key of Array.from(pages.keys())) pages.delete(key)
    for (const [number, values] of Object.entries(rawPages)) {
      if (!Array.isArray(values) || values.length === 0) continue
      const list = new Y.Array()
      list.push(values.map(elementFromJson))
      pages.set(String(number), list)
    }
  }, 'bootstrap')
}

export function pagesToJson(document) {
  const result = {}
  const pages = document.getMap('pages')
  for (const [number, list] of pages.entries()) {
    if (!(list instanceof Y.Array)) continue
    const values = list.toArray().filter((entry) => entry instanceof Y.Map).map((entry) => {
      const value = {}
      for (const [key, field] of entry.entries()) value[key] = field instanceof Y.Text ? field.toString() : field
      return value
    })
    if (values.length) result[number] = values
  }
  return result
}
