import { useEffect, useState } from 'react'

// ЭТАЛОННЫЙ ХОЛСТ. Вся сцена рисуется в этих координатах,
// затем целиком масштабируется под реальный экран через transform: scale().
// На инсталляционном мониторе 3440x1440 scale === 1.0 (пиксель-в-пиксель).
const SCENE_WIDTH = 3440
const SCENE_HEIGHT = 1440

// Размер карточки в эталонных координатах.
// TODO: подтверди реальные значения из старого кода, если отличались.
const CARD_WIDTH = 640
const CARD_HEIGHT = 518

// Жёсткая сетка 2 ряда по 4 (как в старом коде).
const CARD_POSITIONS = [
  { left: 334,  top: 225 },
  { left: 1042, top: 225 },
  { left: 1750, top: 225 },
  { left: 2458, top: 225 },
  { left: 334,  top: 783 },
  { left: 1042, top: 783 },
  { left: 1750, top: 783 },
  { left: 2458, top: 783 },
]

// Порядок раскладки: 1-2-3-4 / 5-6-7-8 (card N -> позиция N).
const CARDS = Array.from({ length: 8 }, (_, i) => i + 1)

function useSceneScale() {
  const [scale, setScale] = useState(1)

  useEffect(() => {
    const recalc = () => {
      const sx = window.innerWidth / SCENE_WIDTH
      const sy = window.innerHeight / SCENE_HEIGHT
      setScale(Math.min(sx, sy))
    }
    recalc()
    window.addEventListener('resize', recalc)
    return () => window.removeEventListener('resize', recalc)
  }, [])

  return scale
}

// Базовый антивандал. В браузере срабатывает частично,
// на Tauri добьём нативно (EPIC C).
function useAntiVandal() {
  useEffect(() => {
    const onContext = (e) => e.preventDefault()
    const onKey = (e) => {
      const k = e.key
      const block =
        k === 'F5' ||
        k === 'F12' ||
        (e.ctrlKey && (k === 'r' || k === 'R')) ||
        (e.ctrlKey && e.shiftKey && (k === 'I' || k === 'J' || k === 'C')) ||
        (e.ctrlKey && (k === 'u' || k === 'U'))
      if (block) {
        e.preventDefault()
        e.stopPropagation()
      }
    }
    window.addEventListener('contextmenu', onContext)
    window.addEventListener('keydown', onKey, true)
    return () => {
      window.removeEventListener('contextmenu', onContext)
      window.removeEventListener('keydown', onKey, true)
    }
  }, [])
}

export function CardScene({ onCardClick }) {
  const scale = useSceneScale()
  useAntiVandal()

  // Перевороты только в памяти — reload сбрасывает (по ТЗ этого этапа).
  const [flipped, setFlipped] = useState({})

  const handleClick = (cardNumber) => {
    const idx = cardNumber - 1
    setFlipped((prev) => ({ ...prev, [cardNumber]: !prev[cardNumber] }))
    if (onCardClick) onCardClick(idx) // тот же cardIndex 0..7, что и раньше
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: '#000',
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        userSelect: 'none',
      }}
    >
      {/* Внутренний холст фиксированного размера, масштабируется целиком */}
      <div
        style={{
          position: 'relative',
          width: SCENE_WIDTH,
          height: SCENE_HEIGHT,
          transform: `scale(${scale})`,
          transformOrigin: 'center center',
          flex: '0 0 auto',
        }}
      >
        {CARDS.map((n, i) => {
          const pos = CARD_POSITIONS[i]
          const isFlipped = Boolean(flipped[n])
          return (
            <div
              key={n}
              onClick={() => handleClick(n)}
              style={{
                position: 'absolute',
                left: pos.left,
                top: pos.top,
                width: CARD_WIDTH,
                height: CARD_HEIGHT,
                perspective: 1600,
                cursor: 'pointer',
              }}
            >
              <div
                style={{
                  position: 'relative',
                  width: '100%',
                  height: '100%',
                  transition: 'transform 0.6s',
                  transformStyle: 'preserve-3d',
                  transform: isFlipped ? 'rotateY(180deg)' : 'rotateY(0deg)',
                }}
              >
                {/* FRONT */}
                <img
                  src={`/cards/images/front/${n}.png`}
                  alt={`card ${n} front`}
                  draggable={false}
                  style={{
                    position: 'absolute',
                    inset: 0,
                    width: '100%',
                    height: '100%',
                    objectFit: 'contain',
                    backfaceVisibility: 'hidden',
                  }}
                />
                {/* BACK */}
                <img
                  src={`/cards/images/back/${n}.png`}
                  alt={`card ${n} back`}
                  draggable={false}
                  style={{
                    position: 'absolute',
                    inset: 0,
                    width: '100%',
                    height: '100%',
                    objectFit: 'contain',
                    backfaceVisibility: 'hidden',
                    transform: 'rotateY(180deg)',
                  }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}