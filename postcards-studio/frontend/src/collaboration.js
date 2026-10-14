import { useCallback, useEffect, useRef, useState } from 'react'
import { HocuspocusProvider } from '@hocuspocus/provider'
import { IndexeddbPersistence } from 'y-indexeddb'
import * as Y from 'yjs'
import { collaborationUrl, session } from './api'

const primitiveKeys = ['id', 'type', 'x', 'y', 'w', 'h', 'fontSize', 'color', 'background', 'align', 'bold', 'src', 'fit']

function toElement(value) {
  const element = new Y.Map()
  for (const key of primitiveKeys) if (value[key] !== undefined) element.set(key, value[key])
  if (value.type === 'text') {
    const text = new Y.Text(); text.insert(0, String(value.text || '')); element.set('text', text)
  }
  return element
}

export function pagesToJson(document) {
  const result = {}
  for (const [number, list] of document.getMap('pages').entries()) {
    if (!(list instanceof Y.Array)) continue
    const values = list.toArray().filter((entry) => entry instanceof Y.Map).map((entry) => {
      const value = {}
      for (const [key, field] of entry.entries()) value[key] = field instanceof Y.Text ? field.toString() : field
      return value
    })
    if (values.length) result[number] = values
  }
  return result
}

function setText(text, nextValue) {
  const current = text.toString()
  if (current === nextValue) return
  let prefix = 0
  while (prefix < current.length && prefix < nextValue.length && current[prefix] === nextValue[prefix]) prefix += 1
  let suffix = 0
  while (suffix < current.length - prefix && suffix < nextValue.length - prefix &&
    current[current.length - 1 - suffix] === nextValue[nextValue.length - 1 - suffix]) suffix += 1
  if (current.length - prefix - suffix) text.delete(prefix, current.length - prefix - suffix)
  const insert = nextValue.slice(prefix, nextValue.length - suffix)
  if (insert) text.insert(prefix, insert)
}

export function replacePages(document, rawPages = {}) {
  const pages = document.getMap('pages')
  document.transact(() => {
    for (const key of Array.from(pages.keys())) pages.delete(key)
    for (const [number, values] of Object.entries(rawPages)) {
      if (!Array.isArray(values) || !values.length) continue
      const list = new Y.Array(); list.push(values.map(toElement)); pages.set(String(number), list)
    }
  }, 'history-restore')
}

function colorFor(value) {
  const colors = ['#2c65d8', '#bf4d28', '#27845c', '#8b4bb3', '#b17a08', '#147d91']
  let hash = 0
  for (const character of value) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0
  return colors[Math.abs(hash) % colors.length]
}

export function useCollaboration(projectId, slot, user) {
  const roomName = `project-${projectId}-${slot}`
  const documentRef = useRef(null)
  const [pages, setPages] = useState({})
  const [ready, setReady] = useState(false)
  const [status, setStatus] = useState('Подключаемся…')
  const [people, setPeople] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    setReady(false); setStatus('Подключаемся…'); setPeople([]); setError('')
    const document = new Y.Doc()
    documentRef.current = document
    const offline = new IndexeddbPersistence(`postcards-${roomName}`, document)
    const refresh = () => setPages(pagesToJson(document))
    document.on('update', refresh)
    const provider = new HocuspocusProvider({
      url: collaborationUrl(), name: roomName, document, token: session.token, flushDelay: 120,
      onStatus: ({ status: value }) => setStatus(value === 'connected' ? 'Синхронизация…' : value === 'connecting' ? 'Подключаемся…' : 'Офлайн — изменения сохранятся'),
      onSynced: () => { refresh(); setReady(true); setStatus('Все изменения сохранены') },
      onUnsyncedChanges: ({ number }) => setStatus(number ? 'Сохраняем…' : 'Все изменения сохранены'),
      onAuthenticationFailed: ({ reason }) => setError(reason || 'Не удалось войти в совместный документ'),
      onAwarenessUpdate: ({ states }) => setPeople(states.map((state) => state.user).filter(Boolean)),
    })
    provider.setAwarenessField('user', { name: user.name, email: user.email, color: colorFor(user.email) })
    offline.on('synced', () => { refresh(); setReady(true) })
    return () => {
      provider.destroy(); offline.destroy(); document.off('update', refresh); document.destroy()
      documentRef.current = null
    }
  }, [roomName, user.email, user.name])

  const transact = useCallback((callback) => {
    const document = documentRef.current
    if (document) document.transact(() => callback(document.getMap('pages')), 'editor')
  }, [])

  const change = useCallback((page, id, patch) => transact((pagesMap) => {
    const list = pagesMap.get(String(page))
    if (!(list instanceof Y.Array)) return
    const element = list.toArray().find((entry) => entry.get('id') === id)
    if (!element) return
    for (const [key, value] of Object.entries(patch)) {
      const current = element.get(key)
      if (key === 'text' && current instanceof Y.Text) setText(current, String(value))
      else element.set(key, value)
    }
  }), [transact])

  const add = useCallback((page, value) => transact((pagesMap) => {
    let list = pagesMap.get(String(page))
    if (!(list instanceof Y.Array)) { list = new Y.Array(); pagesMap.set(String(page), list) }
    list.push([toElement(value)])
  }), [transact])

  const remove = useCallback((page, id) => transact((pagesMap) => {
    const list = pagesMap.get(String(page))
    if (!(list instanceof Y.Array)) return
    const index = list.toArray().findIndex((entry) => entry.get('id') === id)
    if (index >= 0) list.delete(index, 1)
  }), [transact])

  const replace = useCallback((value) => { if (documentRef.current) replacePages(documentRef.current, value) }, [])
  const snapshot = useCallback(() => documentRef.current ? pagesToJson(documentRef.current) : {}, [])
  return { pages, ready, status, people, error, change, add, remove, replace, snapshot }
}
