import test from 'node:test'
import assert from 'node:assert/strict'
import * as Y from 'yjs'
import { pagesToJson, replacePages } from '../src/model.js'

test('round trips structured pages and preserves collaborative text', () => {
  const first = new Y.Doc()
  replacePages(first, { 1: [{ id: 'a', type: 'text', x: .1, y: .2, w: .3, h: .4, text: 'Привет' }] })
  const second = new Y.Doc()
  Y.applyUpdate(second, Y.encodeStateAsUpdate(first))
  const text = second.getMap('pages').get('1').get(0).get('text')
  text.insert(text.length, ', мир')
  Y.applyUpdate(first, Y.encodeStateAsUpdate(second))
  assert.equal(pagesToJson(first)['1'][0].text, 'Привет, мир')
})
