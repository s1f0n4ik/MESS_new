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
    this.vibroEl = null
    this.vibroEnabled = false
    this.unlocked = false
    this.unlocking = false
    this._boundUnlock = () => this.unlock()
  }

  _ensureEl() {
    if (!this.el) {
      const el = new Audio()
      el.preload = 'auto'
      el.addEventListener('error', () => {
        const e = el.error
        console.warn('[audio] element error:', e && e.code, e && e.message, el.currentSrc)
      })
      el.addEventListener('playing', () =>
        console.log('[audio] playing', el.currentSrc, 'vol=', el.volume, 'muted=', el.muted)
      )
      this.el = el
    }
    return this.el
  }

  _ensureVibroEl() {
    if (!this.vibroEl) {
      const el = new Audio()
      el.preload = 'auto'
      el.addEventListener('error', () => {
        const e = el.error
        console.warn('[vibro] element error:', e && e.code, e && e.message, el.currentSrc)
      })
      el.addEventListener('playing', () =>
        console.log('[vibro] playing', el.currentSrc, 'sink=', el.sinkId || 'default')
      )
      this.vibroEl = el
    }
    return this.vibroEl
  }

  // Применение выбранных устройств вывода. Вызывается при старте
  // и из AudioDevicePanel при каждом изменении.
  async applyOutputs({ monitorSinkId, vibroSinkId, vibroEnabled } = {}) {
    this.vibroEnabled = !!vibroEnabled && !!vibroSinkId

    const main = this._ensureEl()
    if (typeof main.setSinkId === 'function') {
      try {
        await main.setSinkId(monitorSinkId || '')
      } catch (e) {
        // Устройство могло исчезнуть (другая машина, выдернут USB) —
        // деградируем в системное, а не молчим.
        console.warn('[audio] monitor setSinkId failed:', e && e.name)
        try { await main.setSinkId('') } catch {}
      }
    }

    if (this.vibroEnabled) {
      const v = this._ensureVibroEl()
      if (typeof v.setSinkId !== 'function') {
        console.warn('[vibro] setSinkId не поддерживается — вибро выключен')
        this.vibroEnabled = false
        return
      }
      try {
        await v.setSinkId(vibroSinkId)
      } catch (e) {
        console.warn('[vibro] setSinkId failed:', e && e.name, '— вибро выключен')
        this.vibroEnabled = false
      }
    }
  }

  setEnabled(v) {
    this.enabled = Boolean(v)
    if (!this.enabled) this.stop()
  }

  stop() {
    for (const el of [this.el, this.vibroEl]) {
      if (!el) continue
      try {
        el.pause()
        el.currentTime = 0
      } catch (_e) {}
    }
  }

  // ВАЖНО: вызывается синхронно из обработчика жеста.
  // Громкость НЕ трогаем: WAV и так беззвучный, а манипуляции
  // с volume при двойном вызове оставляли элемент на нуле навсегда.
  unlock() {
    if (this.unlocked || this.unlocking) return
    this.unlocking = true
    const el = this._ensureEl()
    el.src = SILENT_WAV
    const p = el.play()
    const finish = () => {
      this.unlocked = true
      this.unlocking = false
      console.log('[audio] unlocked')
    }
    if (p && typeof p.then === 'function') {
      p.then(finish).catch((err) => {
        // AbortError здесь безвреден: жест уже зачтён элементу.
        finish()
        console.debug('[audio] unlock warning:', err && err.name)
      })
    } else {
      finish()
    }

    // Тем же жестом разблокируем вибро-элемент: без этого его первый
    // play() упрётся в автоплей-политику.
    const v = this._ensureVibroEl()
    v.src = SILENT_WAV
    const pv = v.play()
    if (pv && typeof pv.catch === 'function') pv.catch(() => {})
  }

  _playVibro(role, n) {
    if (!this.vibroEnabled) return
    const v = this._ensureVibroEl()
    v.volume = 1
    v.muted = false
    // ЗАМЕНИТЬ на vibroFilePath(role, n), когда заказчица пришлёт дорожки.
    v.src = soundFilePath(role, n)
    try { v.currentTime = 0 } catch (_e) {}
    const p = v.play()
    if (p && typeof p.catch === 'function') {
      p.catch((err) => console.warn('[vibro] play failed:', err && err.name))
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
    // Страховка от любых прошлых сбоев: элемент всегда звучащий.
    el.volume = 1
    el.muted = false
    el.src = src
    el.play().catch((err) => {
      console.warn('[audio] play failed:', err && err.name, err && err.message, src)
    })
    this._playVibro(role, clickNumber)
  }

  bindUnlock() {
    const evs = ['pointerdown', 'mousedown', 'keydown', 'touchstart']
    evs.forEach((ev) =>
      window.addEventListener(ev, this._boundUnlock, { capture: true, passive: true })
    )
  }

  // Совместимость с текущими вызовами в App.jsx — заглушки.
  startKeepAliveLoop() {}
  stopKeepAliveLoop() {}
}

export const audioEngine = new AudioEngine()
export { soundFilePath }