# BACKLOG

Что осталось сделать до финальной цели. Сгруппировано по эпикам. Внутри эпиков — по приоритету.
Статусы: [ ] todo · [~] в работе · [x] done · [!] тех-долг/требует решения

## EPIC A — Транспорт и сеть
- [x] Перевести SSE → WebSocket (двусторонний). Клиент шлёт identify (role, hostName). `/ws` проксируется vite, end-to-end подтверждён.
- [x] Выпилить SSE (`/api/stream`) либо явно решить роли двух транспортов — сейчас живут оба.
- [x] Починить «дёргающиеся» WS-соединения (open→closed→open): корректный teardown в useEffect, проверка StrictMode, дебаунс reconnect.
- [ ] identify расширить: localIps, wantsServer.
- [x] Координатор ведёт список подключённых устройств (connectedDevices) + lastSeen.
- [ ] Zeroconf/mDNS discovery координатора + ручной ввод IP (serverHost) как fallback.
- [x] Роль клиента (pc1..pc4) как настройка, а не хардкод `?role=pc1`.
- [~] Reconnect-логика на клиенте, статус online/offline.

## EPIC B — Логика сценария и волн (ядро)
- [x] Модель кругов: waveIndex (1..4), waveSettled, popupEpoch, popupPage.
- [x] Cycle-машина: OPEN (накопительно pc1→pcN) → HOLD (n сек) → CLOSE (обратно pcN→pc1)
      → SETTLE (осевшая раскладка pc1..pcN с вкладками) → следующий круг → FINAL_HOLD.
- [x] forceOpenAll — открыть/закрыть окна на всех ПК (+ restoreAfterForce).
- [x] Разнести сброс: reset_scenario (сохраняет клики/перевороты) и hard_reset.
- [x] Выбор источника PDF: во время пробега круга N все открытые несут pdf{N};
      в SETTLE на pcK активна вкладка K, доступны вкладки 1..N.
- [x] Серверные таймеры: stepSeconds (шаг sweep), holdSeconds (n сек удержания),
      gapSeconds (пауза между кругами, боевое 120с).
- [x] Модель закладок окна: серверная, pdfWindowsByRole = {visible, tabs, activeTab, token}.
      Переключение вкладок — локальное на клиенте, сервер задаёт только дефолт.
- [x] Порог кликов (17) → старт сценария + lock роли. Подтверждён вживую:
      17 click_card в phase=idle → автоматический прогон 4 кругов без ручных экшенов.
- [x] Боевой финал: launch в FINAL_HOLD → close_scenario. Подтверждено логом
      (force-ветка из админки). Ветка от finalHoldRole — та же функция,
      подтвердится MIDI-прогоном.
- [x] Семантика локов зафиксирована (вариант Б): после боевого финала лок
      сохраняется, клики не обнуляются. Причина: после ноты начинается
      другой блок представления, самоперезапуск сценария был бы помехой.
      Сброс — кнопка медиатора (hard_reset). close_scenario по умолчанию
      сохраняет clicks/locks/flips.
- [x] Фаза manual_midi не считается занятостью сценария (busy),
      ручной open_role_popup не блокирует порог до вмешательства медиатора.

## EPIC C — Управление окнами (Tauri v2, нативно)
- [x] PDF-окно как нативное WebviewWindow: 1968×1392, без декораций,
      по центру монитора со смещением +100 X / −50 Y.
- [x] Открыть/скрыть/сфокусировать/переместить PDF-окно из состояния
      (open_pdf_window / close_pdf_window / windowDriver.js).
- [x] Свой рендер PDF через pdfjs-dist вместо встроенного вьюера WebKitGTK
      (иначе SecurityError на cross-origin frame и неубираемый тулбар).
- [!] Крашей X11 больше нет: причина была в отсутствии XInitThreads до gtk_init.
      Не удалять init_x11_threads() и не вызывать set_size/set_position
      вне run_on_main_thread — вернётся [xcb] Aborting.
- [ ] Перезагрузка PDF по mtime файла (cache-buster ?v={mtime}).
- [ ] «Свернуть все окна» — уточнить семантику: minimize_all сворачивает только
      окна нашего процесса, «все окна ОС» требует платформенного вызова.
- [ ] Управление кэшем профиля просмотрщика (размер + очистка).
- [ ] Антивандал добить нативно: фиксированный zoom вместо JS-перехвата
      Ctrl+колесо / pinch / auxclick.

## EPIC D — Главная сцена
- [x] Жёсткая сетка 3440×1440, CARD_POSITIONS (2 ряда по 4), scale под экран.
- [x] Реальные картинки front/back открыток.
- [x] Адаптация не только под 3440×1440.
- [x] Меню только при ?admin=1, тоггл по физической клавише M (e.code).
- [~] Антивандал: сделано contextmenu, F5/F12/Ctrl+R/Ctrl+Shift+IJC/Ctrl+U,
      userSelect:none, draggable=false. Осталось Ctrl+колесо/pinch/auxclick → EPIC C.
- [~] Хоткеи: M меню и Esc есть. Осталось E (редактирование), Q (перевернуть все),
      F (fullscreen), Ctrl+Shift+R (сброс).

## EPIC E — Аудио
- [x] 16 типов звуков на ПК, проигрывание по клику, прерывание предыдущего.
- [x] Keep-alive аудио-loop (разблокировка автоплея).
- [x] Включение/выключение аудио в настройках.
- [x] Работа под Tauri/WebKitGTK (единый HTMLAudioElement + unlock по жесту).

## EPIC F — MIDI (backend, Python)
- [x] Решение принято: Web MIDI недоступен в WebKitGTK и WebView2, MIDI живёт
      в бэкенде. midi_config.py / midi_service.py / midi_router.py,
      main.py только include_router.
- [x] Legacy-маппинг перенесён один-в-один (ch2, launch 60, open 61/63/65/67,
      close 62/64/66/68, minimizeAll 69, out 72 v100 180ms), дедуп 180ms,
      фильтр канала, persist в midi-settings.json.
- [x] launch подставляет role=finalHoldRole: порт слушает координатор,
      поэтому «нота пришла на pc4» задаётся состоянием, а не слушателем.
- [x] Гонка потоков исключена: колбэк rtmidi только кладёт в asyncio-очередь,
      apply_action вызывается из таска событийного цикла.
- [x] Нота 60 — только закрытие в FINAL_HOLD. Старт сценария исключительно
      от 17 кликов (нота из Reaper приходит по расписанию, дублирующий старт
      дал бы двойной запуск при живом final_hold).
      В прочих фазах нота логируется как launch_ignored — чтобы на стенде
      «нота пришла, эффекта нет» не читалось как поломка.
- [x] Frontend: MidiPanel переписана на /api/midi/*. Web MIDI удалён.
      Поллинг статуса 1с (лог не часть игрового состояния — не гнать в broadcast).
      Черновик маппинга отделён от применённого, чтобы поллинг не перетирал
      правки оператора.
- [ ] Зачистка мёртвого кода: midiMapping.js (оставить только MIDI_ACTIONS
      и LEGACY_*-константы), midiNote.js (parseMidi/mapKey), localSettings
      (midiInputId/midiOutputId/midiFilterEnabled/midiFilterChannel).
- [~] Полевая проверка на PC-10 + сквозной боевой прогон:
      17 кликов → 4 круга → нота 60 на ch2 от pc4 → откат.
- [x] Поллинг /api/midi/status остановлен при document.hidden, доступ-лог
      uvicorn для этого маршрута отфильтрован. Причина: 60 запросов в минуту
      с каждого клиента вытесняли [action] и [tick] из лога боевого прогона.

## EPIC G — Окно экфрасисов (popup 2052×966)
- [ ] Разворот: 2 страницы (картинка + side-text + bottom-text), 8 разворотов, навигация.
- [ ] Режим редактирования (E, только на сервере), хранение текстов.
- [ ] Синхронизация текущей страницы между окнами.
- [ ] Анимации открытия/закрытия.

## EPIC H — Настройки и персист
- [x] global-settings.json на координаторе: GET/POST /api/settings/global
      (stepSeconds, holdSeconds, gapSeconds), initial_state читает GLOBAL_SETTINGS.
- [~] Локальные настройки через localStorage (localSettings.js): role, serverHost,
      audioEnabled, midi*. Осталось: файл вместо localStorage (Tauri), PDF-маппинг.
- [ ] Сброс настроек к дефолтам, persist текстов экфрасисов.

## EPIC I — Админка
- [ ] Вкладки по 4 ПК: вкл/выкл, статус, логи каждого.
- [ ] PDF-менеджер: список, превью, привязка к ПК/кругу.
- [ ] MIDI-мониторинг, кэш-менеджер, сброс сценария/настроек.

## EPIC J — Сборка и эксплуатация
- [ ] Python sidecar внутри Tauri v2 (включая нативный python-rtmidi).
- [ ] Прод-сборка frontend в Tauri (frontendDist, один исполняемый файл).
- [ ] Роль ПК из CLI-аргумента или файла рядом с бинарником,
      а не из ?role= в конфиге окна (один бинарник на 4 машины).
- [x] Целевая ОС стенда: Windows (выставка). Разработка на Ubuntu.
      Кросс-платформенность сохраняем: единственная платформенная вставка —
      init_x11_threads под #[cfg(target_os = "linux")].
      На Windows НЕ нужны: XInitThreads, PulseAudio sink-input, module-stream-restore.
- [ ] Прогон под Windows выполнить СРАЗУ после MIDI-переезда, не в конце.
      Причина: WebView2 вместо WebKitGTK — другая автоплей-политика,
      аудио-unlock требует повторной проверки.
- [ ] Python sidecar: python-rtmidi на Windows идёт через WinMM,
      rtpMIDI-порт PC-10 виден как обычный MIDI input по имени.
      Сетевую логику не писать — виртуальный порт создаёт rtpMIDI-демон.

## ✅ DONE (слайсы)
- Slice 1–5: WS-хаб, состояние, клики, порог 17, ядро волн, force_open_all, reset/hard_reset.
- Slice 6: резолв PDF-окна на клиенте (устарел, заменён серверным pdfWindowsByRole).
- Slice 6.5: legacy MIDI compatibility (код), полевая сверка маппинга.
- Slice 7: phase-machine с маятником — ОТМЕНЁН как модель, см. Slice 9.
- Slice 8: аудио (EPIC E).
- Slice 9: реконсиляция backend на единую cycle-машину, подтверждена сквозным прогоном.
- Slice 10: реконсиляция фронта под pdfWindowsByRole.

## 🔜 NEXT
- Slice 14 — доделать MIDI: зачистка мёртвого фронт-кода, проверка через
  /api/midi/simulate, затем железо на PC-10.
- Slice 15 — Windows: сборка, Python sidecar с python-rtmidi,
  проверка аудио-unlock на WebView2, роль из CLI-аргумента.
- Хвосты EPIC C: mtime cache-buster (обязательно — PDF будут переписывать
  вживую), minimize_all, фиксированный zoom.

## 🧊 LATER (после сдачи)
- Разбиение backend/main.py на модули. Новые эпики писать отдельными роутерами.
- EPIC G: HTML-развороты экфрасисов и режим редактирования (E/У) —
  вытеснены PDF-веткой по решению заказчика.
- EPIC I: админка со вкладками по ПК, PDF-менеджер, логи.
