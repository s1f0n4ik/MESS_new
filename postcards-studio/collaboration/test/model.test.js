import test from 'node:test'
import assert from 'node:assert/strict'
import * as Y from 'yjs'
import { allowsTextOnlyUpdate, pagesToJson, replacePages } from '../src/model.js'

test('round trips structured pages and preserves collaborative text', () => {
  const first = new Y.Doc()
  replacePages(first, { 1: [
    { id: 'background-1', type: 'page-background', x: 0, y: 0, w: 1, h: 1, color: '#ffffff' },
    { id: 'a', type: 'text', x: .1, y: .2, w: .3, h: .4, text: 'Привет', fontFamily: 'Georgia', italic: true,
      locked: true, role: 'body', cardIndex: 1, placeholder: 'Текст' },
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
  assert.equal(result[1].locked, true)
  assert.equal(result[1].role, 'body')
  assert.equal(result[1].placeholder, 'Текст')
  assert.equal(result[2].strokeStyle, 'dashed')
})

test('mediators can synchronize text but cannot move, add or remove template objects', () => {
  const server = new Y.Doc()
  replacePages(server, { 1: [{ id: 'body', type: 'text', x: .1, text: 'До' },
    { id: 'line', type: 'shape', x: .2, side: 'left' }] })
  for (const [change, allowed] of [
    [(client) => client.getMap('pages').get('1').get(0).get('text').insert(2, ' правки'), true],
    [(client) => client.getMap('pages').get('1').get(1).set('x', .8), false],
    [(client) => client.getMap('pages').get('1').delete(1, 1), false],
    [(client) => client.getMap('pages').get('1').push([new Y.Map([['id', 'extra']])]), false],
  ]) {
    const client = new Y.Doc()
    Y.applyUpdate(client, Y.encodeStateAsUpdate(server))
    const vector = Y.encodeStateVector(server)
    change(client)
    assert.equal(allowsTextOnlyUpdate(server, Y.encodeStateAsUpdate(client, vector)), allowed)
    client.destroy()
  }
  assert.equal(pagesToJson(server)['1'][1].x, .2)
  server.destroy()
})

test('mediation sessions accept body text but protect captions and geometry even for staff', () => {
  const server = new Y.Doc()
  replacePages(server, {1:[{id:'body',type:'text',role:'body',text:'До'},
    {id:'caption',type:'text',role:'caption',text:'Подпись'},
    {id:'line',type:'shape',h:.9}]})
  for (const [index,key,value,allowed] of [[0,'text','После',true],[1,'text','Другая подпись',false],[2,'h',.1,false]]) {
    const client = new Y.Doc();Y.applyUpdate(client,Y.encodeStateAsUpdate(server))
    const element=client.getMap('pages').get('1').get(index)
    if(key==='text'){element.get('text').delete(0,element.get('text').length);element.get('text').insert(0,value)}
    else element.set(key,value)
    assert.equal(allowsTextOnlyUpdate(server,Y.encodeStateAsUpdate(client,Y.encodeStateVector(server)),true),allowed)
    client.destroy()
  }
  server.destroy()
})
