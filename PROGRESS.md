# PROGRESS

Журнал фактически сделанного. Пишем сверху вниз по датам. Только то, что реально работает в коде.

## Архитектура (зафиксировано)
Монорепа:
- `/backend` — FastAPI + (план) WebSocket + Zeroconf + persist JSON. Координатор состояния.
- `/frontend` — React (Vite). Роуты: главная сцена / экфрасисы (popup) / админка.
- `/desktop` — Tauri-оболочка. Нативное управление окнами, Python sidecar, кросс-платформенный запуск.
- Docker (`docker-compose.yml`) для дев-окружения backend+frontend.

Решение по платформенным костылям: управление окнами (PDF-окно, minimize all) в новом варианте делаем нативно через Tauri WebviewWindow, НЕ через PowerShell/WinApi как в старом JS-варианте.

## Slice 1 — каркас (готово)
- Поднята структура монорепы: backend / frontend / desktop.
- Tauri-каркас инициализирован (`src-tauri`, иконки, конфиг) — пока дефолтный, без нашей логики.
- Docker-окружение: Dockerfile для backend (python:3.12-slim) и frontend (node:22), docker-compose, vite-proxy на backend (`/api`, `/pdfs`).

## Slice 2 — сквозная вертикаль состояния (готово)
Backend (`backend/main.py`):
- FastAPI + CORS.
- Единое in-memory состояние `STATE` + `initial_state()`.
- SSE-стрим `/api/stream` (initial snapshot + push по изменениям + ping-keepalive 15с).
- `GET /api/state`, `GET /api/health`.
- `POST /api/action` с экшенами: `click_card`, `open_role_popup`, `close_role_popup`, `launch`, `reset_all`.
- Счётчики кликов по ролям, переворот карточек, lock роли, порог кликов (17) → старт сценария (всегда с pc1).
- Раздача PDF из `/pdfs` (статикой).
- Заглушки состояния: scenario (active/openRoles/popupEpoch), pdfWindow (visible/role/pdfFile/token).

Frontend (`frontend/src/App.jsx`):
- Подписка на `/api/state` + EventSource на `/api/stream`.
- Сетка из 8 карточек, переворот по клику, индикатор stateVersion / clicks / scenario.
- Кнопки: Open PDF (открывает `pdf-viewer.html` в отдельном окне через window.open), Close PDF, Launch, Reset.
- `pdf-viewer.html` во `frontend/public` — отдельная страница просмотрщика (черновая).


## Slice 3 — WebSocket-транспорт (готово)
Backend (`backend/main.py`):
- Эндпоинт `WebSocket /ws`: accept, приём сообщений, broadcast состояния подключённым клиентам.
- Приём `identify` (role, hostName) от клиента.
- Состояние пушится по `/ws` при изменениях (наряду/взамен SSE — уточнить, см. тех-долг).

Frontend (`frontend/src/App.jsx`):
- Создание `WebSocket` к `/ws` (через vite-proxy), отправка `identify`, приём снапшотов состояния.
- Reconnect при разрыве (черновой).

Инфраструктура:
- `frontend/vite.config.js`: добавлен проксируемый блок `/ws` с `ws: true` (target `http://backend:8787`).
- Подтверждено end-to-end: бэк логирует `WebSocket /ws [accepted]` + `connection open`.

## Slice 4 — единый транспорт + стабилизация WS (готово)
- Подтверждено: SSE полностью отсутствует (нет `/api/stream`, нет `EventSource`). Источник правды — только WS `/ws`.
- `App.jsx`: `ROLESLIST` поднят в начало модуля (был в TDZ-зоне внизу файла).
- `App.jsx`: пуленепробиваемый teardown в `useEffect` — перед `ws.close()` отвязываются обработчики (особенно `onclose`), поэтому размонтирование не триггерит reconnect. Добавлены guard'ы `if (stopped)` в `connect()` и `onopen`.
- Итог: бесконечное «дёргание» open→closed→open устранено. Остаётся ровно один цикл при старте в dev из-за React StrictMode double-mount — это ожидаемо.

## Slice 5 — модель волн (ядро, перенос из server.js) (готово)
- В `STATE.scenario` добавлены поля волн: `waveIndex` (0..4), `waveSettled`, плюс `forceOpenAll`/`restoreAfterForce`/`phase`/`popupPage`/`trigger`.
- Перенесены из server.js (один-в-один по семантике): `recompute_wave_settled`, `start_scenario`, `open_role`, `close_role`, `advance_wave`, `toggle_force_open_all`, `close_scenario`, `hard_reset`. Плюс `sync_pdf_window` (намерение для desktop-слоя).
- `launch` переписан с «круга ролей» на эталонную семантику advance-wave: 1→2→3→4→close. Сам роли НЕ открывает (как в оригинале) — открывают отдельные команды open_role_popup. Это будущая развязка MIDI launch / open pcX.
- Сброс разнесён: `reset_scenario` (close_scenario, сохраняет clicks/locks/flips) и `hard_reset` (обнуляет всё).
- Тех-долг закрыт попутно: close_scenario/hard_reset сохраняют connectedDevices.
- `App.jsx`: дев-тулбар — Launch (advance), Force open all, open/close pcX, Reset scenario, Hard reset + отладочная строка состояния волны.

## Slice 6 — резолв PDF-окна (готово)
Перенос логики выбора PDF из эталонного `app.js` (`currentPopupPayload`) на фронт.

Frontend:
- `frontend/src/pdf/resolvePdfWindow.js` — чистая функция-резолвер. КЛЮЧЕВОЙ ИНВАРИАНТ
  (подтверждён эталоном, НЕ инвертировать):
    · waveSettled === true  → каждый ПК показывает СВОЙ pcX.pdf (sourceRole = myRole)
    · waveSettled === false → круг идёт, все видимые показывают pc{waveIndex}.pdf
    · visible = forceOpenAll || openRoles[myRole]
    · forceOpenAll → каждый свой домашний PDF (sourceRole = myRole)
  Возвращает {visible, sourceRole, pdfFile, token}. token = `${popupEpoch}:${myRole}:${sourceRole}`
  (заготовка под дедуп синка натив-окна, EPIC C).
- `frontend/src/pdf/PdfWindowLayer.jsx` — реактивный слой (useMemo от state+role).
  Рендерит реальный `<iframe src="/pdfs/...#toolbar=0&navpanes=0&zoom=120">` поверх всего
  (position:fixed, inset:0, z-index:50) когда payload.visible. Шапка __meta показывает
  myRole/source/pdfFile + кнопка ✕ close (проп onClose → close_role_popup).
- `App.jsx`: подключён `<PdfWindowLayer state={state} onClose={...} />` последним в дереве.
- Роль берётся из `?role=pcX` (временно, до EPIC A).

Backend:
- В этом слайсе НЕ менялся. Поля `pdfsByRole` (pc1.pdf..pc4.pdf) и `scenario`
  (openRoles/forceOpenAll/waveIndex/waveSettled/popupEpoch) уже отдавались в публичном
  снапшоте с прошлых слайсов — резолверу хватило.

Подтверждено вживую: окно открывается, source переключается по фазе волны.

Сознательно НЕ сделано в Slice 6 (вынесено в BACKLOG):
- mtime cache-buster (`?v={mtime}`) для «PDF переписали на диске вживую» → EPIC C.
- Вкладки внутри окна (addPdfTab из pdf.html) — это отдельная модель, НЕ резолв
  currentPopupPayload (он даёт ровно один файл на окно). Не смешивать с автоматикой волн.
- pdfWindowsByRole (per-окно activeBookmark) — резолв per-client по myRole закрывает кейс
  без серверного словаря окон; на каждой машине свой клиент со своей ролью.


## Известные временные решения (тех-долг, см. BACKLOG)
- Управление окнами через `window.open`, не через Tauri. Заголовок/размеры/позиция не контролируются.
- Состояние не персистится (нет local-settings.json / global-settings.json).
- Нет MIDI, нет аудио, нет popup-экфрасисов, нет админки, нет сети/discovery.
- WS-соединения в dev «дёргаются» (open→closed→open) — подозрение на React StrictMode double-mount и/или незаглушённый reconnect. Проверить очистку в useEffect.
- Роль всё ещё хардкод/из query (`?role=pc1`), не из настроек.
- Выбор источника PDF по waveSettled (своя pcX.pdf vs pcN.pdf волны) ещё не реализован — pdfWindow.pdfFile сейчас всегда = pdf текущей роли. Slice 6.
- pdfWindow — пока только «намерение» в состоянии, исполнение окнами через Tauri не подключено (EPIC C).



## EPIC A — DONE (role from settings + lastSeen diagnostics)

Что сделано:
- A1: единый источник роли (role.js), reload-смена через селект, роль = проп в PdfWindowLayer.
- A2: lastSeenAt + фоновый sweeper (30s/5s) + lifespan; UI "Ns назад".

Архитектурные решения:
- lifespan вместо @app.on_event (корректный жизненный цикл asyncio-задачи).
- ping теперь содержательный (двигает lastSeen) — защита от ложного протухания.
- disconnect НЕ трогает lastSeenAt — видно "когда видели в последний раз".
- PdfWindowLayer защищён lastTokenRef от лишних broadcast'ов (их стало больше из-за sweeper).

Самопроверка перед коммитом (прогони руками):
1. Открыть две вкладки, в одной select -> pc2 (reload). В Devices у обеих видно pc1/pc2 🟢 + растущие секунды.
2. Закрыть одну вкладку -> её роль становится ⚪ почти сразу (disconnect), секунды "замораживаются" на моменте ухода.
3. "Жёсткий" обрыв (DevTools -> Network offline на вкладке, НЕ закрывая): через ~30s роль уходит в ⚪ сама (sweeper).
4. Open PDF -> окно открылось у нужной роли; sweeper-broadcast'ы НЕ перефокусируют окно (token не менялся).


## Решение по источнику продвижения волн (вход в Slice 7) 
Зафиксировано из ТЗ (прямая цитата заказчика). 
Источников продвижения ДВА, разнесены по фазам сценария — ранее в BACKLOG это ошибочно стояло как один открытый вопрос «таймер vs MIDI». 
Цитата (ключевое): «...на ПК-1 на время до прихода MIDI-ноты, затем сворачивается, на ПК-2 на время до прихода MIDI-ноты... [pc1→2→3→4→3→2→1] ...затем открывается на ПК-1 и остаётся там. Окно на ПК-1 остаётся открытым на протяжении 2 минут, после чего сворачивается и разворачивается окно на ПК-2 [и т.д. круги 2–4]. Окно на ПК-4 разворачивается и сворачивается, когда в ПК-4 приходит та же MIDI-нота, что и для запуска сценария.» 
Вывод: - Первый круг = MIDI пошагово (7 шагов маятника). - Круги 2–4 = серверный таймер 2 минуты, накопительно. - Финал = MIDI-нота на pc4 → откат. Архитектурное следствие зафиксировано в BACKLOG (Slice 7): waveIndex и pendulumStep — разные оси, advance_wave описывает только круги 2–4. 


## MIDI field-check at installation site
- Подтверждено: Web MIDI в браузере работает на месте установки.
- Подтверждено: rtpMIDI-вход виден в системе и в приложении.
- Обнаружены два MIDI input: `MOTU UltraLite-mk5 MIDI In` и `PC-10`.
- Для сценария инсталляции целевой порт = `PC-10` (совпадает со старой версией).
- Подтверждено соответствие старому MIDI-конфигу из legacy UI:
  - channel = 2
  - launch = 60
  - open pc1..pc4 = 61,63,65,67
  - close pc1..pc4 = 62,64,66,68
  - minimizeAll = 69
  - output = 72
  - velocity = 100
  - duration = 180
- Вывод: можно безопасно опираться на legacy MIDI mapping из server.js/app.js.
- Выявлен следующий техдолг: текущий MIDI monitor слушает все inputs сразу; нужен выбор конкретного input (`PC-10`) во избежание дублей/шума.


## Slice 6.5 — MIDI field-check + legacy compatibility (в работе)
- Подтверждено на месте установки: Web MIDI в Chrome работает, rtpMIDI-порты видны.
- Обнаружены входы: `MOTU UltraLite-mk5 MIDI In` и `PC-10`; целевой инсталляционный порт = `PC-10`.
- Подтверждено, что инсталляция использует тот же legacy MIDI-маппинг, что и старая JS-версия:
  - channel = 2
  - launch = 60
  - open pc1..pc4 = 61,63,65,67
  - close pc1..pc4 = 62,64,66,68
  - minimizeAll = 69
  - output = 72
  - velocity = 100
  - duration = 180
- Текущий MIDI monitor показал сырые входящие noteOn-события по legacy-нотам.
- Выявлен техдолг: монитор сейчас подписывается на все inputs сразу, из-за чего возможны дубли/шум; следующий шаг — выбор одного input (`PC-10`) и дедупликация.


- `MidiPanel.jsx`: добавлен выбор конкретного MIDI input/output, с автопредпочтением `PC-10`.
- Входящие MIDI-события теперь читаются только с выбранного input, а не со всех inputs сразу.
- Добавлен фильтр по каналу, по умолчанию включён на legacy-канале `2`.
- `midiMapping.js`: добавлен предзаполненный legacy-маппинг
  (`60 launch`, `61/63/65/67 open pc1..pc4`, `62/64/66/68 close pc1..pc4`, `69 minimizeAll`).
- Добавлена дедупликация одинаковых `noteOn` в коротком окне (`180ms`).
- Добавлена диспетчеризация MIDI-действий в существующие `sendAction`:
  `launch`, `open_role_popup`, `close_role_popup`, `toggle_force_open_all`,
  `reset_scenario`, `hard_reset`, `minimize_all_windows`.
- Добавлена тест-кнопка MIDI output (`note 72`, velocity `100`, duration `180ms`) в выбранный output.
