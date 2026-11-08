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
  assert.equal(style.fontFamily, '"Studio Times New Roman", "Times New Roman", serif')
  assert.equal(style.lineHeight, 1.2)
  assert.equal(style.padding, 0)
})

test('body row grid fills the fixed field and does not change font size', () => {
  const item = { role: 'body', fontSize: 15.78, h: 410.537638 / 841.89, fontFamily: 'Times New Roman' }
  const style = pdfTextPreviewStyle(item, 1190.55)
  assert.equal(style.fontSize, '15.78px')
  assert.ok(style.lineHeight > 1.2)
  assert.ok(style.lineHeight < 1.25)
  assert.ok(Math.abs(21 * style.lineHeight * item.fontSize - item.h * 841.89) < .000001)
})
