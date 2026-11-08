import { useEffect, useRef, useState } from 'react'
import { apiUrl } from '../net/urls'

export function MediationPanel({ serverHost, runKey, releaseId, onClose }) {
  const iframe = useRef(null)
  const finishRequested = useRef(false)
  const [config, setConfig] = useState(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [hasDocument, setHasDocument] = useState(false)
  useEffect(() => {
    let cancelled = false
    fetch(apiUrl(`/api/mediation/current?runKey=${encodeURIComponent(runKey)}`, serverHost))
      .then(async r => { if (!r.ok) throw new Error('Обновите серверную часть десктопного приложения'); return r.json() })
      .then(value => { if (!cancelled) { setConfig(value); setHasDocument(Boolean(value.projectId)) } }).catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [runKey, serverHost])
  useEffect(() => {
    if (!config) return
    const origin = new URL(config.studioUrl).origin
    const receive = async event => {
      if (event.origin !== origin || event.source !== iframe.current?.contentWindow) return
      if (event.data?.type === 'postcards:mediation-state') setBusy(Boolean(event.data.busy))
      if (event.data?.type === 'postcards:mediation') {
        setHasDocument(true)
        try {
          const response = await fetch(apiUrl('/api/mediation/current', serverHost), { method: 'POST',
            headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ runKey,
              projectId: event.data.projectId, title: event.data.title }) })
          if (!response.ok) throw new Error('Не удалось закрепить медиацию за текущим показом')
        } catch (e) { setError(e.message) }
      }
      if (event.data?.type === 'postcards:archived') {
        if (event.data.ok && finishRequested.current) onClose()
        else if (!event.data.ok) setError(event.data.error || event.data.result?.deliveryError || event.data.result?.pdfError || 'Архив пока не отправлен на NAS')
        finishRequested.current = false
      }
    }
    window.addEventListener('message', receive)
    return () => window.removeEventListener('message', receive)
  }, [config, onClose, runKey, serverHost])
  const close = () => {
    if (!busy || window.confirm('Редактор ещё сохраняет изменения. Закрыть окно? При доступном интернете дождитесь надписи «Все изменения сохранены».')) onClose()
  }
  const finish = () => {
    if (!config || busy) return
    finishRequested.current = true
    iframe.current?.contentWindow.postMessage({ type: 'postcards:archive' }, new URL(config.studioUrl).origin)
  }
  const url = config ? new URL(config.studioUrl) : null
  if (url) {
    url.searchParams.set('mediation', config.projectId ? String(config.projectId) : 'desktop')
    url.searchParams.set('embed', '1')
    if (releaseId) url.searchParams.set('release', releaseId)
  }
  return <div className="mediation-panel">
    <div className="pdf-editor-bar">
      <b>Документ 4 · Текст текущей медиации</b>
      <button disabled={!config || busy || !hasDocument} onClick={finish}>Готово · сохранить на NAS</button>
      <button onClick={close}>Вернуться к PDF</button>
    </div>
    {error && <p className="pdf-editor-error--block">{error}</p>}
    <div className="mediation-connection-note">Редактор работает через {config?.studioUrl || 'Postcards Studio'}. Для открытия и обмена с сайтом нужен интернет.</div>
    {url ? <iframe ref={iframe} src={url.toString()} title="Редактор текста медиации" className="mediation-frame" /> : <p>Подключаем редактор…</p>}
  </div>
}
