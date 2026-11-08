import { bodyLineHeight } from './layoutGeometry.js'

const TEMPLATE_WIDTH_PT = 1190.55

const PDF_FONT_FAMILIES = {
  'Times New Roman': '"Studio Times New Roman", "Times New Roman", serif',
  Arial: '"Studio Arial", Arial, sans-serif',
  Georgia: '"Studio Georgia", Georgia, serif',
  'Courier New': '"Studio Courier New", "Courier New", monospace',
}

export function pdfTextPreviewStyle(item, pageWidth) {
  const scale = Math.max(0.01, Number(pageWidth || TEMPLATE_WIDTH_PT) / TEMPLATE_WIDTH_PT)
  return {
    fontSize: `${Number(item.fontSize || 28) * scale}px`,
    lineHeight: item.role === 'body' ? bodyLineHeight(item) : 1.2,
    padding: 0,
    color: item.color,
    background: item.background,
    fontFamily: PDF_FONT_FAMILIES[item.fontFamily] || item.fontFamily || '"DejaVu Serif", serif',
    fontWeight: item.bold ? 700 : 400,
    fontStyle: item.italic ? 'italic' : 'normal',
    textAlign: item.align === 'justify' ? 'justify' : item.align,
    fontKerning: 'none',
    fontVariantLigatures: 'none',
  }
}
