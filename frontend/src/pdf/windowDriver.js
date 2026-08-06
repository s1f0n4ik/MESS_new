// Единый драйвер окна PDF: web (window.open) и tauri (нативное окно).
// Выбор реализации — по наличию window.__TAURI__ (включён withGlobalTauri).

const isTauri = () =>
  typeof window !== 'undefined' && !!window.__TAURI__

// ---- WEB (dev в браузере / fallback) --------------------------------
function createWebDriver() {
  let win = null
  return {
    kind: 'web',
    async open(_token, url, opts = {}) {
      const features = opts.features || 'width=1968,height=1392'
      win = window.open(url, 'pdf-window', features)
      return !!win
    },
    async close() {
      if (win && !win.closed) win.close()
      win = null
    },
    async minimize() {
      // В браузере свернуть окно нельзя — no-op.
    },
    async restore() {
      if (win && !win.closed) win.focus()
    },
    async minimizeAll() {},
  }
}

// ---- TAURI ----------------------------------------------------------
function createTauriDriver() {
  const { invoke } = window.__TAURI__.core
  const { WebviewWindow } = window.__TAURI__.webviewWindow

  let label = null

  const handle = async () => {
    if (!label) return null
    try {
      return await WebviewWindow.getByLabel(label)
    } catch (e) {
      console.error('[tauriDriver] getByLabel failed:', e)
      return null
    }
  }

  return {
    kind: 'tauri',
    async open(token, url, opts = {}) {
      const next = `pdf-${opts.role || 'x'}`
      if (label && label !== next) await this.close()
      label = next
      const query = String(url).replace(/^\/?\?/, '')
      try {
        await invoke('open_pdf_window', { label, query })
        return true
      } catch (e) {
        console.error('[tauriDriver] open_pdf_window failed:', e)
        label = null
        return false
      }
    },
    async close() {
      if (!label) return
      try {
        await invoke('close_pdf_window', { label })
      } catch (e) {
        console.error('[tauriDriver] close_pdf_window failed', e)
      }
      label = null
    },
    async minimize() {
      const win = await handle()
      if (win) { try { await win.minimize() } catch (_) {} }
    },
    async restore() {
      const win = await handle()
      if (win) {
        try {
          await win.unminimize()
          await win.setFocus()
        } catch (_) {}
      }
    },
    async minimizeAll() {
      try { await invoke('minimize_all') } catch (e) {
        console.error('[tauriDriver] minimize_all failed', e)
      }
    },
    async setMainFullscreen(on) {
      try { await invoke('main_fullscreen', { on: !!on }) } catch (e) {
        console.error('[tauriDriver] main_fullscreen failed', e)
      }
    },
  }
}

let _driver = null
export function getWindowDriver() {
  if (_driver) return _driver
  _driver = isTauri() ? createTauriDriver() : createWebDriver()
  return _driver
}