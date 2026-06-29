// Порт currentPopupPayload() из эталонного app.js.
// КЛЮЧЕВОЙ ИНВАРИАНТ (подтверждён эталоном, НЕ инвертировать):
//   waveSettled === true  -> каждый ПК показывает СВОЙ pcX.pdf (sourceRole = myRole)
//   waveSettled === false -> круг идёт, все видимые показывают pc{waveIndex}.pdf
// Видимость окна = forceOpenAll || openRoles[myRole].

export function resolvePdfWindow(state, myRole) {
  const scenario = state?.scenario || {};
  const pdfsByRole = state?.pdfsByRole || {};

  const openRoles = scenario.openRoles || {};
  const forceOpenAll = Boolean(scenario.forceOpenAll);
  const waveIndex = Number(scenario.waveIndex) || 0;
  const waveSettled = Boolean(scenario.waveSettled);

  const visible = forceOpenAll || Boolean(openRoles[myRole]);

  // По умолчанию — свой домашний PDF.
  let sourceRole = myRole;

  if (!forceOpenAll && waveIndex >= 1) {
    if (waveSettled) {
      // Круг волны завершён — каждый открытый ПК показывает свой домашний PDF.
      sourceRole = myRole;
    } else {
      // Круг идёт — все видимые показывают pc{waveIndex}.pdf текущей волны.
      sourceRole = `pc${waveIndex}`;
    }
  }
  // forceOpenAll -> sourceRole остаётся myRole (каждый свой). Уже покрыто дефолтом.

  const pdfFile = pdfsByRole[sourceRole] || pdfsByRole[myRole] || '';

  return {
    visible,
    sourceRole,
    pdfFile,
    // token — для будущей дедупликации синка натив-окна (EPIC C). Сейчас информативно.
    token: `${scenario.popupEpoch || 0}:${myRole}:${sourceRole}`,
  };
}