import { useEffect, useState } from 'react'
import { audioEngine } from './audioEngine'

async function listOutputs() {
  // Без разрешения enumerateDevices отдаёт пустые label (подтверждено
  // на WebView2) — поэтому сначала getUserMedia, поток сразу гасим.
  try {
    const s = await navigator.mediaDevices.getUserMedia({ audio: true })
    s.getTracks().forEach((t) => t.stop())
  } catch (e) {
    console.warn('[audio] mic permission for labels denied:', e && e.name)
  }
  const all = await navigator.mediaDevices.enumerateDevices()
  return all.filter((d) => d.kind === 'audiooutput')
}

export function AudioDevicePanel({ settings, onChange }) {
  const [outputs, setOutputs] = useState(null)

  const refresh = () => listOutputs().then(setOutputs).catch(() => setOutputs([]))
  useEffect(() => { refresh() }, [])

  // Любое изменение сразу применяем к движку и отдаём наверх в localSettings.
  const apply = (patch) => {
    const next = { ...settings, ...patch }
    onChange(patch)
    audioEngine.applyOutputs({
      monitorSinkId: next.audioMonitorSinkId,
      vibroSinkId: next.audioVibroSinkId,
      vibroEnabled: next.vibroEnabled,
    })
  }

  const select = (value, onPick) => (
    <select value={value || ''} onChange={(e) => onPick(e.target.value)}>
      <option value="">— системное по умолчанию —</option>
      {(outputs || []).map((d) => (
        <option key={d.deviceId} value={d.deviceId}>
          {d.label || `выход ${d.deviceId.slice(0, 8)}…`}
        </option>
      ))}
    </select>
  )

  return (
    <div style={{ margin: '12px 0', padding: 12, border: '1px solid #444', borderRadius: 8 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>
        Аудиоустройства{' '}
        <button onClick={refresh} style={{ marginLeft: 8 }}>обновить список</button>
      </div>

      {outputs && !outputs.length && (
        <div style={{ color: '#e88', fontSize: 13 }}>
          Выходы не видны — вероятно, не выдано разрешение на микрофон
          (оно нужно только для имён устройств).
        </div>
      )}

      <div style={{ fontSize: 13, lineHeight: 2 }}>
        <div>
          Мониторы (клики):{' '}
          {select(settings.audioMonitorSinkId, (v) => apply({ audioMonitorSinkId: v }))}
          <button style={{ marginLeft: 8 }} onClick={() => audioEngine.play('pc1', 1)}>
            тест ▶
          </button>
        </div>
        <div>
          <label>
            <input
              type="checkbox"
              checked={!!settings.vibroEnabled}
              onChange={(e) => apply({ vibroEnabled: e.target.checked })}
            />{' '}
            Вибро-финал
          </label>{' '}
          {select(settings.audioVibroSinkId, (v) => apply({ audioVibroSinkId: v }))}
          <button
            style={{ marginLeft: 8 }}
            disabled={!settings.vibroEnabled}
            onClick={() => audioEngine.playVibroFinal()}
          >
            тест вибро ▶
          </button>
          <button style={{ marginLeft: 4 }} onClick={() => audioEngine.stopVibro()}>
            ■
          </button>
        </div>
        <div>
          Задержка вибро после final_hold, сек:{' '}
          <input
            type="number"
            min="0"
            step="1"
            value={settings.vibroDelaySeconds ?? 120}
            onChange={(e) => onChange({ vibroDelaySeconds: Number(e.target.value) || 0 })}
            style={{ width: 80 }}
          />
        </div>
      </div>

      <div style={{ marginTop: 6, fontSize: 12, opacity: 0.7 }}>
        Вибро-финал (/cards/audio/vibro/final.wav) играет на этой машине через выбранное
        устройство спустя заданную задержку после входа сценария в final_hold.
        Включать его только на той машине, к которой подключён вибродинамик
        (или на единственном ноутбуке). deviceId привязан к origin:
        после установки прод-сборки устройства нужно выбрать заново.
      </div>
    </div>
  )
}