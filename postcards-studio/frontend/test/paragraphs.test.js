import test from 'node:test'
import assert from 'node:assert/strict'
import { insertBodyText } from '../src/paragraphs.js'

test('pasting a fragment inside a sentence does not add a paragraph indent', () => {
  assert.equal(insertBodyText('Начало конец', 7, 7, 'и ').text, 'Начало и конец')
  assert.equal(insertBodyText('', 0, 0, 'Первый\r\nВторой').text, '\u2003Первый\n\u2003Второй')
  assert.equal(insertBodyText('Абзац\n', 6, 6, '\u2003Новый').text, 'Абзац\n\u2003Новый')
})
