const TEMPLATE_WIDTH_PT = 1190.55

const PDF_FONT_FAMILIES = {
  'Times New Roman': '"DejaVu Serif", serif',
  Arial: '"DejaVu Sans", sans-serif',
  Georgia: '"DejaVu Serif", serif',
  'Courier New': '"DejaVu Sans Mono", monospace',
}

export function pdfTextPreviewStyle(item, pageWidth) {
  const scale = Math.max(0.01, Number(pageWidth || TEMPLATE_WIDTH_PT) / TEMPLATE_WIDTH_PT)
  return {
    fontSize: `${Number(item.fontSize || 28) * scale}px`,
    lineHeight: 1.08,
    padding: 0,
    color: item.color,
    background: item.background,
    fontFamily: PDF_FONT_FAMILIES[item.fontFamily] || item.fontFamily || '"DejaVu Serif", serif',
    fontWeight: item.bold ? 700 : 400,
    fontStyle: item.italic ? 'italic' : 'normal',
    textAlign: item.align === 'justify' ? 'justify' : item.align,
  }
}
