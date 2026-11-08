// Text belongs to the areas defined by the template contours, including after
// an administrator moves a separator. Coordinates are fractions of the page.
// Logical PDF size. At the normal editor scale this renders as 15.3 CSS px,
// while matching the line composition of the Illustrator reference.
export const DEFAULT_FONT_SIZE = 15.75
export const CAPTION_DIVIDER_Y = .40104 + ((3 * 1.2 - .22) * DEFAULT_FONT_SIZE + 1) / 841.89

export function bodyLineHeight(item) {
  const size = Number(item.fontSize || DEFAULT_FONT_SIZE)
  const height = Number(item.h) * 841.89
  const rows = Math.floor((height + .000001) / (size * 1.2))
  return rows >= 2 ? height / (rows * size) : 1.2
}

export function alignTemplateText(items) {
  return items.map((item) => {
    if (item.type !== 'text' || !['caption', 'body'].includes(item.role)) return item
    const siblings = items.filter((value) => value.cardIndex === item.cardIndex)
    const outline = siblings.find((value) => value.role === 'outline')
    if (!outline) return item
    const upper = siblings.find((value) => value.role === 'scan-divider')
    const lower = siblings.find((value) => value.role === 'caption-divider')
    const inkOffset = -.22 * Number(item.fontSize || DEFAULT_FONT_SIZE) / 841.89
    const top = item.role === 'caption'
      ? (upper ? upper.y + upper.h / 2 + inkOffset : item.y)
      : (lower ? lower.y + lower.h / 2 + inkOffset : outline.y + inkOffset)
    const bottom = item.role === 'caption'
      ? (lower ? lower.y + lower.h / 2 - 1 / 841.89 : item.y + item.h)
      : outline.y + outline.h - 1e-7
    return { ...item, x: outline.x + .0005, y: top,
      w: Number(Math.max(.001, outline.w - .001).toFixed(9)), h: Number(Math.max(.001, bottom - top).toFixed(9)) }
  })
}
