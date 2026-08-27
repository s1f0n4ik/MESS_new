import { useEffect, useState } from 'react'
import { pdfUrl } from '../net/urls'

// Адрес меты выводим из pdfUrl, а не строим сами: как бы ни собирался
// базовый URL внутри urls.js, мета окажется на том же хосте.
function metaUrl(serverHost) {
  return pdfUrl('x.pdf', serverHost).replace(/\/pdfs\/x\.pdf(\?.*)?$/, '/api/pdfs/meta')
}

/**
 * mtime всех PDF с координатора. Перечитывается при каждой смене refreshKey
 * (мы передаём token окна — то есть на каждый круг/оседание), поэтому
 * подменённый на диске файл подхватится не позже следующего показа.
 */
export function usePdfMeta(serverHost, refreshKey) {
  const [meta, setMeta] = useState({})
  useEffect(() => {
    let cancelled = false
    fetch(metaUrl(serverHost))
      .then((r) => r.json())
      .then((m) => { if (!cancelled && m && typeof m === 'object') setMeta(m) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [serverHost, refreshKey])
  return meta
}