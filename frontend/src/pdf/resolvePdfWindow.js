const PENDULUM_ROUTE = ['pc1', 'pc2', 'pc3', 'pc4', 'pc3', 'pc2', 'pc1']

function getPendulumRole(step) {
  if (!Number.isInteger(step)) return null
  return PENDULUM_ROUTE[step] || null
}

// Порт currentPopupPayload() из эталонного app.js + расширение под Slice 7.
// КЛЮЧЕВЫЕ ИНВАРИАНТЫ:
//   forceOpenAll === true          -> каждый ПК показывает СВОЙ pcX.pdf
//   phase === 'pendulum'           -> видно только окно текущей роли шага,
//                                     sourceRole = роль текущего шага маятника
//   waveSettled === true           -> каждый открытый ПК показывает СВОЙ pcX.pdf
//   waveSettled === false          -> круг идёт, все видимые показывают pc{waveIndex}.pdf
//   visible = forceOpenAll || openRoles[myRole]
export function resolvePdfWindow(state, myRole) {
  const scenario = state?.scenario || {}
  const pdfsByRole = state?.pdfsByRole || {}

  const openRoles = scenario.openRoles || {}
  const forceOpenAll = Boolean(scenario.forceOpenAll)
  const phase = scenario.phase || 'idle'
  const waveIndex = Number(scenario.waveIndex) || 0
  const waveSettled = Boolean(scenario.waveSettled)
  const pendulumStep = Number.isInteger(scenario.pendulumStep) ? scenario.pendulumStep : null

  const visible = forceOpenAll || Boolean(openRoles[myRole])

  if (!visible) {
    return {
      visible: false,
      sourceRole: myRole,
      pdfFile: '',
      token: `${scenario.popupEpoch || 0}:${myRole}:hidden`,
    }
  }

  // Force-open-all: каждый клиент показывает свой домашний PDF.
  if (forceOpenAll) {
    const sourceRole = myRole
    return {
      visible: true,
      sourceRole,
      pdfFile: pdfsByRole[sourceRole] || '',
      token: `${scenario.popupEpoch || 0}:${myRole}:${sourceRole}:force`,
    }
  }

  // Первый круг: маятник. Источник PDF = роль текущего шага маятника.
  if (phase === 'pendulum') {
    const stepRole = getPendulumRole(pendulumStep) || myRole
    return {
      visible: true,
      sourceRole: stepRole,
      pdfFile: pdfsByRole[stepRole] || pdfsByRole[myRole] || '',
      token: `${scenario.popupEpoch || 0}:${myRole}:${stepRole}:pendulum:${pendulumStep ?? 'x'}`,
    }
  }

  // Осевшие круги / финал:
  // - settled => свой домашний PDF
  // - moving  => pdf текущей волны
  let sourceRole = myRole
  if (waveIndex >= 1) {
    sourceRole = waveSettled ? myRole : `pc${waveIndex}`
  }

  return {
    visible: true,
    sourceRole,
    pdfFile: pdfsByRole[sourceRole] || pdfsByRole[myRole] || '',
    token: `${scenario.popupEpoch || 0}:${myRole}:${sourceRole}:${phase}`,
  }
}