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
- [~] Порог кликов (17) → старт сценария + lock роли. Есть, старт всегда с pc1.
      Не проверен вживую с реальными 17 кликами при полном прогоне.
- [ ] Боевой финал: launch в FINAL_HOLD от finalHoldRole (pc4) → close_scenario.
      Код есть, логом не подтверждён (тест закрывается сам по gap, минуя эту ветку).

## EPIC C — Управление окнами (Tauri v1, нативно)
- [ ] PDF-окно как нативное WebviewWindow: 1968×1392, без декораций, по центру.
- [ ] Открыть/скрыть/сфокусировать/переместить PDF-окно из состояния.
- [ ] Перезагрузка PDF по mtime файла (cache-buster ?v={mtime}).
- [ ] «Свернуть все окна Windows» нативно (вместо Shell.Application MinimizeAll).
- [ ] Управление кэшем профиля просмотрщика (размер + очистка).
- [ ] Антивандал добить нативно: Ctrl+колесо, pinch, auxclick.

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

## EPIC F — MIDI (последним этапом)
Код панели написан и не проверен на текущей сборке. Ноды переносим из legacy-версии.
- [~] Выбор конкретного MIDI input/output в UI, дефолт `PC-10`.
- [~] Слушать только выбранный input; фильтр по каналу (legacy channel = 2).
- [~] Предзаполненный legacy-маппинг: launch=60 · open pc1..pc4=61,63,65,67 ·
      close pc1..pc4=62,64,66,68 · minimizeAll=69 · output=72 · velocity=100 · duration=180.
- [~] Дедупликация входящих noteOn (окно 180ms) — по полевому логу дубли мелькали.
- [~] Привязка note -> sendAction; тест-кнопка MIDI output.
- [ ] Свести панель с cycle-машиной: launch осмыслен только в FINAL_HOLD;
      боевой старт — порог кликов, а не нота.
- [ ] Полевая проверка на `PC-10`.

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
- [ ] Python sidecar внутри Tauri v1 (упаковка backend).
- [ ] Прод-сборка frontend в Tauri.
- [ ] Кросс-платформенная проверка (Windows основная).

## ✅ DONE (слайсы)
- Slice 1–5: WS-хаб, состояние, клики, порог 17, ядро волн, force_open_all, reset/hard_reset.
- Slice 6: резолв PDF-окна на клиенте (устарел, заменён серверным pdfWindowsByRole).
- Slice 6.5: legacy MIDI compatibility (код), полевая сверка маппинга.
- Slice 7: phase-machine с маятником — ОТМЕНЁН как модель, см. Slice 9.
- Slice 8: аудио (EPIC E).
- Slice 9: реконсиляция backend на единую cycle-машину, подтверждена сквозным прогоном.
- Slice 10: реконсиляция фронта под pdfWindowsByRole.

## 🔜 NEXT
- Slice 11 — разбиение backend/main.py на модули
  (state / settings / devices / scenario / hub / api).
- Slice 12 — EPIC G + I в приближённом варианте (вау-слой для сдачи).
- Slice 13 — Tauri v1 (EPIC C + J).
- Slice 14 — MIDI (EPIC F) последним.
