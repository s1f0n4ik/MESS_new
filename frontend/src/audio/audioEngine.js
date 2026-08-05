const AUDIO_BASE = '/cards/audio'

// Пустой валидный WAV — для разблокировки элемента внутри жеста.
const SILENT_WAV =
  'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA='

function soundFileName(role, clickNumber) {
  const n = Math.max(1, Math.min(16, Number(clickNumber) || 1))
  const byRole = {
    pc1: `cliks1st type ${n}.wav`,
    pc2: `cliks2 type ${n}.wav`,
    pc3: `cliks3 type ${n}.wav`,
    pc4: `cliks4 type ${n}.wav`,
  }
  return byRole[role] || byRole.pc1
}

function soundFilePath(role, clickNumber) {
  return `${AUDIO_BASE}/${role}/${encodeURIComponent(soundFileName(role, clickNumber))}`
}

class AudioEngine {
  constructor() {
    this.enabled = true
    this.el = null
    this.unlocked = false
    this._boundUnlock = () => this.unlock()
  }

  _ensureEl() {
    if (!this.el) {
      const el = new Audio()
      el.preload = 'auto'
      this.el = el
    }
    return this.el
  }

  setEnabled(v) {
    this.enabled = Boolean(v)
    if (!this.enabled) this.stop()
  }

  stop() {
    if (!this.el) return
    try {
      this.el.pause()
      this.el.currentTime = 0
    } catch (_e) {}
  }

  // ВАЖНО: вызывается синхронно из обработчика жеста.
  unlock() {
    if (this.unlocked) return
    const el = this._ensureEl()
    const vol = el.volume
    el.volume = 0
    el.src = SILENT_WAV
    const p = el.play()
    const done = () => {
      try { el.pause(); el.currentTime = 0 } catch (_e) {}
      el.volume = vol
      this.unlocked = true
      console.log('[audio] unlocked')
    }
    if (p && typeof p.then === 'function') {
      p.then(done).catch((err) => {
        el.volume = vol
        console.warn('[audio] unlock failed:', err && err.name, err && err.message)
      })
    } else {
      done()
    }
  }

  // Резкий обрыв предыдущего + новый звук на ТОМ ЖЕ элементе.
  play(role, clickNumber) {
    if (!this.enabled) return
    const el = this._ensureEl()
    const src = soundFilePath(role, clickNumber)
    try {
      el.pause()
      el.currentTime = 0
    } catch (_e) {}
    el.src = src
    el.play().catch((err) => {
      console.warn('[audio] play failed:', err && err.name, err && err.message, src)
    })
  }

  bindUnlock() {
    const evs = ['pointerdown', 'mousedown', 'keydown', 'touchstart']
    evs.forEach((ev) =>
      window.addEventListener(ev, this._boundUnlock, { capture: true, passive: true })
    )
  }

  _ensureEl() {
    if (!this.el) {
      const el = new Audio()
      el.preload = 'auto'
      el.addEventListener('error', () => {
        const e = el.error
        console.warn('[audio] element error:', e && e.code, e && e.message, el.currentSrc)
      })
      el.addEventListener('canplay', () => console.log('[audio] canplay', el.currentSrc))
      el.addEventListener('playing', () => console.log('[audio] playing', el.currentSrc))
      this.el = el
    }
    return this.el
  }

  // Совместимость с текущими вызовами в App.jsx — заглушки.
  startKeepAliveLoop() {}
  stopKeepAliveLoop() {}
}



export const audioEngine = new AudioEngine()
export { soundFilePath };