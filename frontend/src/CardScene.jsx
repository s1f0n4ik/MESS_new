


import { useEffect, useState } from 'react'

// ЭТАЛОННЫЙ ХОЛСТ. Вся сцена рисуется в этих координатах,
// затем целиком масштабируется под реальный экран через transform: scale().
const SCENE_WIDTH = 3440
const SCENE_HEIGHT = 1440

// Размеры из ТЗ: изображение 648×432, поля 284 по бокам, 213 сверху/снизу,
// зазор между карточками 60, между рядами 156.
const CARD_WIDTH = 648
const CARD_HEIGHT = 432

const COL_STEP = CARD_WIDTH + 60   // 708
const ROW_STEP = CARD_HEIGHT + 156 // 588
const MARGIN_X = 284
const MARGIN_Y = 213

//const CARD_POSITIONS = Array.from({ length: 8 }, (_, i) => ({
//  left: MARGIN_X + (i % 4) * COL_STEP,
//  top: MARGIN_Y + Math.floor(i / 4) * ROW_STEP,
//}))
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
  //useAntiVandal()

  const [flipped, setFlipped] = useState({})

  const handleClick = (cardNumber) => {
    setFlipped((prev) => ({ ...prev, [cardNumber]: !prev[cardNumber] }))
    if (onCardClick) onCardClick(cardNumber - 1)
  }
  useEffect(() => {
  CARDS.forEach((n) => {
    const img = new Image()
    img.src = `/cards/images/back/${n}.png`
  })
}, [])

  return (
    <div className="pc-scene-root">
      <div
        className="pc-scene-canvas"
        style={{
          width: SCENE_WIDTH,
          height: SCENE_HEIGHT,
          transform: `scale(${scale})`,
        }}
      >
        {CARDS.map((n, i) => {
          const pos = CARD_POSITIONS[i]
          const isFlipped = Boolean(flipped[n])
          return (
            <div
              key={n}
              className={`pc-card${isFlipped ? ' is-flipped' : ''}`}
              onClick={() => handleClick(n)}
              style={{
                left: pos.left,
                top: pos.top,
                width: CARD_WIDTH,
                height: CARD_HEIGHT,
              }}
            >
              <div className="pc-card__inner">
                <img
                  className="pc-card__face"
                  src={`/cards/images/${isFlipped ? 'back' : 'front'}/${n}.png`}
                  alt={`card ${n}`}
                  draggable={false}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}