import { useEffect, useRef, useState } from 'react'
import { apiUrl } from '../net/urls'
import { serverOrigin } from '../net/origin'
import { audioEngine } from '../audio/audioEngine'

const AUDIO_EXTS = ['wav', 'mp3', 'ogg', 'flac', 'm4a']

const PDF_ITEMS = [1, 2, 3, 4].map((n) => ({
  kind: 'pdf', slot: `pdf${n}`, label: `Документ ${n}`, exts: ['pdf'],
}))
const AUDIO_ITEMS = [
  ...[1, 2, 3, 4].map((n) => ({
    kind: 'audio', slot: `circle${n}`, label: `Волна ${n}`, exts: AUDIO_EXTS,
  })),
  { kind: 'audio', slot: 'vibro_final', label: 'Вибро', exts: AUDIO_EXTS },
]

function fmtSize(b) {
  if (b == null) return ''
  if (b < 1024 * 1024) return `${Math.round(b / 1024)} КБ`
  return `${(b / 1024 / 1024).toFixed(1)} МБ`
}
function fmtTime(mtime) {
  return mtime ? new Date(mtime * 1000).toLocaleString('ru-RU') : ''
}
function baseName(p) {
  return String(p || '').split(/[\\/]/).pop()
}

export function MediaPanel({ serverHost, media: mediaFromState }) {
  const [local, setLocal] = useState(null)
  const [unsupported, setUnsupported] = useState(false)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const fileInputRef = useRef(null)
  const pendingRef = useRef(null)

  // Снимок из state — источник истины; локальный — до первой рассылки.
  const media = mediaFromState || local

  useEffect(() => {
    fetch(apiUrl('/api/media', serverHost))
      .then((r) => {
        if (r.status === 404) { setUnsupported(true); return null }
        return r.json()
      })
      .then((m) => { if (m) setLocal(m) })
      .catch(() => {})
  }, [serverHost])

  const applyResult = (data) => {
    setLocal(data)
    // Не ждём рассылки state — прослушать можно сразу.
    audioEngine.setMedia(serverOrigin(serverHost), data?.audio)
  }

  const send = async (item, url, init) => {
    setBusy(item.slot)
    setError('')
    setNotice('')
    try {
      const r = await fetch(url, init)
      const data = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`)
      applyResult(data)
      if (item.slot === 'sync') {
        const release = data?.installedRelease
        setNotice(release?.status === 'already-current'
          ? `Уже установлена актуальная версия ${release.releaseId}`
          : `Установлена свежая версия ${release?.releaseId || ''}`)
      }
    } catch (e) {
      setError(`${item.label}: ${e.message || e}`)
    } finally {
      setBusy(null)
    }
  }

  const pick = async (item) => {
    const dlg = window.__TAURI__?.dialog
    if (!dlg?.open) {
      // Браузер: нативного диалога нет — грузим байты через <input type=file>.
      pendingRef.current = item
      const inp = fileInputRef.current
      inp.accept = item.exts.map((e) => `.${e}`).join(',')
      inp.click()
      return
    }
    const dir = media?.dirs?.[item.kind === 'pdf' ? 'pdfs' : 'audio']
    let picked
    try {
      picked = await dlg.open({
        multiple: false,
        directory: false,
        defaultPath: dir || undefined,
        title: `Файл для «${item.label}»`,
        filters: [{ name: item.kind === 'pdf' ? 'PDF' : 'Аудио', extensions: item.exts }],
      })
    } catch (e) {
      setError(`диалог: ${e?.message || e}`)
      return
    }
    if (!picked) return
    const path = typeof picked === 'string' ? picked : picked?.path
    await send(item, apiUrl('/api/media/import', serverHost), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: item.kind, slot: item.slot, path }),
    })
  }

  const onFileInput = async (e) => {
    const f = e.target.files?.[0]
    const item = pendingRef.current
    e.target.value = ''
    if (!f || !item) return
    const url = apiUrl(
      `/api/media/upload/${item.kind}/${item.slot}?filename=${encodeURIComponent(f.name)}`,
      serverHost,
    )
    await send(item, url, { method: 'POST', body: f })
  }

  const reset = (item) =>
    send(item, apiUrl(`/api/media/${item.kind}/${item.slot}`, serverHost), { method: 'DELETE' })

  const installTemplate = async () => {
    if (!window.confirm('Установить шаблон 2×2 во все четыре документа? Текущие PDF будут сохранены в резервной папке.')) return
    await send(
      { slot: 'template', label: 'Шаблон 2×2' },
      apiUrl('/api/media/template', serverHost),
      { method: 'POST' },
    )
  }

  const syncDocuments = async () => {
    await send(
      { slot: 'sync', label: 'Синхронизация документов' },
      apiUrl('/api/media/sync', serverHost),
      { method: 'POST' },
    )
  }

  const preview = (item) => {
    if (item.slot === 'vibro_final') audioEngine.playVibroFinal()
    else audioEngine.playCircle(Number(item.slot.replace('circle', '')))
  }

  if (unsupported) {
    return (
      <div style={{ margin: '12px 0', padding: 12, border: '1px solid #a55', borderRadius: 8, color: '#e88' }}>
        Медиа: бэкенд не поддерживает /api/media — пересобери postcards-backend.exe (build-backend.bat).
      </div>
    )
  }
  if (!media) return null

  const row = (item) => {
    const info = media[item.kind === 'pdf' ? 'pdfs' : 'audio']?.[item.slot]
    const isBusy = busy === item.slot
    const label = item.kind === 'pdf' ? (media.pdfTitles?.[item.slot] || item.label) : item.label
    return (
      <div key={item.slot} style={{ display: 'flex', gap: 8, alignItems: 'center', minHeight: 28 }}>
        <span style={{ width: 160, fontWeight: 600 }}>{label}</span>
        <span style={{ flex: 1, fontFamily: 'monospace', fontSize: 12, opacity: info ? 1 : 0.6 }}>
          {info
            ? `${info.file} · ${fmtSize(info.size)} · ${fmtTime(info.mtime)}${
                info.source ? ` · из: ${baseName(info.source)}` : ''
              }`
            : item.kind === 'pdf' ? 'файла нет!' : 'встроенный звук'}
        </span>
        <button onClick={() => pick(item)} disabled={isBusy}>
          {isBusy ? '…' : 'Выбрать…'}
        </button>
        {item.kind === 'audio' && (
          <>
            <button onClick={() => preview(item)} title="прослушать">▶</button>
            <button onClick={() => reset(item)} disabled={!info || isBusy} title="вернуть встроенный">✕</button>
          </>
        )}
      </div>
    )
  }

  return (
    <div style={{ margin: '12px 0', padding: 12, border: '1px solid #444', borderRadius: 8 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>Документы и звуки</div>
      <input ref={fileInputRef} type="file" style={{ display: 'none' }} onChange={onFileInput} />

      <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4 }}>
        Документы — {media.dirs?.pdfs}
      </div>
      <div style={{ display: 'grid', gap: 4, marginBottom: 12 }}>{PDF_ITEMS.map(row)}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
        <button onClick={syncDocuments} disabled={busy === 'sync'} style={{ fontWeight: 700 }}>
          {busy === 'sync' ? 'Синхронизируем…' : 'Синхронизировать все документы'}
        </button>
        <span style={{ fontSize: 12, opacity: 0.75 }}>
          Источник: {media.sync?.path || 'не настроен'}
          {media.sync?.installedReleaseId ? ` · установлена ${media.sync.installedReleaseId}` : ''}
        </span>
      </div>
      {media.template?.available && (
        <button onClick={installTemplate} disabled={busy === 'template'} style={{ marginBottom: 12, fontWeight: 700 }}>
          {busy === 'template' ? 'Устанавливаем…' : 'Установить шаблон 2×2 × 14 во все четыре документа'}
        </button>
      )}

      <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4 }}>
        Звуки открытий — {media.dirs?.audio}
      </div>
      <div style={{ display: 'grid', gap: 4 }}>{AUDIO_ITEMS.map(row)}</div>

      {error && <div style={{ color: '#e88', marginTop: 8, fontSize: 13 }}>{error}</div>}
      {notice && !error && <div style={{ color: '#8d8', marginTop: 8, fontSize: 13 }}>{notice}</div>}

      <div style={{ marginTop: 8, fontSize: 12, opacity: 0.7 }}>
        Кнопка синхронизации читает current.json из папки «Релизы» на диске Z:, проверяет контрольные
        суммы и атомарно устанавливает сразу четыре опубликованных PDF. Предыдущий комплект сохраняется
        в резервной папке. Выбранный вручную файл копируется на место pdfN.pdf / circleN / vibro_final. Выбирать можно любой
        файл на диске — диалог просто открывается в текущей папке. Клиенты подхватывают новый текст
        со следующего показа, звук — с ближайшей рассылки состояния. Прослушивание вибро требует
        включённого канала «Вибро-финал». Менять файлы лучше в idle: пока текст отдаётся клиенту,
        подмена вернёт 409 — повтори через пару секунд.
      </div>
    </div>
  )
}
