import assert from 'node:assert/strict'
import { HocuspocusProvider } from '@hocuspocus/provider'
import * as Y from 'yjs'
import { pagesToJson, replacePages } from '../src/model.js'

const apiUrl = process.env.TEST_API_URL || 'http://127.0.0.1:18081'
const socketUrl = process.env.TEST_COLLAB_URL || 'ws://127.0.0.1:12345'
const login = await fetch(`${apiUrl}/api/auth/login`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'admin@test.local', password: 'very-secure-test-password' }),
})
assert.equal(login.status, 200)
const token = (await login.json()).token

function connect() {
  const document = new Y.Doc()
  return new Promise((resolve, reject) => {
    const provider = new HocuspocusProvider({
      url: socketUrl, name: 'project-1-pdf1-layout-v5', token, document,
      onSynced: () => resolve({ provider, document }),
      onAuthenticationFailed: ({ reason }) => reject(new Error(reason)),
    })
  })
}

const first = await connect()
const second = await connect()
replacePages(first.document, { 1: [{ id: 'shared', type: 'text', x: .1, y: .1, w: .4, h: .2, text: 'A' }] })
await new Promise((resolve) => setTimeout(resolve, 250))
const firstText = first.document.getMap('pages').get('1').get(0).get('text')
const secondText = second.document.getMap('pages').get('1').get(0).get('text')
firstText.insert(1, 'B')
secondText.insert(0, 'C')
await new Promise((resolve) => setTimeout(resolve, 2200))
assert.equal(pagesToJson(first.document)['1'][0].text, pagesToJson(second.document)['1'][0].text)
const saved = await fetch(`${apiUrl}/api/projects/1/documents/pdf1`, { headers: { Authorization: `Bearer ${token}` } })
assert.equal(saved.status, 200)
assert.equal((await saved.json()).pages['1'][0].text, pagesToJson(first.document)['1'][0].text)
first.provider.destroy(); second.provider.destroy(); first.document.destroy(); second.document.destroy()
console.log('Two-client collaboration converged and persisted.')
