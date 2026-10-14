import test from 'node:test'
import assert from 'node:assert/strict'
import * as Y from 'yjs'
import { pagesToJson, replacePages } from '../src/model.js'

test('round trips structured pages and preserves collaborative text', () => {
  const first = new Y.Doc()
  replacePages(first, { 1: [
    { id: 'background-1', type: 'page-background', x: 0, y: 0, w: 1, h: 1, color: '#ffffff' },
    { id: 'a', type: 'text', x: .1, y: .2, w: .3, h: .4, text: 'Привет', fontFamily: 'Georgia', italic: true },
    { id: 'shape', type: 'shape', x: .2, y: .4, w: .3, h: .2, shape: 'ellipse', fill: 'transparent', stroke: '#111111', strokeWidth: 3, strokeStyle: 'dashed' },
  ] })
  const second = new Y.Doc()
  Y.applyUpdate(second, Y.encodeStateAsUpdate(first))
  const text = second.getMap('pages').get('1').get(1).get('text')
  text.insert(text.length, ', мир')
  Y.applyUpdate(first, Y.encodeStateAsUpdate(second))
  const result = pagesToJson(first)['1']
  assert.equal(result[0].type, 'page-background')
  assert.equal(result[1].text, 'Привет, мир')
  assert.equal(result[1].fontFamily, 'Georgia')
  assert.equal(result[1].italic, true)
  assert.equal(result[2].strokeStyle, 'dashed')
})
