export function insertBodyText(current, start, end, pasted) {
  const prefix = current.slice(0, start)
  const parts = pasted.replace(/\r\n?/g, '\n').split('\n')
  const formatted = parts.map((line, index) => {
    const paragraphStart = index > 0 || !prefix || prefix.endsWith('\n') || !prefix.trim()
    return paragraphStart && line.trim() && !line.startsWith('\u2003') ? `\u2003${line.trimStart()}` : line
  }).join('\n')
  return { text: `${prefix}${formatted}${current.slice(end)}`, cursor: start + formatted.length }
}
