import test from 'node:test'
import assert from 'node:assert/strict'
import { alignTemplateText } from '../src/layoutGeometry.js'

test('text fields follow the actual contours and moving a separator keeps content', () => {
  const items = [
    { role: 'outline', cardIndex: 1, x: .02, y: .03, w: .46, h: .94 },
    { role: 'scan-divider', cardIndex: 1, y: .4, h: .006 },
    { role: 'caption-divider', cardIndex: 1, y: .49, h: .006 },
    { type: 'text', role: 'caption', cardIndex: 1, y: .39, h: .1, text: 'Атрибуция' },
    { type: 'text', role: 'body', cardIndex: 1, y: .4, h: .6, text: 'Экфрасис' },
  ]
  let result = alignTemplateText(items)
  assert.ok(result[3].y < .403)
  assert.ok(result[3].y + result[3].h < .493)
  assert.ok(Math.abs((result[3].y - .403) - (result[4].y - .493)) < 1e-9)
  assert.ok(result[4].x + result[4].w < .48)
  assert.equal(result[4].text, 'Экфрасис')
  items[2].y = .55
  result = alignTemplateText(items)
  assert.ok(Math.abs((result[4].y - .553) - (result[3].y - .403)) < 1e-9)
  assert.equal(result[4].text, 'Экфрасис')
  assert.equal(items[4].y, .4)
})
