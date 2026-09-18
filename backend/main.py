import asyncio
import json
import time
import socket
import sys
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
import ipaddress

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from midi_router import router as midi_router
from midi_service import midi_service
from pdfs_router import router as pdfs_router

from paths import DATA_DIR, PDFS_DIR, GLOBAL_SETTINGS_FILE

from media_admin import MediaAdmin, create_router, mount_static
# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------
ROLES = ["pc1", "pc2", "pc3", "pc4"]
CLICK_THRESHOLD = 17
def seed_pdfs_if_empty():
    """Первый запуск после установки: data/pdfs пуста — копируем дефолтные
    PDF из ресурсов установщика (лежат рядом с exe в pdfs-default)."""
    if any(PDFS_DIR.glob("*.pdf")):
        return
    if not getattr(sys, "frozen", False):
        return
    seed = Path(sys.executable).parent / "pdfs-default"
    if not seed.is_dir():
        return
    for f in seed.glob("*.pdf"):
        (PDFS_DIR / f.name).write_bytes(f.read_bytes())
        print(f"[seed] {f.name} -> {PDFS_DIR}", flush=True)
PHASE_IDLE = "idle"
PHASE_CYCLE_OPEN = "cycle_open"      # sweep открытия слева-направо
PHASE_CYCLE_HOLD = "cycle_hold"      # держим все открытыми n сек
PHASE_CYCLE_CLOSE = "cycle_close"    # sweep закрытия справа-налево
PHASE_CYCLE_SETTLE = "cycle_settle"  # осела накопительная раскладка с вкладками
PHASE_FINAL_HOLD = "final_hold"
PHASE_FORCE_OPEN_ALL = "force_open_all"
PHASE_MANUAL = "manual_midi"
PHASE_AWAIT_MIDI = "await_midi"

# тайминги (боевые)
DEFAULT_STEP_SECONDS = 2.0     # шаг sweep между ПК
DEFAULT_HOLD_SECONDS = 1.0     # n сек удержания «всё открыто» перед закрытием
DEFAULT_GAP_SECONDS = 120.0    # 2 минуты между кругами

# тайминги (тест-прогон без MIDI)
DEFAULT_TEST_STEP_SECONDS = 2.0
DEFAULT_TEST_HOLD_SECONDS = 1.0
DEFAULT_TEST_GAP_SECONDS = 3.0

SCENARIO_TICK_INTERVAL = 0.5

# живость устройств
DEVICE_STALE_SECONDS = 30.0
DEVICE_SWEEP_INTERVAL = 5.0

DEFAULT_VIBRO_DELAY_SECONDS = 120.0       # пауза после входа в final_hold
DEFAULT_TEST_VIBRO_DELAY_SECONDS = 3.0
# BASE_DIR = Path(__file__).resolve().parent
# GLOBAL_SETTINGS_PATH = BASE_DIR / "global-settings.json"


def now_ts() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Глобальные настройки (persist)
# ---------------------------------------------------------------------------
INSTALLATION_MODES = ("exhibition", "laptop")

def default_global_settings():
    return {
        "stepSeconds": DEFAULT_STEP_SECONDS,
        "holdSeconds": DEFAULT_HOLD_SECONDS,
        "gapSeconds": DEFAULT_GAP_SECONDS,
        "installationMode": "exhibition",
        "pendulumStepMs": 2000,
        "vibroDelaySeconds": DEFAULT_VIBRO_DELAY_SECONDS,
    }

def load_global_settings():
    data = default_global_settings()
    try:
        if GLOBAL_SETTINGS_FILE.exists():
            raw = json.loads(GLOBAL_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k in ("stepSeconds", "holdSeconds", "gapSeconds", "vibroDelaySeconds"):
                    if k in raw:
                        data[k] = float(raw[k])
                if raw.get("installationMode") in INSTALLATION_MODES:
                    data["installationMode"] = raw["installationMode"]
                if "pendulumStepMs" in raw:
                    data["pendulumStepMs"] = max(100, int(raw["pendulumStepMs"]))
    except Exception:
        pass
    return data

def save_global_settings(data: dict):
    payload = {
        "stepSeconds": float(data.get("stepSeconds", DEFAULT_STEP_SECONDS) or 0),
        "holdSeconds": float(data.get("holdSeconds", DEFAULT_HOLD_SECONDS) or 0),
        "gapSeconds": float(data.get("gapSeconds", DEFAULT_GAP_SECONDS) or 0),
        "installationMode": data.get("installationMode", "exhibition"),
        "pendulumStepMs": int(data.get("pendulumStepMs", 2000)),
        "vibroDelaySeconds": float(data.get("vibroDelaySeconds", DEFAULT_VIBRO_DELAY_SECONDS) or 0),
    }
    GLOBAL_SETTINGS_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


GLOBAL_SETTINGS = load_global_settings()


# ---------------------------------------------------------------------------
# Состояние
# ---------------------------------------------------------------------------
def initial_state():
    return {
        "stateVersion": 0,
        "clicksByRole": {r: 0 for r in ROLES},
        "clickScenarioLockedByRole": {r: False for r in ROLES},
        "flippedCardsByRole": {r: {} for r in ROLES},
        "pdfsByRole": {r: f"{r}.pdf" for r in ROLES},
        "connectedDevices": {},
        "scenario": {
            "active": False,
            "trigger": None,
            "phase": PHASE_IDLE,
            "currentRole": None,
            "openRoles": {r: False for r in ROLES},
            "popupEpoch": 0,
            "popupPage": 0,
            "startedAt": None,
            "forceOpenAll": False,
            "restoreAfterForce": None,
            "waveIndex": 0,
            "waveSettled": False,
            "cycleStep": None,        # позиция внутри open/close sweep (0-based)
            "cyclePhaseRoles": [],    # активные роли прогона (канон pc1..pcN)
            "finalHoldRole": "pc4",
            "dwellStartedAt": None,   # момент взвода текущего таймера
            "dwellNextAt": None,      # когда сработает следующий авто-шаг
            "vibroFired": False,  # вибро-дорожка уже запущена в этом final_hold
            "vibroAt": None,
            "waveSoundSeq": 0,  # растёт на каждом старте волны; фронт играет звук по приросту
            "waveSoundWave": 0,  # номер волны, к которой относится последний seq
            "testVibroDelaySeconds": DEFAULT_TEST_VIBRO_DELAY_SECONDS,
            "testMode": False,
            "testRoles": [],
            # тайминги: боевые из GLOBAL_SETTINGS, тестовые — короткие
            "stepSeconds": GLOBAL_SETTINGS["stepSeconds"],
            "holdSeconds": GLOBAL_SETTINGS["holdSeconds"],
            "gapSeconds": GLOBAL_SETTINGS["gapSeconds"],
            "testStepSeconds": DEFAULT_TEST_STEP_SECONDS,
            "testHoldSeconds": DEFAULT_TEST_HOLD_SECONDS,
            "testGapSeconds": DEFAULT_TEST_GAP_SECONDS,
        },
        "pdfWindow": {
            "visible": False,
            "role": None,
            "pdfFile": None,
            "token": None,
        },
        "pdfWindowsByRole": {
            r: {"visible": False, "tabs": [], "activeTab": None, "token": None}
            for r in ROLES
        },
    }


STATE = initial_state()


def bump_version():
    STATE["stateVersion"] += 1


def clone_state():
    st = deepcopy(STATE)
    # Снимок медиа едет в каждом state: клиенты pc2–pc4 узнают о новых звуках
    # без отдельного запроса. media определяется ниже, но вызывается только в рантайме.
    st["media"] = media.snapshot()
    return st


# ---------------------------------------------------------------------------
# Утилиты ролей
# ---------------------------------------------------------------------------
def sanitize_role(role) -> str:
    return role if role in ROLES else "pc1"

def visible_roles(roles_ordered):
    """Фильтр по online: окна открываем только там, где есть живой клиент.
    Если online вообще никого — не фильтруем (dev-режим, одна вкладка)."""
    online = set(get_online_roles())
    if not online:
        return list(roles_ordered)
    return [r for r in roles_ordered if r in online]

def get_online_roles():
    """Online-роли в каноническом порядке pc1..pc4."""
    devices = STATE["connectedDevices"]
    return [r for r in ROLES if devices.get(r, {}).get("online")]


def get_last_open_role():
    opened = [r for r in ROLES if STATE["scenario"]["openRoles"].get(r)]
    return opened[-1] if opened else None


def reset_open_roles():
    STATE["scenario"]["openRoles"] = {r: False for r in ROLES}


def _set_open_flags(open_roles):
    s = STATE["scenario"]
    open_set = set(open_roles)
    s["openRoles"] = {r: (r in open_set) for r in ROLES}
    s["currentRole"] = open_roles[-1] if open_roles else None


def clear_scenario_timers():
    s = STATE["scenario"]
    s["dwellStartedAt"] = None
    s["dwellNextAt"] = None

def midi_driven(s=None) -> bool:
    """Кто продвигает круги. Выставка — ноты Reaper (61–68), таймер молчит.
    Ноутбуки и тест-прогон — таймер: там Reaper нет."""
    s = s or STATE["scenario"]
    return GLOBAL_SETTINGS.get("installationMode") != "laptop" and not s.get("testMode")

# ---------------------------------------------------------------------------
# Тайминги (боевые vs тест)
# ---------------------------------------------------------------------------
def step_seconds(s):
    if s.get("testMode"):
        return float(s["testStepSeconds"])
    if GLOBAL_SETTINGS.get("installationMode") == "laptop":
        return float(GLOBAL_SETTINGS.get("pendulumStepMs", 2000)) / 1000.0
    return float(s.get("stepSeconds") or DEFAULT_STEP_SECONDS)


def hold_seconds(s):
    return float(s["testHoldSeconds"] if s.get("testMode") else s.get("holdSeconds") or DEFAULT_HOLD_SECONDS)


def gap_seconds(s):
    return float(s["testGapSeconds"] if s.get("testMode") else s.get("gapSeconds") or DEFAULT_GAP_SECONDS)


def vibro_delay_seconds(s):
    if s.get("testMode"):
        return float(s["testVibroDelaySeconds"])
    # Читаем из GLOBAL_SETTINGS напрямую, чтобы правка в админке
    # действовала на уже идущий сценарий.
    return float(GLOBAL_SETTINGS.get("vibroDelaySeconds") or DEFAULT_VIBRO_DELAY_SECONDS)


def enter_final_hold():
    """Единая точка входа в final_hold: из SETTLE четвёртого круга и из debug-действия.
    Взводит таймер вибро; что происходит после него — решает ветка FINAL_HOLD в тике."""
    s = STATE["scenario"]
    active = s.get("cyclePhaseRoles") or list(ROLES)
    total = len(active)
    s["phase"] = PHASE_FINAL_HOLD
    s["cycleStep"] = None
    s["popupEpoch"] += 1
    s["vibroFired"] = False
    s["vibroAt"] = None
    set_windows_settled(active[:total], total)
    _set_open_flags(active[:total])
    arm_cycle_timer(vibro_delay_seconds(s))
    recompute_wave_settled()
    sync_pdf_window()

def mark_wave_start(n: int):
    """Единственная точка «волна началась». Счётчик монотонный и переживает
    close_scenario, иначе после сброса фронт не отличит новый старт от старого."""
    s = STATE["scenario"]
    s["waveSoundSeq"] = int(s.get("waveSoundSeq") or 0) + 1
    s["waveSoundWave"] = int(n)

def arm_cycle_timer(delay):
    s = STATE["scenario"]
    now = now_ts()
    s["dwellStartedAt"] = now
    s["dwellNextAt"] = now + max(0.0, float(delay or 0))


# ---------------------------------------------------------------------------
# Раскладка окон
# ---------------------------------------------------------------------------
def pdf_file_for_wave(n: int) -> str:
    return f"pdf{n}.pdf"


def set_windows_sweep(open_roles_ordered, wave_n):
    s = STATE["scenario"]
    pdf = pdf_file_for_wave(wave_n)
    open_set = set(visible_roles(open_roles_ordered))   # <-- фильтр
    wins = {}
    for r in ROLES:
        if r in open_set:
            wins[r] = {
                "visible": True,
                "tabs": [pdf],
                "activeTab": pdf,
                "token": f'{s["popupEpoch"]}:{r}:sweep{wave_n}',
            }
        else:
            wins[r] = {"visible": False, "tabs": [], "activeTab": None, "token": None}
    STATE["pdfWindowsByRole"] = wins


def set_windows_settled(settled_roles_ordered, wave_n):
    s = STATE["scenario"]
    tabs_all = [pdf_file_for_wave(i + 1) for i in range(wave_n)]
    settled_set = set(visible_roles(settled_roles_ordered))   # <-- фильтр
    wins = {}
    for idx, r in enumerate(ROLES):
        if r in settled_set:
            k = idx + 1
            wins[r] = {
                "visible": True,
                "tabs": list(tabs_all),
                "activeTab": pdf_file_for_wave(k),
                "token": f'{s["popupEpoch"]}:{r}:settle{wave_n}',
            }
        else:
            wins[r] = {"visible": False, "tabs": [], "activeTab": None, "token": None}
    STATE["pdfWindowsByRole"] = wins


def clear_windows():
    STATE["pdfWindowsByRole"] = {
        r: {"visible": False, "tabs": [], "activeTab": None, "token": None}
        for r in ROLES
    }


def sync_legacy_pdf_window():
    """Держим старый одиночный pdfWindow согласованным (по currentRole)."""
    s = STATE["scenario"]
    cur = s["currentRole"]
    if s.get("forceOpenAll"):
        STATE["pdfWindow"] = {
            "visible": True, "role": "all", "pdfFile": None,
            "token": f'{s["popupEpoch"]}:all',
        }
        return
    win = STATE["pdfWindowsByRole"].get(cur) if cur in ROLES else None
    if win and win.get("visible"):
        STATE["pdfWindow"] = {
            "visible": True, "role": cur, "pdfFile": win.get("activeTab"),
            "token": win.get("token"),
        }
    else:
        STATE["pdfWindow"] = {"visible": False, "role": None, "pdfFile": None, "token": None}


def sync_pdf_window():
    """Пересобирает legacy-окно; в force_open_all раскрывает всем."""
    if STATE["scenario"].get("forceOpenAll"):
        STATE["pdfWindowsByRole"] = {
            r: {"visible": True, "tabs": [pdf_file_for_wave(1)],
                "activeTab": pdf_file_for_wave(1),
                "token": f'{STATE["scenario"]["popupEpoch"]}:{r}:all'}
            for r in ROLES
        }
    sync_legacy_pdf_window()


def recompute_wave_settled():
    s = STATE["scenario"]
    if not s["active"] or s["forceOpenAll"]:
        s["waveSettled"] = False
        return
    s["waveSettled"] = s.get("phase") in (PHASE_CYCLE_SETTLE, PHASE_FINAL_HOLD)


# ---------------------------------------------------------------------------
# Cycle-машина
# ---------------------------------------------------------------------------
def start_cycles(source=None, *, test=False):
    """Старт сценария. Роли круга — ВСЕГДА pc1..pc4 (свойство сценария).
    Онлайн влияет только на то, где реально откроется окно.
    Выставка: окна откроет Reaper по нотам, мы только встаём в ожидание.
    Ноутбуки/тест: первый шаг сразу, дальше таймер."""
    s = STATE["scenario"]
    active = list(ROLES)

    s["active"] = True
    s["trigger"] = source or {"type": "cycles"}
    s["popupEpoch"] += 1
    s["popupPage"] = 0
    s["startedAt"] = now_ts()
    s["forceOpenAll"] = False
    s["restoreAfterForce"] = None
    s["testMode"] = bool(test)
    s["testRoles"] = get_online_roles()      # ИНФО: где видно
    s["cyclePhaseRoles"] = active
    s["finalHoldRole"] = active[-1]          # pc4
    clear_scenario_timers()

    if midi_driven(s):
        s["waveIndex"] = 0
        s["phase"] = PHASE_AWAIT_MIDI
        s["cycleStep"] = None
        clear_windows()
        _set_open_flags([])
        recompute_wave_settled()
        sync_pdf_window()
        print("[cycles] exhibition: awaiting Reaper (note 61)", flush=True)
        return True

    s["waveIndex"] = 1
    s["phase"] = PHASE_CYCLE_OPEN
    s["cycleStep"] = 0
    mark_wave_start(1)
    opened = active[:1]
    set_windows_sweep(opened, 1)
    _set_open_flags(opened)
    arm_cycle_timer(step_seconds(s))
    recompute_wave_settled()
    sync_pdf_window()
    return True


def start_test_run(source: dict | None = None):
    return start_cycles(source or {"type": "test_run"}, test=True)


def start_scenario(trigger: dict, role: str = "pc1"):
    if trigger.get("type") == "click_threshold" and trigger.get("role"):
        STATE["clickScenarioLockedByRole"][sanitize_role(trigger["role"])] = True
    start_cycles(trigger, test=False)


def cycle_tick_advance():
    """Один авто-шаг фазовой машины круга. True если что-то изменилось."""
    s = STATE["scenario"]
    if not s["active"] or s["forceOpenAll"]:
        return False

    phase = s.get("phase")
    active = s.get("cyclePhaseRoles") or []
    total = len(active)
    n = int(s.get("waveIndex") or 1)

    if total == 0:
        return False

    # -------- OPEN sweep --------
    if phase == PHASE_CYCLE_OPEN:
        step = int(s.get("cycleStep") or 0)
        if step < total - 1:
            step += 1
            s["cycleStep"] = step
            s["popupEpoch"] += 1
            opened = active[:step + 1]
            set_windows_sweep(opened, n)
            _set_open_flags(opened)
            arm_cycle_timer(step_seconds(s))
        else:
            s["phase"] = PHASE_CYCLE_HOLD
            arm_cycle_timer(hold_seconds(s))
        recompute_wave_settled()
        sync_pdf_window()
        return True

    # -------- HOLD -> CLOSE --------
    if phase == PHASE_CYCLE_HOLD:
        s["phase"] = PHASE_CYCLE_CLOSE
        s["cycleStep"] = total - 1
        s["popupEpoch"] += 1
        set_windows_sweep(active[:total], n)
        _set_open_flags(active[:total])
        arm_cycle_timer(step_seconds(s))
        recompute_wave_settled()
        sync_pdf_window()
        return True

    # -------- CLOSE sweep --------
    if phase == PHASE_CYCLE_CLOSE:
        step = int(s.get("cycleStep") if s.get("cycleStep") is not None else total - 1)
        if step > 0:
            step -= 1
            s["cycleStep"] = step
            s["popupEpoch"] += 1
            opened = active[:step + 1]
            set_windows_sweep(opened, n)
            _set_open_flags(opened)
            arm_cycle_timer(step_seconds(s))
        else:
            s["phase"] = PHASE_CYCLE_SETTLE
            s["cycleStep"] = None
            s["popupEpoch"] += 1
            settled = active[:n]
            set_windows_settled(settled, n)
            _set_open_flags(settled)
            arm_cycle_timer(gap_seconds(s))
        recompute_wave_settled()
        sync_pdf_window()
        return True

    # -------- SETTLE -> следующий круг или final_hold --------
    if phase == PHASE_CYCLE_SETTLE:
        if n >= total:
            enter_final_hold()
            return True
        s["waveIndex"] = n + 1
        s["phase"] = PHASE_CYCLE_OPEN
        s["cycleStep"] = 0
        mark_wave_start(n + 1)
        s["popupEpoch"] += 1
        opened = active[:1]
        set_windows_sweep(opened, n + 1)
        _set_open_flags(opened)
        arm_cycle_timer(step_seconds(s))
        recompute_wave_settled()
        sync_pdf_window()
        return True

        # -------- FINAL_HOLD --------
    if phase == PHASE_FINAL_HOLD:
        if not s.get("vibroFired"):
            s["vibroFired"] = True
            s["vibroAt"] = now_ts()
            print("[vibro] fire", flush=True)
            laptop = GLOBAL_SETTINGS.get("installationMode") == "laptop"
            if s.get("testMode") or laptop:
                # Ни тест, ни ноутбуки не получат MIDI-ноту — закрываемся сами.
                arm_cycle_timer(gap_seconds(s))
            else:
                clear_scenario_timers()  # бой ждёт ноту с finalHoldRole
            return True
        if s.get("testMode") or GLOBAL_SETTINGS.get("installationMode") == "laptop":
            close_scenario({"type": "final_hold_auto_close"})
            return True
        return False


# def start_test_run(source: dict | None = None):
#     active = get_online_roles()
#     if not active:
#         return False
#     return start_cycles(active, source or {"type": "test_run"}, test=True)


# ---------------------------------------------------------------------------
# Боевой старт / launch / ручной override
# ---------------------------------------------------------------------------
# def start_scenario(trigger: dict, role: str = "pc1"):
#     if trigger.get("type") == "click_threshold" and trigger.get("role"):
#         STATE["clickScenarioLockedByRole"][sanitize_role(trigger["role"])] = True
#     active = get_online_roles() or list(ROLES)
#     start_cycles(active, trigger, test=False)

def midi_window_step(role: str, opening: bool) -> bool:
    """Шаг круга по ноте Reaper (выставка). True — нота обработана внутри сценария.
    False — сценарий не ведётся по MIDI; вызывающий откатится к ручному
    open_role/close_role (legacy-поведение нот вне сценария).

    Семантика как в старом server.js: open_pcX показывает окно X с PDF текущего
    круга, close_pcX убирает. Границы кругов выводятся из набора открытых окон:
    пустой набор после закрытия = круг осел (накопительная раскладка), первая
    нота открытия после этого = следующий круг. После четвёртого — final_hold.
    """
    s = STATE["scenario"]
    if not midi_driven(s) or not s["active"] or s["forceOpenAll"]:
        return False
    phase = s.get("phase")
    if phase in (PHASE_MANUAL, PHASE_FINAL_HOLD, PHASE_FORCE_OPEN_ALL):
        return False

    target = sanitize_role(role)
    total = len(ROLES)
    n = int(s.get("waveIndex") or 0)

    if phase in (PHASE_AWAIT_MIDI, PHASE_CYCLE_SETTLE):
        # Между кругами открытых окон нет — закрывать нечего.
        if not opening:
            print(f"[midi-step] close_{target} in {phase}: nothing open, ignored", flush=True)
            return True
        n += 1
        s["waveIndex"] = n
        mark_wave_start(n)
        opened = [target]
    else:
        opened = [r for r in ROLES if s["openRoles"].get(r)]
        if opening:
            if target not in opened:
                opened = [r for r in ROLES if r in opened or r == target]
        else:
            opened = [r for r in opened if r != target]

    s["popupEpoch"] += 1
    s["cycleStep"] = None
    clear_scenario_timers()   # выставка: таймер во время кругов молчит

    if opened:
        s["phase"] = PHASE_CYCLE_OPEN if opening else PHASE_CYCLE_CLOSE
        set_windows_sweep(opened, n)
        _set_open_flags(opened)
    elif n >= total:
        # Четвёртый круг закрыт целиком. enter_final_hold сам выложит накопительную
        # раскладку и взведёт вибро; дальше ждём ноту 60.
        enter_final_hold()
        print(f"[midi-step] wave {n} closed -> final_hold", flush=True)
        return True
    else:
        s["phase"] = PHASE_CYCLE_SETTLE
        settled = ROLES[:n]
        set_windows_settled(settled, n)
        _set_open_flags(settled)

    recompute_wave_settled()
    sync_pdf_window()
    print(f"[midi-step] {'open' if opening else 'close'}_{target} wave={n}/{total} "
          f"open={opened} phase={s['phase']}", flush=True)
    return True

def advance_wave(source: dict | None = None):
    """launch: смысл только в final_hold.
    Боевой путь — нота от finalHoldRole. Админский — payload.force."""
    s = STATE["scenario"]
    source = source or {}
    if not s["active"] or s["forceOpenAll"]:
        return
    if s.get("phase") != PHASE_FINAL_HOLD:
        return
    if source.get("force"):
        close_scenario({**source, "type": "launch_close_final_hold_forced"})
        return
    source_role = sanitize_role(source.get("role", "pc1"))
    final_role = sanitize_role(s.get("finalHoldRole") or "pc4")
    if source_role == final_role:
        close_scenario({**source, "type": "launch_close_final_hold"})


def open_role(role: str, source: dict | None = None):
    """Ручной override (админка). Ломает cycle-автоматику, переводит в manual."""
    target = sanitize_role(role)
    s = STATE["scenario"]
    source = source or {}

    if not s["active"]:
        s["active"] = True
        s["trigger"] = {"type": "open", "role": target, "source": source}
        s["phase"] = PHASE_MANUAL
        s["popupEpoch"] += 1
        s["popupPage"] = 0
        s["startedAt"] = now_ts()
        s["forceOpenAll"] = False
        s["restoreAfterForce"] = None
        s["waveIndex"] = max(1, int(s.get("waveIndex") or 1))
        clear_scenario_timers()
        reset_open_roles()
        s["openRoles"][target] = True
        s["currentRole"] = target
        set_windows_sweep([target], s["waveIndex"])
        recompute_wave_settled()
        sync_pdf_window()
        return

    if not s["forceOpenAll"] and s["currentRole"] == target and s["openRoles"].get(target):
        return

    if s["forceOpenAll"]:
        s["forceOpenAll"] = False
        s["restoreAfterForce"] = None

    s["active"] = True
    s["phase"] = PHASE_MANUAL
    clear_scenario_timers()
    s["openRoles"][target] = True
    s["currentRole"] = target
    opened = [r for r in ROLES if s["openRoles"].get(r)]
    set_windows_sweep(opened, s.get("waveIndex") or 1)
    recompute_wave_settled()
    sync_pdf_window()


def close_role(role: str, source: dict | None = None):
    target = sanitize_role(role)
    s = STATE["scenario"]
    if not s["active"]:
        return
    if s["forceOpenAll"]:
        s["forceOpenAll"] = False
        s["restoreAfterForce"] = None
    if s["openRoles"].get(target):
        s["openRoles"][target] = False
        if s["currentRole"] == target:
            s["currentRole"] = get_last_open_role()
        s["phase"] = PHASE_MANUAL
        clear_scenario_timers()
        opened = [r for r in ROLES if s["openRoles"].get(r)]
        set_windows_sweep(opened, s.get("waveIndex") or 1)
        recompute_wave_settled()
        sync_pdf_window()


def toggle_force_open_all(source: dict | None = None):
    s = STATE["scenario"]
    source = source or {}
    if not s["forceOpenAll"]:
        s["restoreAfterForce"] = {
            "active": s["active"],
            "currentRole": s["currentRole"],
            "openRoles": dict(s["openRoles"]),
            "phase": s["phase"],
            "trigger": s["trigger"],
            "waveIndex": s["waveIndex"],
            "cycleStep": s.get("cycleStep"),
            "cyclePhaseRoles": list(s.get("cyclePhaseRoles") or []),
            "dwellStartedAt": s.get("dwellStartedAt"),
            "dwellNextAt": s.get("dwellNextAt"),
        }
        s["forceOpenAll"] = True
        s["active"] = True
        s["phase"] = PHASE_FORCE_OPEN_ALL
        s["currentRole"] = "all"
        s["openRoles"] = {r: True for r in ROLES}
        s["popupEpoch"] += 1
        recompute_wave_settled()
        sync_pdf_window()
        return

    restore = s["restoreAfterForce"]
    s["forceOpenAll"] = False
    s["restoreAfterForce"] = None
    if restore and restore.get("active"):
        s["active"] = True
        s["currentRole"] = restore["currentRole"]
        s["cycleStep"] = restore.get("cycleStep")
        s["cyclePhaseRoles"] = restore.get("cyclePhaseRoles") or []
        s["dwellStartedAt"] = restore.get("dwellStartedAt")
        s["dwellNextAt"] = restore.get("dwellNextAt")
        s["openRoles"] = restore.get("openRoles") or {r: False for r in ROLES}
        s["phase"] = restore.get("phase") or PHASE_MANUAL
        s["trigger"] = restore.get("trigger")
        s["waveIndex"] = restore.get("waveIndex") or 0
        recompute_wave_settled()
        sync_pdf_window()
        return
    close_scenario({**source, "reason": "force_open_all_disabled_without_restore"})


def close_scenario(source: dict | None = None, *, preserve_clicks=True,
                   preserve_click_locks=True, preserve_flips=True):
    source = source or {}
    pdfs = dict(STATE["pdfsByRole"])
    devices = deepcopy(STATE["connectedDevices"])
    version = STATE["stateVersion"]
    clicks = dict(STATE["clicksByRole"]) if preserve_clicks else None
    locks = dict(STATE["clickScenarioLockedByRole"]) if preserve_click_locks else None
    flips = deepcopy(STATE["flippedCardsByRole"]) if preserve_flips else None
    popup_epoch = STATE["scenario"]["popupEpoch"] + 1
    wave_seq = STATE["scenario"].get("waveSoundSeq") or 0

    fresh = initial_state()
    STATE.clear()
    STATE.update(fresh)
    STATE["pdfsByRole"] = pdfs
    STATE["connectedDevices"] = devices
    STATE["stateVersion"] = version
    if clicks is not None:
        STATE["clicksByRole"] = clicks
    if locks is not None:
        STATE["clickScenarioLockedByRole"] = locks
    if flips is not None:
        STATE["flippedCardsByRole"] = flips
    STATE["scenario"]["popupEpoch"] = popup_epoch
    STATE["scenario"]["waveSoundSeq"] = wave_seq
    recompute_wave_settled()
    sync_pdf_window()


def hard_reset(source: dict | None = None):
    close_scenario(
        {**(source or {}), "type": "hard_reset"},
        preserve_clicks=False,
        preserve_click_locks=False,
        preserve_flips=False,
    )


# ---------------------------------------------------------------------------
# WS hub
# ---------------------------------------------------------------------------
class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast(self, reason: str = "state"):
        msg = json.dumps({"type": "state", "payload": clone_state(), "reason": reason})
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = Hub()


# ---------------------------------------------------------------------------
# Реестр устройств
# ---------------------------------------------------------------------------
def touch_device(role: str, host_name: str | None = None):
    dev = STATE["connectedDevices"].get(role) or {"role": role, "hostName": ""}
    dev["role"] = role
    if host_name is not None:
        dev["hostName"] = host_name
    dev["online"] = True
    dev["lastSeenAt"] = now_ts()
    STATE["connectedDevices"][role] = dev


def mark_device_offline(role: str):
    dev = STATE["connectedDevices"].get(role)
    if dev:
        dev["online"] = False


async def device_sweeper():
    try:
        while True:
            await asyncio.sleep(DEVICE_SWEEP_INTERVAL)
            changed = False
            t = now_ts()
            for role, dev in STATE["connectedDevices"].items():
                if not dev.get("online"):
                    continue
                last = dev.get("lastSeenAt") or 0
                if t - last > DEVICE_STALE_SECONDS:
                    dev["online"] = False
                    changed = True
            if changed:
                await hub.broadcast("device_stale_sweep")
    except asyncio.CancelledError:
        pass


async def scenario_timer_loop():
    try:
        while True:
            await asyncio.sleep(SCENARIO_TICK_INTERVAL)
            s = STATE["scenario"]
            if not s["active"] or s["forceOpenAll"]:
                continue
            now = now_ts()
            due_at = s.get("dwellNextAt")
            if due_at is None or now < due_at:
                continue
            changed = cycle_tick_advance()
            if changed:
                s2 = STATE["scenario"]
                print(
                    f"[tick] phase={s2.get('phase')} wave={s2.get('waveIndex')}"
                    f"/{len(s2.get('cyclePhaseRoles') or [])} step={s2.get('cycleStep')}"
                    f" open={[r for r in ROLES if s2['openRoles'].get(r)]}",
                    flush=True,
                )
                bump_version()
                await hub.broadcast("cycle_tick")
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_pdfs_if_empty()
    device_task = asyncio.create_task(device_sweeper())
    scenario_task = asyncio.create_task(scenario_timer_loop())
    try:
        midi_service.final_hold_role = lambda: STATE["scenario"].get("finalHoldRole")
        midi_service.in_final_hold = lambda: STATE["scenario"].get("phase") == PHASE_FINAL_HOLD
        midi_service.midi_allowed = lambda: GLOBAL_SETTINGS.get("installationMode") != "laptop"
        midi_service.scenario_brief = lambda: (
            f"phase={STATE['scenario'].get('phase')} wave={STATE['scenario'].get('waveIndex')}"
        )
        await midi_service.start(apply_action, hub.broadcast)
        yield
    finally:
        await midi_service.stop()
        for task in (device_task, scenario_task):
            task.cancel()
        for task in (device_task, scenario_task):
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(midi_router)
app.include_router(pdfs_router)
# PDF_DIR = BASE_DIR / "pdfs"
# PDF_DIR.mkdir(exist_ok=True)
app.mount("/pdfs", StaticFiles(directory=str(PDFS_DIR)), name="pdfs")

# ---------------------------------------------------------------------------
# Медиа из служебного меню: тексты (PDF) и настраиваемые звуки
# ---------------------------------------------------------------------------
async def _media_changed():
    """После подмены файла — рассылаем state, чтобы все клиенты узнали новые mtime."""
    bump_version()
    await hub.broadcast("media_changed")


media = MediaAdmin(DATA_DIR, pdf_dir=PDFS_DIR, on_change=_media_changed)
app.include_router(create_router(media))   # /api/media, /api/media/import, ...
mount_static(app, media)                    # /audio/* — настраиваемые звуки

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _addr_kind(ip: str) -> str:
    a = ipaddress.ip_address(ip)
    if a in ipaddress.ip_network("100.64.0.0/10"):
        return "vpn"        # Tailscale / CGNAT — точно не стенд
    if a in ipaddress.ip_network("192.168.0.0/16") or a in ipaddress.ip_network("172.16.0.0/12"):
        return "lan"
    if a in ipaddress.ip_network("10.0.0.0/8"):
        return "lan10"      # и офисные сети, и OpenVPN (10.8.x.x) — ниже приоритетом
    return "other"


_KIND_RANK = {"lan": 0, "lan10": 1, "other": 2, "vpn": 3}
_KIND_LABEL = {
    "lan": "локальная сеть",
    "lan10": "сеть 10.x — может быть VPN",
    "vpn": "VPN / Tailscale",
    "other": "прочее",
}


def _iface_toward(peer_ip: str):
    """Каким своим адресом ОС дойдёт до peer_ip. UDP-connect пакетов не шлёт."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((peer_ip, 1))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None


def _all_ipv4():
    addrs = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith(("127.", "169.254.")) and ip not in addrs:
                addrs.append(ip)
    except OSError:
        pass
    return addrs


def _connected_peer_ips():
    """IP машин, висящих на WS. Структура hub у нас своя — перебираем возможные имена коллекции."""
    ips = []
    for attr in ("clients", "connections", "sockets", "active"):
        coll = getattr(hub, attr, None)
        if coll is None:
            continue
        items = coll.values() if isinstance(coll, dict) else coll
        for ws in list(items):
            host = getattr(getattr(ws, "client", None), "host", None)
            if host and not host.startswith("127.") and host not in ips:
                ips.append(host)
    return ips


@app.get("/api/net/info")
def net_info(request: Request):
    addrs = _all_ipv4()
    primary, reason = None, ""

    # 1. Лучший признак — интерфейс, через который видны реальные клиенты.
    peers = _connected_peer_ips()
    req_host = getattr(request.client, "host", None)
    if req_host and not req_host.startswith("127."):
        peers.append(req_host)
    for peer in peers:
        ip = _iface_toward(peer)
        if ip and not ip.startswith("127."):
            primary, reason = ip, f"через этот адрес виден клиент {peer}"
            if ip not in addrs:
                addrs.insert(0, ip)
            break

    # 2. Клиентов нет — ранжируем по типу сети.
    if not primary and addrs:
        addrs.sort(key=lambda ip: (_KIND_RANK[_addr_kind(ip)], ip))
        primary, reason = addrs[0], "по типу сети (клиенты пока не подключены)"

    return {
        "hostname": socket.gethostname(),
        "primary": primary,
        "primaryReason": reason,
        "port": request.url.port or 8787,
        "addresses": [
            {"ip": ip, "kind": _addr_kind(ip), "label": _KIND_LABEL[_addr_kind(ip)]}
            for ip in addrs
        ],
    }

@app.get("/api/state")
def get_state():
    return clone_state()


async def apply_action(t: str, p: dict):
    print(f"[action] {t} payload={p} phase={STATE['scenario'].get('phase')}", flush=True)
    role = sanitize_role(p.get("role", "pc1"))

    if t == "click_card":
        card_idx = str(int(p.get("cardIndex", 0)))
        cur = STATE["flippedCardsByRole"][role].get(card_idx, False)
        STATE["flippedCardsByRole"][role][card_idx] = not cur
        STATE["clicksByRole"][role] += 1

        s = STATE["scenario"]
        busy = s["active"] and s.get("phase") != PHASE_MANUAL
        if (
                not busy
                and not STATE["clickScenarioLockedByRole"][role]
                and STATE["clicksByRole"][role] >= CLICK_THRESHOLD
        ):
            start_scenario(
                {"type": "click_threshold", "role": role,
                 "clicks": STATE["clicksByRole"][role]},
                "pc1",
            )
            asyncio.create_task(midi_service.send_scenario_started())
        bump_version()
        await hub.broadcast("click_card")
        return {"ok": True}

    if t == "open_role_popup":
        if not (p.get("via") == "midi" and midi_window_step(role, True)):
            open_role(role, {"type": "manual_open", "role": role})
        bump_version()
        await hub.broadcast("open_role_popup")
        return {"ok": True}

    if t == "close_role_popup":
        if not (p.get("via") == "midi" and midi_window_step(role, False)):
            close_role(role, {"type": "manual_close", "role": role})
        bump_version()
        await hub.broadcast("close_role_popup")
        return {"ok": True}

    if t == "launch":
        advance_wave({"type": "manual_launch", "role": role, "force": bool(p.get("force"))})
        bump_version()
        await hub.broadcast("launch")
        return {"ok": True}

    if t == "toggle_force_open_all":
        toggle_force_open_all({"type": "manual_force_open_all", "role": role})
        bump_version()
        await hub.broadcast("toggle_force_open_all")
        return {"ok": True}

    if t == "reset_scenario":
        close_scenario({"type": "manual_reset", "role": role})
        bump_version()
        await hub.broadcast("reset_scenario")
        return {"ok": True}

    if t == "hard_reset":
        hard_reset({"type": "manual_hard_reset", "role": role})
        bump_version()
        await hub.broadcast("hard_reset")
        return {"ok": True}

    if t == "minimize_all_windows":
        bump_version()
        await hub.broadcast("minimize_all_windows")
        return {"ok": True, "noop": True}

    if t == "start_test_run":
        ok = start_test_run({"type": "manual_test_run", "role": role})
        bump_version()
        await hub.broadcast("start_test_run")
        return {"ok": ok, "error": None if ok else "no online devices"}

    if t == "stop_test_run":
        close_scenario({"type": "manual_test_stop", "role": role})
        bump_version()
        await hub.broadcast("stop_test_run")
        return {"ok": True}

    if t == "debug_final_hold":
        active = list(ROLES)
        s = STATE["scenario"]
        s["active"] = True
        s["forceOpenAll"] = False
        s["testMode"] = False
        s["cyclePhaseRoles"] = active
        s["waveIndex"] = len(active)
        s["finalHoldRole"] = active[-1]
        enter_final_hold()
        bump_version()
        await hub.broadcast("debug_final_hold")
        return {"ok": True}

    return {"ok": False, "error": f"Unknown action: {t}"}


class ActionBody(BaseModel):
    type: str
    payload: dict = {}


class GlobalSettingsBody(BaseModel):
    stepSeconds: float
    holdSeconds: float
    gapSeconds: float
    installationMode: str | None = None
    pendulumStepMs: int | None = None
    vibroDelaySeconds: float | None = None


@app.post("/api/action")
async def action(body: ActionBody):
    return await apply_action(body.type, body.payload or {})


@app.get("/api/settings/global")
def get_global_settings():
    return dict(GLOBAL_SETTINGS)


@app.post("/api/settings/global")
async def set_global_settings(body: GlobalSettingsBody):
    GLOBAL_SETTINGS["stepSeconds"] = float(body.stepSeconds)
    GLOBAL_SETTINGS["holdSeconds"] = float(body.holdSeconds)
    GLOBAL_SETTINGS["gapSeconds"] = float(body.gapSeconds)
    if body.installationMode in INSTALLATION_MODES:
        GLOBAL_SETTINGS["installationMode"] = body.installationMode
    if body.pendulumStepMs is not None:
        GLOBAL_SETTINGS["pendulumStepMs"] = max(100, int(body.pendulumStepMs))
    if body.vibroDelaySeconds is not None:
        GLOBAL_SETTINGS["vibroDelaySeconds"] = max(0.0, float(body.vibroDelaySeconds))
    save_global_settings(GLOBAL_SETTINGS)
    # Смена режима действует сразу: laptop глушит MIDI-вход, exhibition поднимает.
    if GLOBAL_SETTINGS["installationMode"] == "laptop":
        midi_service.close_input()
    else:
        midi_service.open_input()
    STATE["scenario"]["stepSeconds"] = GLOBAL_SETTINGS["stepSeconds"]
    STATE["scenario"]["holdSeconds"] = GLOBAL_SETTINGS["holdSeconds"]
    STATE["scenario"]["gapSeconds"] = GLOBAL_SETTINGS["gapSeconds"]

    bump_version()
    await hub.broadcast("global_settings_updated")
    return {"ok": True, "settings": dict(GLOBAL_SETTINGS)}

TIMING_KEYS = ("stepSeconds", "holdSeconds", "gapSeconds", "pendulumStepMs", "vibroDelaySeconds")


@app.get("/api/settings/global/defaults")
def get_global_defaults():
    return default_global_settings()


@app.post("/api/settings/global/reset-timings")
async def reset_global_timings():
    """Кнопка «Стандартный тайминг»: боевые значения из констант. Режим не трогаем."""
    d = default_global_settings()
    for k in TIMING_KEYS:
        if k in d:
            GLOBAL_SETTINGS[k] = d[k]
    save_global_settings(GLOBAL_SETTINGS)
    STATE["scenario"]["stepSeconds"] = GLOBAL_SETTINGS["stepSeconds"]
    STATE["scenario"]["holdSeconds"] = GLOBAL_SETTINGS["holdSeconds"]
    STATE["scenario"]["gapSeconds"] = GLOBAL_SETTINGS["gapSeconds"]
    print("[settings] timings reset to defaults", flush=True)
    bump_version()
    await hub.broadcast("global_settings_updated")
    return {"ok": True, "settings": dict(GLOBAL_SETTINGS)}

# ---------------------------------------------------------------------------
# WS endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    bound_role = None
    try:
        await ws.send_text(json.dumps(
            {"type": "state", "payload": clone_state(), "reason": "initial"}
        ))
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            payload = msg.get("payload") or {}

            if mtype == "ping":
                if bound_role:
                    touch_device(bound_role)
                continue

            if mtype == "identify":
                bound_role = sanitize_role(payload.get("role", "pc1"))
                touch_device(bound_role, payload.get("hostName", ""))
                await hub.broadcast("identify")
                continue

            if mtype == "action":
                await apply_action(payload.get("type"), payload.get("payload") or {})
                continue
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(ws)
        if bound_role:
            mark_device_offline(bound_role)
        await hub.broadcast("disconnect")