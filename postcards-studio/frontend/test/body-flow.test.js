import test from 'node:test'
import assert from 'node:assert/strict'
import { bodyPairs, flowFingerprint, continuationSelection } from '../src/bodyFlow.js'

test('each column has its own continuation and content is never coupled across columns', () => {
  const pages = { 1: [
    { id: 'left', role: 'body', cardIndex: 1, type: 'text', text: 'Начало слева ', w: .45, h: .4, fontSize: 15.75 },
    { id: 'right', role: 'body', cardIndex: 2, type: 'text', text: 'Другой текст справа', w: .45, h: .4, fontSize: 15.75 },
  ], 2: [
    { id: 'right-next', role: 'body', cardIndex: 2, type: 'text', text: ' справа', w: .45, h: .9, fontSize: 15.75 },
    { id: 'left-next', role: 'body', cardIndex: 1, type: 'text', text: 'конец', w: .45, h: .9, fontSize: 15.75 },
  ] }
  const pairs = bodyPairs(pages)
  assert.equal(pairs[0].second.id, 'left-next')
  assert.equal(pairs[1].second.id, 'right-next')
  assert.notEqual(flowFingerprint(pairs[0]), flowFingerprint(pairs[1]))
  const fields = [{ page: 1, id: 'left', text: 'Начало ' }, { page: 2, id: 'left-next', text: 'слева конец' }]
  assert.equal(continuationSelection(pairs[0], fields, 'right', 1, 1), null)
  const caret = continuationSelection(pairs[0], fields, 'left', 13, 13)
  assert.equal(caret.id, 'left-next')
  assert.equal(caret.start, 6)
  const backToFirst = continuationSelection(pairs[0], [
    { page: 1, id: 'left', text: 'Начало слева конец' }, { page: 2, id: 'left-next', text: '' },
  ], 'left-next', 5, 5)
  assert.equal(backToFirst.id, 'left')
  assert.equal(pages[1][1].text, 'Другой текст справа')
})
