import { Server } from '@hocuspocus/server'
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import * as Y from 'yjs'
import { pagesToJson, replacePages } from './model.js'

const port = Number(process.env.COLLABORATION_PORT || 1234)
const apiUrl = (process.env.STUDIO_API_URL || 'http://127.0.0.1:8081').replace(/\/$/, '')
const secret = process.env.STUDIO_COLLABORATION_SECRET || 'development-collaboration-secret'
const dataDir = process.env.COLLABORATION_DATA_DIR || './data'
await mkdir(dataDir, { recursive: true })

function safeName(name) {
  if (!/^project-\d+-pdf[1-4]$/.test(name)) throw new Error('Некорректное имя документа')
  return name
}

async function api(path, options = {}) {
  const response = await fetch(`${apiUrl}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-Collaboration-Secret': secret, ...(options.headers || {}) },
  })
  if (!response.ok) throw new Error((await response.text()) || `Studio API ${response.status}`)
  return response.json()
}

async function loadDocument(documentName) {
  const name = safeName(documentName)
  try {
    return new Uint8Array(await readFile(join(dataDir, `${name}.bin`)))
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
  const source = await api(`/api/internal/collaboration/documents/${name}`)
  const document = new Y.Doc()
  replacePages(document, source.pages || {})
  return document
}

async function persistDocument(documentName, document, updatedBy) {
  const name = safeName(documentName)
  const target = join(dataDir, `${name}.bin`)
  const temporary = `${target}.${process.pid}.tmp`
  await writeFile(temporary, Y.encodeStateAsUpdate(document))
  await rename(temporary, target)
  await api(`/api/internal/collaboration/documents/${name}`, {
    method: 'POST',
    body: JSON.stringify({ pages: pagesToJson(document), updatedBy: updatedBy || 'collaboration' }),
  })
}

const server = new Server({
  name: 'Postcards Studio Collaboration',
  port,
  address: '0.0.0.0',
  debounce: 500,
  maxDebounce: 1500,
  quiet: true,
  websocketOptions: { maxPayload: 6 * 1024 * 1024 },
  async onAuthenticate({ token, documentName }) {
    const value = await api('/api/internal/collaboration/auth', {
      method: 'POST', body: JSON.stringify({ token, documentName }),
    })
    return value
  },
  async onLoadDocument({ documentName }) {
    return loadDocument(documentName)
  },
  async onStoreDocument({ documentName, document, lastContext }) {
    await persistDocument(documentName, document, lastContext?.user?.email)
  },
  async beforeHandleAwareness({ states, context }) {
    for (const state of states.values()) {
      state.user = context?.user ? {
        id: context.user.id,
        name: context.user.name,
        email: context.user.email,
        color: state.user?.color || '#2c65d8',
      } : null
    }
  },
})

await server.listen()

async function shutdown() {
  await server.destroy()
  process.exit(0)
}
process.on('SIGTERM', shutdown)
process.on('SIGINT', shutdown)
