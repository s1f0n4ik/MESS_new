// Синглтон аудио-движка. Один переиспользуемый HTMLAudioElement,
// резкий обрыв предыдущего звука (как в легаси), keep-alive для автоплея.

const AUDIO_BASE = '/cards/audio';

// Шаблон имени зависит от роли: pc1 особый ("cliks1st"), остальные "cliks2/3/4".
function soundFileName(role, clickNumber) {
  const n = Math.max(1, Math.min(16, Number(clickNumber) || 1));
  const byRole = {
    pc1: `cliks1st type ${n}.wav`,
    pc2: `cliks2 type ${n}.wav`,
    pc3: `cliks3 type ${n}.wav`,
    pc4: `cliks4 type ${n}.wav`,
  };
  return byRole[role] || byRole.pc1;
}

function soundFilePath(role, clickNumber) {
  return `${AUDIO_BASE}/${role}/${encodeURIComponent(soundFileName(role, clickNumber))}`;
}

const KEEP_ALIVE_SRC = soundFilePath('pc1', 1);
const KEEP_ALIVE_VOLUME = 0.01;
const KEEP_ALIVE_INTERVAL_MS = 2 * 60 * 1000;

class AudioEngine {
  constructor() {
    this.enabled = true;
    this.current = null;         // текущий HTMLAudioElement
    this.keepAlive = null;
    this.keepAliveTimer = null;
    this.unlocked = false;
    this._boundUnlock = this._unlockHandler.bind(this);
  }

  setEnabled(value) {
    this.enabled = Boolean(value);
    if (!this.enabled) this.stop();
  }

  stop() {
    if (this.current) {
      try {
        this.current.pause();
        this.current.currentTime = 0;
      } catch (_e) {}
      this.current = null;
    }
  }

  // Резкий обрыв предыдущего + новый звук (семантика легаси).
  play(role, clickNumber) {
    if (!this.enabled) return;
    this.stop();
    const audio = new Audio(soundFilePath(role, clickNumber));
    this.current = audio;
    audio.play().catch(() => {});
  }

  // Разблокировка автоплея по первому пользовательскому жесту.
  bindUnlock() {
    ['pointerdown', 'keydown', 'touchstart'].forEach((ev) =>
      window.addEventListener(ev, this._boundUnlock, { once: false, passive: true })
    );
  }

  _unlockHandler() {
    if (this.unlocked) return;
    this.unlocked = true;
    this._ensureKeepAlive();
    const ka = this.keepAlive;
    if (ka) {
      ka.play().then(() => {
        ka.pause();
        ka.currentTime = 0;
      }).catch(() => {});
    }
    ['pointerdown', 'keydown', 'touchstart'].forEach((ev) =>
      window.removeEventListener(ev, this._boundUnlock)
    );
  }

  _ensureKeepAlive() {
    if (this.keepAlive) return this.keepAlive;
    const audio = new Audio(KEEP_ALIVE_SRC);
    audio.preload = 'auto';
    audio.volume = KEEP_ALIVE_VOLUME;
    this.keepAlive = audio;
    try { audio.load(); } catch (_e) {}
    return audio;
  }

  startKeepAliveLoop() {
    this._ensureKeepAlive();
    this.stopKeepAliveLoop();
    this.keepAliveTimer = setInterval(() => {
      if (!this.keepAlive || !this.unlocked) return;
      try {
        this.keepAlive.currentTime = 0;
        this.keepAlive.play().then(() => {
          setTimeout(() => {
            try { this.keepAlive.pause(); this.keepAlive.currentTime = 0; } catch (_e) {}
          }, 50);
        }).catch(() => {});
      } catch (_e) {}
    }, KEEP_ALIVE_INTERVAL_MS);
  }

  stopKeepAliveLoop() {
    if (this.keepAliveTimer) {
      clearInterval(this.keepAliveTimer);
      this.keepAliveTimer = null;
    }
  }
}

export const audioEngine = new AudioEngine();
export { soundFilePath };