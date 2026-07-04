import { useEffect, useMemo, useRef } from 'react'
import { resolvePdfWindow } from './resolvePdfWindow'

export function PdfWindowLayer({ state, myRole}) {
  const winRef = useRef(null)
  const lastTokenRef = useRef(null)

  const payload = useMemo(() => {
    return resolvePdfWindow(state, myRole)
  }, [state, myRole])

  useEffect(() => {
    if (!payload.visible) {
      if (winRef.current && !winRef.current.closed) {
        try { winRef.current.close() } catch {}
      }
      winRef.current = null
      lastTokenRef.current = null
      return
    }

    if (!payload.pdfFile) return

    const token = payload.token || null
    if (token && token === lastTokenRef.current) return

    const url =
      `/pdf-viewer.html?role=${encodeURIComponent(myRole)}` +
      `&file=${encodeURIComponent(payload.pdfFile)}` +
      `&token=${encodeURIComponent(token || '')}`

    if (!winRef.current || winRef.current.closed) {
      winRef.current = window.open(url, `pdf_${myRole}`, 'width=1200,height=900')
    } else {
      winRef.current.location.href = url
      winRef.current.focus()
    }

    lastTokenRef.current = token
  }, [myRole, payload.visible, payload.pdfFile, payload.token])

  useEffect(() => {
    return () => {
      if (winRef.current && !winRef.current.closed) {
        try { winRef.current.close() } catch {}
      }
      winRef.current = null
    }
  }, [])

  return null
}