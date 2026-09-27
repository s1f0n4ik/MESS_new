const AUDIO_BASE = '/cards/audio'
const VIBRO_FINAL = `${AUDIO_BASE}/vibro/final.wav`
const CIRCLES_MAX = 4

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

function circleFilePath(n) {
  return `${AUDIO_BASE}/circles/circle${n}.wav`
}

class AudioEngine {
  constructor() {
    this.enabled = true
    this.el = null
    this.vibroEl = null
    this.vibroEnabled = false
    this.unlocked = false
    this.unlocking = false
    // Настраиваемые дорожки с координатора (state.media.audio) и его origin.
    this.mediaOrigin = ''
    this.mediaAudio = null
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
      el.addEventListener('ended', () => console.log('[vibro] ended'))
      this.vibroEl = el
    }
    return this.vibroEl
  }

  // ---------- настраиваемые дорожки ----------

  // audio: { circle1: {file, mtime}, ..., vibro_final: {...} } или null.
  setMedia(origin, audio) {
    this.mediaOrigin = origin || ''
    this.mediaAudio = audio || null
  }

  // URL настраиваемого файла для слота, либо null — тогда играем встроенный.
  _serverTrack(slot) {
    const m = this.mediaAudio && this.mediaAudio[slot]
    if (!m || !m.file) return null
    return `${this.mediaOrigin}/audio/${encodeURIComponent(m.file)}?v=${m.mtime || 0}`
  }

  // ---------- устройства вывода ----------

  async applyOutputs({ monitorSinkId, vibroSinkId, vibroEnabled } = {}) {
    this.vibroEnabled = !!vibroEnabled

    const main = this._ensureEl()
    if (typeof main.setSinkId === 'function') {
      try {
        await main.setSinkId(monitorSinkId || '')
      } catch (e) {
        console.warn('[audio] monitor setSinkId failed:', e && e.name, '→ системное')
        try { await main.setSinkId('') } catch {}
      }
    }

    if (this.vibroEnabled) {
      const v = this._ensureVibroEl()
      if (typeof v.setSinkId === 'function') {
        try {
          await v.setSinkId(vibroSinkId || '')
        } catch (e) {
          console.warn('[vibro] setSinkId failed:', e && e.name, '→ системное')
          try { await v.setSinkId('') } catch {}
        }
      } else if (vibroSinkId) {
        console.warn('[vibro] setSinkId не поддерживается — вибро пойдёт в системное устройство')
      }
    }
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

  stopVibro() {
    if (!this.vibroEl) return
    try {
      this.vibroEl.pause()
      this.vibroEl.currentTime = 0
    } catch (_e) {}
  }

  stopAll() {
    this.stop()
    this.stopVibro()
  }

  // ВАЖНО: вызывается синхронно из обработчика жеста. Громкость не трогаем.
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
        finish()
        console.debug('[audio] unlock warning:', err && err.name)
      })
    } else {
      finish()
    }

    // Тем же жестом разблокируем вибро-элемент: финал играет без клика.
    const v = this._ensureVibroEl()
    v.src = SILENT_WAV
    const pv = v.play()
    if (pv && typeof pv.catch === 'function') pv.catch(() => {})
  }

  // Общий путь для монитор-канала: обрыв предыдущего + новый src на том же элементе.
  _playOnMain(src, onFail) {
    const el = this._ensureEl()
    try {
      el.pause()
      el.currentTime = 0
    } catch (_e) {}
    el.volume = 1
    el.muted = false
    el.src = src
    const p = el.play()
    if (p && typeof p.catch === 'function') {
      p.catch((err) => {
        if (onFail) onFail(err)
        else console.warn('[audio] play failed:', err && err.name, err && err.message, src)
      })
    }
  }

  // Звук клика открытки (встроенные, не настраиваются).
  play(role, clickNumber) {
    if (!this.enabled) return
    this._playOnMain(soundFilePath(role, clickNumber))
  }

  // Встроенный звук волны: circle{N}.wav, нет — откат на circle1.wav.
  _playBundledCircle(num) {
    const src = circleFilePath(num)
    this._playOnMain(src, (err) => {
      if (num !== 1 && err && err.name === 'NotSupportedError') {
        console.log(`[audio] circle${num}.wav не найден → circle1.wav`)
        this._playOnMain(circleFilePath(1))
        return
      }
      console.warn('[audio] circle play failed:', err && err.name, err && err.message, src)
    })
  }

  // Звук начала волны: настраиваемый с координатора, иначе встроенный.
  playCircle(n) {
    if (!this.enabled) return
    const num = Math.max(1, Math.min(CIRCLES_MAX, Number(n) || 1))
    const custom = this._serverTrack(`circle${num}`)
    if (!custom) {
      this._playBundledCircle(num)
      return
    }
    this._playOnMain(custom, (err) => {
      console.warn('[audio] custom circle failed:', err && err.name, custom, '→ встроенный')
      this._playBundledCircle(num)
    })
  }

    /**
   * Играет фрагмент клика и резолвится, когда он дослушан.
   * why: ended | disabled | error | replaced | not_playing — уходит в журнал.
   */
  playAndWait(role, n) {
    return new Promise((resolve) => {
      if (!this.enabled) { resolve({ why: 'disabled' }); return }
      const el = this._ensureEl()
      let done = false
      let watchdog = null
      const finish = (why) => {
        if (done) return
        done = true
        clearInterval(watchdog)
        el.removeEventListener('ended', onEnded)
        el.removeEventListener('error', onError)
        resolve({ why })
      }
      const onEnded = () => finish('ended')
      const onError = () => finish('error')
      el.addEventListener('ended', onEnded)
      el.addEventListener('error', onError)
      this.play(role, n)
      const mySrc = el.src
      // Кто-то другой сменил src (playCircle и т.п.) — не ждём чужой ended.
      // Через 1.5 с элемент так и не заиграл (autoplay/файла нет) — не вешаем гейт.
      const startedAt = Date.now()
      watchdog = setInterval(() => {
        if (el.src !== mySrc) finish('replaced')
        else if (Date.now() - startedAt > 1500 && el.paused && !el.ended) finish('not_playing')
      }, 250)
    })
  }

  // Финальная вибро-дорожка: настраиваемая, иначе встроенная final.wav.
  playVibroFinal() {
    if (!this.vibroEnabled) {
      console.log('[vibro] канал выключен — финал пропущен')
      return
    }
    const v = this._ensureVibroEl()
    try {
      v.pause()
      v.currentTime = 0
    } catch (_e) {}
    v.volume = 1
    v.muted = false
    v.src = this._serverTrack('vibro_final') || VIBRO_FINAL
    const p = v.play()
    if (p && typeof p.catch === 'function') {
      p.catch((err) => console.warn('[vibro] play failed:', err && err.name, err && err.message))
    }
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