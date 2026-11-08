import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { bodyPairs, continuationSelection, flowBox, flowFingerprint } from './bodyFlow'

export function useAutomaticTextFlow(projectId, slot, templateRevision, collaboration) {
  const context = `${projectId}:${slot}:${templateRevision}`
  const sessionRef = useRef(null)
  const [flowTrigger, setFlowTrigger] = useState(0)
  const [state, setState] = useState({ pending: 0, message: '', error: '', overflow: false })
  const { pages, snapshot, ready, changeTexts, status } = collaboration

  useEffect(() => {
    const session = { context, stopped: false, initialized: false, seen: new Map(), versions: new Map(),
      timers: new Map(), requests: new Map(), failed: new Set(), results: new Map(), lastMessage: '', status }
    session.immediate = new Set()
    sessionRef.current = session
    setState({ pending: 0, message: '', error: '', overflow: false })
    return () => {
      session.stopped = true
      for (const timer of session.timers.values()) clearTimeout(timer)
      for (const controller of session.requests.values()) controller.abort()
    }
  }, [context])

  useEffect(() => {
    const session = sessionRef.current
    if (!ready || !session || session.stopped) return
    const pairs = bodyPairs(snapshot())
    const present = new Set(pairs.map((pair) => pair.key))
    for (const key of session.seen.keys()) if (!present.has(key)) {
      clearTimeout(session.timers.get(key))
      session.requests.get(key)?.abort()
      for (const map of [session.seen, session.timers, session.requests, session.versions, session.results]) map.delete(key)
      session.immediate.delete(key)
      session.failed.delete(key)
    }
    if (!pairs.length) {
      if (session.initialized) setState({ pending: 0, message: '', error: '', overflow: false })
      session.initialized = false
      return
    }
    if (!session.initialized) {
      for (const pair of pairs) {
        if (!(pair.first.text || '').trim() && !(pair.second.text || '').trim()) session.seen.set(pair.key, flowFingerprint(pair))
      }
      session.initialized = true
    }
    const reconnected = session.status !== status && !status.startsWith('Офлайн')
    session.status = status
    const updatePending = () => {
      if (!session.stopped) setState((current) => ({ ...current, pending: session.timers.size + session.requests.size }))
    }
    const updateSummary = () => {
      const overflows = [...session.results.values()].filter((value) => value.overflow)
      const message = overflows.length === 1 ? overflows[0].message : overflows.length > 1
        ? `Текст не помещается в два поля: ${overflows.map((value) => value.cardIndex).join(', ')}.` : session.lastMessage
      if (!session.stopped) setState((value) => ({ ...value, error: '', overflow: overflows.length > 0, message }))
    }
    for (const pair of pairs) {
      const fingerprint = flowFingerprint(pair)
      if (session.seen.get(pair.key) === fingerprint && !(reconnected && session.failed.has(pair.key))) continue
      session.seen.set(pair.key, fingerprint)
      session.failed.delete(pair.key)
      const version = (session.versions.get(pair.key) || 0) + 1
      session.versions.set(pair.key, version)
      clearTimeout(session.timers.get(pair.key))
      session.timers.delete(pair.key)
      session.requests.get(pair.key)?.abort()
      session.requests.delete(pair.key)
      if (!(pair.first.text || '').trim() && !(pair.second.text || '').trim()) {
        session.results.delete(pair.key)
        session.lastMessage = ''
        updateSummary()
        continue
      }
      const delay = session.immediate.delete(pair.key) ? 0 : 300
      session.timers.set(pair.key, setTimeout(async () => {
        session.timers.delete(pair.key)
        const controller = new AbortController()
        session.requests.set(pair.key, controller)
        updatePending()
        try {
          const result = await api(`/api/projects/${projectId}/documents/${slot}/text-flow`, {
            method: 'POST', signal: controller.signal,
            body: JSON.stringify({ page: pair.page, itemId: pair.first.id,
              text: (pair.first.text || '') + (pair.second.text || ''), templateRevision,
              fields: [flowBox(pair.first), flowBox(pair.second)] }),
          })
          if (session.stopped || session.versions.get(pair.key) !== version) return
          const current = bodyPairs(snapshot()).find((value) => value.key === pair.key)
          if (!current || flowFingerprint(current) !== fingerprint) return
          const active = document.activeElement
          const activeId = active?.closest('[data-item-id]')?.dataset.itemId
          const caret = active?.tagName === 'TEXTAREA'
            ? continuationSelection(current, result.fields, activeId, active.selectionStart, active.selectionEnd) : null
          const next = { ...current, first: { ...current.first, text: result.fields[0].text },
            second: { ...current.second, text: result.fields[1].text } }
          session.seen.set(pair.key, flowFingerprint(next))
          if (flowFingerprint(next) !== fingerprint) changeTexts(result.fields)
          if (caret) requestAnimationFrame(() => {
            if (session.stopped || document.activeElement !== active) return
            const target = document.querySelector(`[data-item-id="${caret.id}"] textarea`)
            target?.focus({ preventScroll: target === active })
            if (target) { target.selectionStart = caret.start; target.selectionEnd = caret.end }
          })
          const message = result.overflow ? `Поле ${pair.first.cardIndex}: ${result.characters} знаков. Текст не помещается в два поля.`
            : `${result.characters} знаков · текст помещается; вместимость зависит от длины слов и абзацев`
          session.results.set(pair.key, { overflow: result.overflow, message, cardIndex: pair.first.cardIndex })
          session.lastMessage = message
          updateSummary()
        } catch (error) {
          if (!session.stopped && error.name !== 'AbortError' && session.versions.get(pair.key) === version) {
            if (!error.status || error.status >= 500) session.failed.add(pair.key)
            setState((value) => ({ ...value, error: `Не удалось автоматически распределить текст: ${error.message}. Введённый текст не удалён.` }))
          }
        } finally {
          if (session.requests.get(pair.key) === controller) session.requests.delete(pair.key)
          updatePending()
        }
      }, 300))
    }
    updatePending()
  }, [pages, ready, context, status, snapshot, changeTexts, projectId, slot, templateRevision, flowTrigger])

  const paste = useCallback((page, id, text, { replaceWhole = false } = {}) => {
    const pair = bodyPairs(snapshot()).find((value) =>
      (value.page === page && value.first.id === id) || (value.page + 1 === page && value.second.id === id))
    if (!pair) return
    const fields = [{ page, id, text }]
    // A complete replacement affects this postcard's continuation only.
    // The opposite column is a separate text and is never copied or changed.
    if (replaceWhole && page === pair.page) fields.push({ page: page + 1, id: pair.second.id, text: '' })
    changeTexts(fields)
    const session = sessionRef.current
    if (session && !session.stopped) {
      session.seen.delete(pair.key)
      session.immediate.add(pair.key)
    }
    // Yjs transactions are synchronous, but a separate trigger makes the
    // redistribution independent of React's update batching (notably Safari).
    setFlowTrigger((value) => value + 1)
  }, [snapshot, changeTexts])

  return { ...state, paste }
}
