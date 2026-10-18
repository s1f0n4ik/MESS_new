import { useCallback, useEffect, useRef, useState } from 'react'
import { HocuspocusProvider } from '@hocuspocus/provider'
import { IndexeddbPersistence } from 'y-indexeddb'
import * as Y from 'yjs'
import { collaborationUrl, session } from './api'

const primitiveKeys = [
  'id', 'type', 'x', 'y', 'w', 'h', 'fontSize', 'fontFamily', 'color', 'background',
  'align', 'bold', 'italic', 'src', 'fit', 'shape', 'fill', 'stroke',
  'strokeWidth', 'strokeStyle', 'locked', 'role', 'placeholder', 'sequence',
  'cardIndex', 'sourceLabel', 'scanCode', 'missing', 'side',
]
const EDITOR_ORIGIN = Symbol('postcards-editor')
// Bump this value whenever the persisted Yjs document schema/bootstrap changes.
// A new room also creates a new IndexedDB namespace, so an old browser tab cannot
// merge a stale local copy back into the freshly migrated server document.
const COLLABORATION_LAYOUT_VERSION = 'layout-v8'

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

export function replacePages(document, rawPages = {}, origin = 'history-restore') {
  const pages = document.getMap('pages')
  document.transact(() => {
    for (const key of Array.from(pages.keys())) pages.delete(key)
    for (const [number, values] of Object.entries(rawPages)) {
      if (!Array.isArray(values) || !values.length) continue
      const list = new Y.Array(); list.push(values.map(toElement)); pages.set(String(number), list)
    }
  }, origin)
}

function colorFor(value) {
  const colors = ['#2c65d8', '#bf4d28', '#27845c', '#8b4bb3', '#b17a08', '#147d91']
  let hash = 0
  for (const character of value) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0
  return colors[Math.abs(hash) % colors.length]
}

export function useCollaboration(projectId, slot, user, templateRevision = 0) {
  const roomName = `project-${projectId}-${slot}-${COLLABORATION_LAYOUT_VERSION}-template-${templateRevision}`
  const documentRef = useRef(null)
  const [pages, setPages] = useState({})
  const [ready, setReady] = useState(false)
  const [status, setStatus] = useState('Подключаемся…')
  const [people, setPeople] = useState([])
  const [error, setError] = useState('')
  const [canUndo, setCanUndo] = useState(false)
  const [canRedo, setCanRedo] = useState(false)
  const undoRef = useRef(null)

  useEffect(() => {
    setReady(false); setStatus('Подключаемся…'); setPeople([]); setError(''); setCanUndo(false); setCanRedo(false)
    const document = new Y.Doc()
    documentRef.current = document
    const undoManager = new Y.UndoManager(document.getMap('pages'), {
      trackedOrigins: new Set([EDITOR_ORIGIN]), captureTimeout: 350,
    })
    undoRef.current = undoManager
    const refreshUndo = () => {
      setCanUndo(undoManager.undoStack.length > 0)
      setCanRedo(undoManager.redoStack.length > 0)
    }
    undoManager.on('stack-item-added', refreshUndo)
    undoManager.on('stack-item-popped', refreshUndo)
    undoManager.on('stack-cleared', refreshUndo)
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
      provider.destroy(); offline.destroy(); document.off('update', refresh); undoManager.destroy(); document.destroy()
      documentRef.current = null
      undoRef.current = null
    }
  }, [roomName, user.email, user.name])

  const transact = useCallback((callback) => {
    const document = documentRef.current
    if (document) document.transact(() => callback(document.getMap('pages')), EDITOR_ORIGIN)
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

  const changeLayout = useCallback((page, id, patch) => transact((pagesMap) => {
    const sourceList = pagesMap.get(String(page))
    if (!(sourceList instanceof Y.Array)) return
    const source = sourceList.toArray().find((entry) => entry.get('id') === id)
    if (!source) return
    const role = source.get('role')
    const templateRoles = ['scan', 'caption', 'body', 'outline', 'scan-divider', 'caption-divider', 'divider', 'outline-vertical']
    const contentPatch = Object.keys(patch).some((key) => ['text', 'src', 'sourceLabel', 'sequence', 'scanCode', 'missing', 'cardIndex'].includes(key))
    if (!templateRoles.includes(role) || contentPatch) {
      for (const [key, value] of Object.entries(patch)) {
        const current = source.get(key)
        if (key === 'text' && current instanceof Y.Text) setText(current, String(value))
        else source.set(key, value)
      }
      return
    }
    const side = source.get('side')
    const deltas = {}
    for (const key of ['x', 'y', 'w', 'h']) if (patch[key] !== undefined) {
      deltas[key] = Number(patch[key]) - Number(source.get(key) || 0)
    }
    const hasGeometry = Object.keys(deltas).length > 0
    for (const [targetPage, list] of pagesMap.entries()) {
      if (!(list instanceof Y.Array)) continue
      for (const element of list.toArray()) {
        if (!(element instanceof Y.Map) || element.get('role') !== role) continue
        if (role === 'outline-vertical' && element.get('side') !== side) continue
        if (role === 'body' && hasGeometry && Number(targetPage) % 2 !== Number(page) % 2) continue
        for (const [key, value] of Object.entries(patch)) {
          // Unlocking is local to the selected line; geometry and styling are global.
          if (key === 'locked' && element !== source) continue
          element.set(key, deltas[key] === undefined ? value : Number(element.get(key) || 0) + deltas[key])
        }
      }
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

  const changeAllText = useCallback((patch) => transact((pagesMap) => {
    for (const list of pagesMap.values()) {
      if (!(list instanceof Y.Array)) continue
      for (const element of list.toArray()) {
        if (!(element instanceof Y.Map) || element.get('type') !== 'text') continue
        for (const [key, value] of Object.entries(patch)) element.set(key, value)
      }
    }
  }), [transact])

  const resetPage = useCallback((page) => transact((pagesMap) => {
    pagesMap.delete(String(page))
  }), [transact])

  const blankPage = useCallback((page) => transact((pagesMap) => {
    const list = new Y.Array()
    list.push([toElement({ id: `background-${page}`, type: 'page-background', x: 0, y: 0, w: 1, h: 1, color: '#ffffff' })])
    pagesMap.set(String(page), list)
  }), [transact])

  const blankDocument = useCallback((pageCount = 28) => transact((pagesMap) => {
    for (const key of Array.from(pagesMap.keys())) pagesMap.delete(key)
    for (let page = 1; page <= pageCount; page += 1) {
      const list = new Y.Array()
      list.push([toElement({ id: `background-${page}`, type: 'page-background', x: 0, y: 0, w: 1, h: 1, color: '#ffffff' })])
      pagesMap.set(String(page), list)
    }
  }), [transact])

  const undo = useCallback(() => undoRef.current?.undo(), [])
  const redo = useCallback(() => undoRef.current?.redo(), [])

  const replace = useCallback((value) => { if (documentRef.current) replacePages(documentRef.current, value, EDITOR_ORIGIN) }, [])
  const snapshot = useCallback(() => documentRef.current ? pagesToJson(documentRef.current) : {}, [])
  return {
    pages, ready, status, people, error, change, changeLayout, add, remove, resetPage, blankPage,
    blankDocument, changeAllText, undo, redo, canUndo, canRedo, replace, snapshot,
  }
}
