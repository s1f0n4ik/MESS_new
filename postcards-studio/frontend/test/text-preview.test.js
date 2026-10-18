import assert from 'node:assert/strict'
import test from 'node:test'

import { pdfTextPreviewStyle } from '../src/textPreview.js'

test('PDF text preview uses the same point scale and server font family', () => {
  const style = pdfTextPreviewStyle({
    fontSize: 15,
    fontFamily: 'Times New Roman',
    color: '#111111',
    background: 'transparent',
    align: 'left',
  }, 1120)

  assert.equal(style.fontSize, `${15 * 1120 / 1190.55}px`)
  assert.equal(style.fontFamily, '"DejaVu Serif", serif')
  assert.equal(style.lineHeight, 1.08)
  assert.equal(style.padding, 0)
})
