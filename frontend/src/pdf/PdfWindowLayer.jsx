import { useEffect, useRef } from 'react'

// ВАЖНО: роль больше НЕ читается здесь из query.
// Единственный источник истины — проп myRole (из role.js через App.jsx).

export function PdfWindowLayer({ state, myRole, onClose }) {
  const winRef = useRef(null)
  const lastTokenRef = useRef(null)

  const pdfWin = state?.pdfWindow
  const scenario = state?.scenario

  // Признак "это окно для МОЕЙ роли".
  // forceOpenAll => currentRole === 'all' => открыто у всех.
  const isForMe =
    Boolean(pdfWin?.visible) &&
    (pdfWin.role === myRole || scenario?.forceOpenAll === true)

  useEffect(() => {
    if (!isForMe) {
      // Состояние говорит "закрыто для меня" — закрываем локальное окно.
      if (winRef.current && !winRef.current.closed) {
        try { winRef.current.close() } catch {}
      }
      winRef.current = null
      lastTokenRef.current = null
      return
    }

    // token = `${popupEpoch}:${role}` — меняется на каждой новой волне/открытии.
    // Если token прежний, повторно окно не дёргаем (иначе моргание/перефокус).
    const token = pdfWin?.token || null
    if (token && token === lastTokenRef.current) return

    // Какой файл показывать: при forceOpenAll каждый показывает СВОЙ домашний pdf,
    // иначе берём то, что прислал сервер в pdfWindow.pdfFile.
    const pdfFile = scenario?.forceOpenAll
      ? (state?.pdfsByRole?.[myRole] || `${myRole}.pdf`)
      : (pdfWin?.pdfFile || `${myRole}.pdf`)

    const url =
      `/pdf-viewer.html?role=${encodeURIComponent(myRole)}` +
      `&file=${encodeURIComponent(pdfFile)}` +
      `&token=${encodeURIComponent(token || '')}`

    if (!winRef.current || winRef.current.closed) {
      winRef.current = window.open(url, `pdf_${myRole}`, 'width=1200,height=900')
    } else {
      winRef.current.location.href = url
      winRef.current.focus()
    }
    lastTokenRef.current = token
  }, [isForMe, pdfWin?.token, pdfWin?.pdfFile, scenario?.forceOpenAll, myRole, state?.pdfsByRole])

  // Cleanup при размонтировании App.
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