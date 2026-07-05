import asyncio
import json
import time
from contextlib import asynccontextmanager
from copy import deepcopy
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path

ROLES = ["pc1", "pc2", "pc3", "pc4"]
CLICK_THRESHOLD = 17

PHASE_IDLE = "idle"
PHASE_CYCLE_OPEN = "cycle_open"      # sweep открытия слева-направо
PHASE_CYCLE_HOLD = "cycle_hold"      # держим все открытыми n сек
PHASE_CYCLE_CLOSE = "cycle_close"    # sweep закрытия справа-налево
PHASE_CYCLE_SETTLE = "cycle_settle"  # осела накопительная раскладка с вкладками
PHASE_FINAL_HOLD = "final_hold"
PHASE_FORCE_OPEN_ALL = "force_open_all"

# n секунд hold перед закрытием на каждой волне
DEFAULT_HOLD_SECONDS = 1.0
# 2 минуты между волнами (в тесте переопределяется коротким)
DEFAULT_GAP_SECONDS = 120.0

DEFAULT_DWELL_SECONDS = 5.0
DEFAULT_RETURN_DELAY_SECONDS = 1.0
SCENARIO_TICK_INTERVAL = 0.5

# --- EPIC A2: пороги живости устройств ---
DEVICE_STALE_SECONDS = 30.0      # не видели дольше -> online:false
DEVICE_SWEEP_INTERVAL = 5.0      # как часто фоновая задача проверяет

BASE_DIR = Path(__file__).resolve().parent
GLOBAL_SETTINGS_PATH = BASE_DIR / "global-settings.json"

DEFAULT_TEST_STEP_SECONDS = 2.0
DEFAULT_TEST_DWELL_SECONDS = 3.0

def now_ts() -> float:
    return time.time()

def default_global_settings():
    return {
        "returnDelaySeconds": DEFAULT_RETURN_DELAY_SECONDS,
        "dwellSeconds": DEFAULT_DWELL_SECONDS,
    }


def load_global_settings():
    data = default_global_settings()
    try:
        if GLOBAL_SETTINGS_PATH.exists():
            raw = json.loads(GLOBAL_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                if "returnDelaySeconds" in raw:
                    data["returnDelaySeconds"] = float(raw["returnDelaySeconds"])
                if "dwellSeconds" in raw:
                    data["dwellSeconds"] = float(raw["dwellSeconds"])
    except Exception:
        pass
    return data


def save_global_settings(data: dict):
    payload = {
        "returnDelaySeconds": float(data.get("returnDelaySeconds", DEFAULT_RETURN_DELAY_SECONDS) or 0),
        "dwellSeconds": float(data.get("dwellSeconds", DEFAULT_DWELL_SECONDS) or 0),
    }
    GLOBAL_SETTINGS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


GLOBAL_SETTINGS = load_global_settings()

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
            "phase": "idle",
            "currentRole": None,
            "openRoles": {r: False for r in ROLES},
            "popupEpoch": 0,
            "popupPage": 0,
            "startedAt": None,
            "forceOpenAll": False,
            "restoreAfterForce": None,
            "waveIndex": 0,
            "waveSettled": False,
            "cycleStep": None,       # позиция внутри open/close sweep (0-based)
            "cyclePhaseRoles": [],   # активные роли этого прогона (pc1..pcN канон)
            "dwellStartedAt": None,
            "dwellNextAt": None,
            "finalHoldRole": "pc4",
            "returnDelaySeconds": DEFAULT_RETURN_DELAY_SECONDS,  # = n (hold)
            "dwellSeconds": DEFAULT_DWELL_SECONDS,               # legacy
            "gapSeconds": DEFAULT_GAP_SECONDS,                   # 2 минуты
            "testMode": False,
            "testRoles": [],
            "testStepSeconds": DEFAULT_TEST_STEP_SECONDS,   # шаг sweep
            "testHoldSeconds": DEFAULT_HOLD_SECONDS,        # n в тесте
            "testGapSeconds": DEFAULT_TEST_DWELL_SECONDS,   # «2 минуты» в тесте

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
    return deepcopy(STATE)

# ---------------------------------------------------------------------------
# Тест полного сценария (без миди)
# ---------------------------------------------------------------------------

def get_online_roles():
    """Online-роли в каноническом порядке pc1..pc4."""
    devices = STATE["connectedDevices"]
    online = [r for r in ROLES if devices.get(r, {}).get("online")]
    return online


def build_pendulum_route(active_roles):
    """[pc1,pc2] -> [pc1,pc2,pc1]; [pc1] -> [pc1]; [] -> []."""
    if not active_roles:
        return []
    if len(active_roles) == 1:
        return list(active_roles)
    return list(active_roles) + list(reversed(active_roles[:-1]))

def cycle_route(active_roles):
    """Канонический порядок активных ролей для sweep: pc1..pcN online."""
    return list(active_roles)


def start_cycles(active_roles, source=None, *, test=False):
    """Старт первого круга: фаза open, шаг 0 -> открыт первый ПК."""
    s = STATE["scenario"]
    s["active"] = True
    s["trigger"] = source or {"type": "cycles"}
    s["popupEpoch"] += 1
    s["popupPage"] = 0
    s["startedAt"] = now_ts()
    s["forceOpenAll"] = False
    s["restoreAfterForce"] = None
    s["testMode"] = bool(test)
    s["testRoles"] = list(active_roles)
    s["cyclePhaseRoles"] = list(active_roles)
    s["finalHoldRole"] = active_roles[-1] if active_roles else "pc4"

    s["waveIndex"] = 1
    s["phase"] = PHASE_CYCLE_OPEN
    s["cycleStep"] = 0
    clear_scenario_timers()

    opened = active_roles[:1]
    set_windows_sweep(opened, 1)
    _set_open_flags(opened)
    arm_cycle_timer(step_seconds(s))
    recompute_wave_settled()
    sync_pdf_window()
    return True


def _set_open_flags(open_roles):
    s = STATE["scenario"]
    open_set = set(open_roles)
    s["openRoles"] = {r: (r in open_set) for r in ROLES}
    s["currentRole"] = open_roles[-1] if open_roles else None


def step_seconds(s):
    return s["testStepSeconds"] if s.get("testMode") else float(s.get("returnDelaySeconds") or DEFAULT_TEST_STEP_SECONDS)


def hold_seconds(s):
    return s["testHoldSeconds"] if s.get("testMode") else float(s.get("returnDelaySeconds") or DEFAULT_HOLD_SECONDS)


def gap_seconds(s):
    return s["testGapSeconds"] if s.get("testMode") else float(s.get("gapSeconds") or DEFAULT_GAP_SECONDS)


def arm_cycle_timer(delay):
    s = STATE["scenario"]
    now = now_ts()
    s["dwellStartedAt"] = now
    s["dwellNextAt"] = now + max(0.0, float(delay or 0))


def cycle_tick_advance():
    """Один авто-шаг фазовой машины круга. True если что-то изменилось."""
    s = STATE["scenario"]
    if not s["active"] or s["forceOpenAll"]:
        return False

    phase = s.get("phase")
    active = s.get("cyclePhaseRoles") or []
    total = len(active)
    n = int(s.get("waveIndex") or 1)

    # -------- OPEN sweep: pc1 -> ... -> pcTotal --------
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
            # все открыты -> HOLD n сек
            s["phase"] = PHASE_CYCLE_HOLD
            arm_cycle_timer(hold_seconds(s))
        recompute_wave_settled()
        sync_pdf_window()
        return True

    # -------- HOLD -> начать CLOSE --------
    if phase == PHASE_CYCLE_HOLD:
        s["phase"] = PHASE_CYCLE_CLOSE
        s["cycleStep"] = total - 1  # индекс последнего открытого
        s["popupEpoch"] += 1
        # ещё все открыты, закрытие пойдёт со следующего тика
        set_windows_sweep(active[:total], n)
        _set_open_flags(active[:total])
        arm_cycle_timer(step_seconds(s))
        recompute_wave_settled()
        sync_pdf_window()
        return True

    # -------- CLOSE sweep: pcTotal -> ... -> pc1 --------
    if phase == PHASE_CYCLE_CLOSE:
        step = int(s.get("cycleStep") if s.get("cycleStep") is not None else total - 1)
        if step > 0:
            step -= 1
            s["cycleStep"] = step
            s["popupEpoch"] += 1
            opened = active[:step + 1]  # осталось открыто первых step+1
            set_windows_sweep(opened, n)
            _set_open_flags(opened)
            arm_cycle_timer(step_seconds(s))
        else:
            # закрыт последний (pc1) -> SETTLE накопительной раскладки
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
            s["phase"] = PHASE_FINAL_HOLD
            set_windows_settled(active[:total], total)
            _set_open_flags(active[:total])
            clear_scenario_timers()
            recompute_wave_settled()
            sync_pdf_window()
            return True
        # следующий круг
        s["waveIndex"] = n + 1
        s["phase"] = PHASE_CYCLE_OPEN
        s["cycleStep"] = 0
        s["popupEpoch"] += 1
        opened = active[:1]
        set_windows_sweep(opened, n + 1)
        _set_open_flags(opened)
        arm_cycle_timer(step_seconds(s))
        recompute_wave_settled()
        sync_pdf_window()
        return True

    # -------- FINAL_HOLD: в тесте просто висим --------
    if phase == PHASE_FINAL_HOLD:
        return False

    return False

def start_test_run(source: dict | None = None):
    active = get_online_roles()
    if not active:
        return False
    return start_cycles(active, source or {"type": "test_run"}, test=True)


def arm_test_timer(delay_seconds: float):
    s = STATE["scenario"]
    s["testNextAt"] = now_ts() + max(0.0, float(delay_seconds or 0))

def set_test_prefix(n: int):
    """Открыть первые n ролей из testRoles (накопительно), остальные закрыть."""
    s = STATE["scenario"]
    active = s.get("testRoles") or []
    n = max(0, min(len(active), int(n or 0)))
    open_set = set(active[:n])
    s["openRoles"] = {r: (r in open_set) for r in ROLES}
    opened = [r for r in active if r in open_set]
    s["currentRole"] = opened[-1] if opened else None


def settle_test_into_dwell():
    s = STATE["scenario"]
    s["phase"] = PHASE_DWELL
    s["pendulumStep"] = None
    s["waveIndex"] = 1
    set_test_prefix(1)
    s["popupEpoch"] += 1
    arm_test_timer(s["testDwellSeconds"])
    recompute_wave_settled()
    sync_pdf_window()

def test_tick_advance():
    """Один авто-шаг тест-режима. Возвращает True, если что-то изменилось."""
    s = STATE["scenario"]
    if not s.get("testMode") or not s["active"] or s["forceOpenAll"]:
        return False

    phase = s.get("phase")

    # --- Маятник: идём по testPendulumRoute авто-шагами ---
    if phase == PHASE_PENDULUM:
        route = s.get("testPendulumRoute") or []
        step = int(s.get("pendulumStep") or 0)
        last_index = len(route) - 1

        if step < last_index:
            next_step = step + 1
            s["pendulumStep"] = next_step
            s["popupEpoch"] += 1
            set_only_open_role(route[next_step])
            arm_test_timer(s["testStepSeconds"])
            recompute_wave_settled()
            sync_pdf_window()
            return True

        # маятник осел на первом активном ПК -> входим в dwell wave1
        settle_test_into_dwell()
        return True

    # --- Dwell-круги: накопление по testRoles ---
    if phase == PHASE_DWELL:
        active = s.get("testRoles") or []
        total = len(active)
        current = int(s.get("waveIndex") or 1)

        if current >= total:
            # последний круг осел -> final_hold
            s["phase"] = PHASE_FINAL_HOLD
            set_test_prefix(total)
            arm_test_timer(s["testDwellSeconds"])
            recompute_wave_settled()
            sync_pdf_window()
            return True

        next_wave = current + 1
        s["waveIndex"] = next_wave
        s["popupEpoch"] += 1
        set_test_prefix(next_wave)
        arm_test_timer(s["testDwellSeconds"])
        recompute_wave_settled()
        sync_pdf_window()
        return True

    # --- Final hold: авто-закрытие (эмуляция MIDI-ноты на последнем ПК) ---
    if phase == PHASE_FINAL_HOLD:
        close_scenario({"type": "test_run_auto_close"})
        return True

    return False

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
# EPIC A2: реестр устройств
# ---------------------------------------------------------------------------
def touch_device(role: str, host_name: str | None = None):
    """Обновляем lastSeen на identify/ping. host_name пишем только если пришёл."""
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
        # lastSeenAt НЕ трогаем — пусть видно, когда видели в последний раз.


async def device_sweeper():
    """Фоновая задача: помечает offline тех, кого давно не видели."""
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


def advance_dwell_timer(source: dict | None = None):
    s = STATE["scenario"]
    if not s["active"] or s["forceOpenAll"]:
        return
    if s.get("phase") != PHASE_DWELL:
        return

    current_wave = int(s.get("waveIndex") or 1)
    if current_wave >= 4:
        s["phase"] = PHASE_FINAL_HOLD
        set_open_roles_prefix(4)
        clear_scenario_timers()
        recompute_wave_settled()
        sync_pdf_window()
        return

    next_wave = current_wave + 1
    s["waveIndex"] = next_wave
    s["popupEpoch"] += 1
    set_open_roles_prefix(next_wave)

    if next_wave >= 4:
        s["phase"] = PHASE_FINAL_HOLD
        clear_scenario_timers()
    else:
        s["phase"] = PHASE_DWELL
        arm_dwell_timer()

    recompute_wave_settled()
    sync_pdf_window()

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
                bump_version()
                await hub.broadcast("cycle_tick")
    except asyncio.CancelledError:
        pass

# ---------------------------------------------------------------------------
# Ядро волн (без изменений относительно Slice 5)
# ---------------------------------------------------------------------------
def sanitize_role(role) -> str:
    return role if role in ROLES else "pc1"


def get_last_open_role():
    opened = [r for r in ROLES if STATE["scenario"]["openRoles"].get(r)]
    return opened[-1] if opened else None


def recompute_wave_settled():
    s = STATE["scenario"]
    if not s["active"] or s["forceOpenAll"]:
        s["waveSettled"] = False
        return
    # settled == раскладка осела (settle/final_hold), sweep -> False
    s["waveSettled"] = s.get("phase") in (PHASE_CYCLE_SETTLE, PHASE_FINAL_HOLD)


def reset_open_roles():
    STATE["scenario"]["openRoles"] = {r: False for r in ROLES}


def set_only_open_role(role: str | None):
    target = sanitize_role(role) if role else None
    STATE["scenario"]["openRoles"] = {r: (r == target) for r in ROLES}
    STATE["scenario"]["currentRole"] = target


def set_open_roles_prefix(n: int):
    n = max(0, min(len(ROLES), int(n or 0)))
    STATE["scenario"]["openRoles"] = {
        r: (idx < n) for idx, r in enumerate(ROLES)
    }
    opened = [r for r in ROLES if STATE["scenario"]["openRoles"][r]]
    STATE["scenario"]["currentRole"] = opened[-1] if opened else None


def clear_scenario_timers():
    s = STATE["scenario"]
    s["dwellStartedAt"] = None
    s["dwellNextAt"] = None


def arm_dwell_timer(delay_seconds: float | None = None):
    s = STATE["scenario"]
    delay = s.get("dwellSeconds") if delay_seconds is None else delay_seconds
    delay = float(delay or 0)
    now = now_ts()
    s["dwellStartedAt"] = now
    s["dwellNextAt"] = now + max(0.0, delay)


def get_pendulum_role(step: int | None):
    if step is None:
        return None
    if 0 <= step < len(PENDULUM_ROUTE):
        return PENDULUM_ROUTE[step]
    return None


def pdf_file_for_wave(n: int) -> str:
    """pdf круга N: pdf1.pdf..pdf4.pdf (n — 1-based номер круга)."""
    return f"pdf{n}.pdf"


def set_windows_sweep(open_roles_ordered, wave_n):
    """Во время open/close: у открытых ролей одна вкладка = pdf текущей волны."""
    s = STATE["scenario"]
    pdf = pdf_file_for_wave(wave_n)
    open_set = set(open_roles_ordered)
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
    """Settle круга N: на pcK активна pdfK, доступны pdf1..pdfN."""
    s = STATE["scenario"]
    tabs_all = [pdf_file_for_wave(i + 1) for i in range(wave_n)]
    settled_set = set(settled_roles_ordered)
    wins = {}
    for idx, r in enumerate(ROLES):
        if r in settled_set:
            k = idx + 1  # pcK -> активная вкладка K
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
    """Совместимость по имени: пересобирает legacy-окно из pdfWindowsByRole."""
    if STATE["scenario"].get("forceOpenAll"):
        STATE["pdfWindowsByRole"] = {
            r: {"visible": True, "tabs": [pdf_file_for_wave(1)],
                "activeTab": pdf_file_for_wave(1),
                "token": f'{STATE["scenario"]["popupEpoch"]}:{r}:all'}
            for r in ROLES
        }
    sync_legacy_pdf_window()


def start_pendulum(trigger: dict | None = None):
    s = STATE["scenario"]
    trigger = trigger or {}

    if trigger.get("type") == "click_threshold" and trigger.get("role"):
        STATE["clickScenarioLockedByRole"][sanitize_role(trigger["role"])] = True

    s["active"] = True
    s["trigger"] = trigger
    s["phase"] = PHASE_PENDULUM
    s["popupEpoch"] += 1
    s["popupPage"] = 0
    s["startedAt"] = now_ts()
    s["forceOpenAll"] = False
    s["restoreAfterForce"] = None

    s["pendulumStep"] = 0
    s["waveIndex"] = 1
    s["finalHoldRole"] = "pc4"

    clear_scenario_timers()
    set_only_open_role(get_pendulum_role(0))

    recompute_wave_settled()
    sync_pdf_window()


def settle_into_dwell_wave1():
    s = STATE["scenario"]
    s["phase"] = PHASE_DWELL
    s["pendulumStep"] = None
    s["waveIndex"] = 1
    set_open_roles_prefix(1)
    s["popupEpoch"] += 1
    arm_dwell_timer()
    recompute_wave_settled()
    sync_pdf_window()


def advance_pendulum(source: dict | None = None):
    s = STATE["scenario"]
    if not s["active"] or s["forceOpenAll"]:
        return
    if s.get("phase") != PHASE_PENDULUM:
        return

    step = s.get("pendulumStep")
    if step is None:
        step = 0

    next_step = step + 1
    if next_step >= len(PENDULUM_ROUTE):
        return

    next_role = get_pendulum_role(next_step)
    s["pendulumStep"] = next_step
    s["popupEpoch"] += 1
    set_only_open_role(next_role)
    recompute_wave_settled()
    sync_pdf_window()

def start_scenario(trigger: dict, role: str = "pc1"):
    if trigger.get("type") == "click_threshold" and trigger.get("role"):
        STATE["clickScenarioLockedByRole"][sanitize_role(trigger["role"])] = True
    active = [r for r in ROLES]  # боевой сценарий по всем 4 ПК
    start_cycles(active, trigger, test=False)


def open_role(role: str, source: dict | None = None):
    target = sanitize_role(role)
    s = STATE["scenario"]
    source = source or {}

    if not s["active"]:
        s["active"] = True
        s["trigger"] = {"type": "open", "role": target, "source": source}
        s["phase"] = "manual_midi"
        s["popupEpoch"] += 1
        s["popupPage"] = 0
        s["startedAt"] = now_ts()
        s["forceOpenAll"] = False
        s["restoreAfterForce"] = None
        s["pendulumStep"] = None
        s["waveIndex"] = max(1, int(s.get("waveIndex") or 1))
        clear_scenario_timers()
        reset_open_roles()
        s["openRoles"][target] = True
        s["currentRole"] = target
        recompute_wave_settled()
        sync_pdf_window()
        return

    if (
            not s["forceOpenAll"]
            and s["currentRole"] == target
            and s["openRoles"].get(target)
    ):
        return

    if s["forceOpenAll"]:
        s["forceOpenAll"] = False
        s["restoreAfterForce"] = None

    s["active"] = True
    s["phase"] = "manual_midi"
    s["pendulumStep"] = None
    clear_scenario_timers()
    s["currentRole"] = target
    s["openRoles"][target] = True
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
        s["phase"] = "manual_midi"
        s["pendulumStep"] = None
        clear_scenario_timers()
        recompute_wave_settled()
        sync_pdf_window()


def advance_wave(source: dict | None = None):
    s = STATE["scenario"]
    source = source or {}

    if not s["active"] or s["forceOpenAll"]:
        return

    phase = s.get("phase")

    if phase == PHASE_PENDULUM:
        advance_pendulum(source)
        return

    if phase == PHASE_FINAL_HOLD:
        source_role = sanitize_role((source or {}).get("role", "pc1"))
        final_role = sanitize_role(s.get("finalHoldRole") or "pc4")
        if source_role == final_role:
            close_scenario({**source, "type": "launch_close_final_hold"})
        return

    if phase == PHASE_DWELL:
        return

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
            "pendulumStep": s.get("pendulumStep"),
            "dwellStartedAt": s.get("dwellStartedAt"),
            "dwellNextAt": s.get("dwellNextAt"),
        }
        s["forceOpenAll"] = True
        s["active"] = True
        s["phase"] = "force_open_all"
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
        s["pendulumStep"] = restore.get("pendulumStep")
        s["dwellStartedAt"] = restore.get("dwellStartedAt")
        s["dwellNextAt"] = restore.get("dwellNextAt")
        s["openRoles"] = restore.get("openRoles") or {r: False for r in ROLES}
        s["phase"] = restore.get("phase") or "manual_midi"
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
    STATE["scenario"]["pendulumStep"] = None
    STATE["scenario"]["dwellStartedAt"] = None
    STATE["scenario"]["dwellNextAt"] = None
    STATE["scenario"]["waveSettled"] = False
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
# lifespan: запуск/останов фоновой задачи
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    device_task = asyncio.create_task(device_sweeper())
    scenario_task = asyncio.create_task(scenario_timer_loop())
    try:
        yield
    finally:
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

PDF_DIR = BASE_DIR / "pdfs"
PDF_DIR.mkdir(exist_ok=True)
app.mount("/pdfs", StaticFiles(directory=str(PDF_DIR)), name="pdfs")
# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/state")
def get_state():
    return clone_state()


async def apply_action(t: str, p: dict):
    role = sanitize_role(p.get("role", "pc1"))
    if t == "click_card":
        card_idx = str(int(p.get("cardIndex", 0)))
        cur = STATE["flippedCardsByRole"][role].get(card_idx, False)
        STATE["flippedCardsByRole"][role][card_idx] = not cur
        STATE["clicksByRole"][role] += 1
        if (
            not STATE["scenario"]["active"]
            and not STATE["clickScenarioLockedByRole"][role]
            and STATE["clicksByRole"][role] >= CLICK_THRESHOLD
        ):
            start_scenario(
                {"type": "click_threshold", "role": role,
                 "clicks": STATE["clicksByRole"][role]},
                "pc1",
            )
        bump_version()
        await hub.broadcast("click_card")
        return {"ok": True}
    if t == "open_role_popup":
        open_role(role, {"type": "manual_open", "role": role})
        bump_version()
        await hub.broadcast("open_role_popup")
        return {"ok": True}
    if t == "close_role_popup":
        close_role(role, {"type": "manual_close", "role": role})
        bump_version()
        await hub.broadcast("close_role_popup")
        return {"ok": True}
    if t == "launch":
        advance_wave({"type": "manual_launch", "role": role})
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
    if t == "start_pendulum":
        start_pendulum({"type": "manual_debug_start", "role": role})
        bump_version()
        await hub.broadcast("start_pendulum")
        return {"ok": True}

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

    if t == "debug_set_final_hold":
        s = STATE["scenario"]
        s["active"] = True
        s["phase"] = PHASE_FINAL_HOLD
        s["pendulumStep"] = None
        s["waveIndex"] = 4
        s["finalHoldRole"] = "pc4"
        s["popupEpoch"] += 1
        clear_scenario_timers()
        set_open_roles_prefix(4)
        recompute_wave_settled()
        sync_pdf_window()
        bump_version()
        await hub.broadcast("debug_set_final_hold")
        return {"ok": True}
    return {"ok": False, "error": f"Unknown action: {t}"}


class ActionBody(BaseModel):
    type: str
    payload: dict = {}

class GlobalSettingsBody(BaseModel):
    returnDelaySeconds: float
    dwellSeconds: float

@app.post("/api/action")
async def action(body: ActionBody):
    return await apply_action(body.type, body.payload or {})

@app.get("/api/settings/global")
def get_global_settings():
    return dict(GLOBAL_SETTINGS)


@app.post("/api/settings/global")
async def set_global_settings(body: GlobalSettingsBody):
    GLOBAL_SETTINGS["returnDelaySeconds"] = float(body.returnDelaySeconds)
    GLOBAL_SETTINGS["dwellSeconds"] = float(body.dwellSeconds)

    save_global_settings(GLOBAL_SETTINGS)

    STATE["scenario"]["returnDelaySeconds"] = GLOBAL_SETTINGS["returnDelaySeconds"]
    STATE["scenario"]["dwellSeconds"] = GLOBAL_SETTINGS["dwellSeconds"]

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
                # EPIC A2: ping двигает lastSeen, если уже идентифицированы
                if bound_role:
                    touch_device(bound_role)
                continue

            if mtype == "identify":
                bound_role = sanitize_role(payload.get("role", "pc1"))
                touch_device(bound_role, payload.get("hostName", ""))
                await hub.broadcast("identify")
                continue

            if mtype == "action":
                inner = payload
                await apply_action(inner.get("type"), inner.get("payload") or {})
                continue
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(ws)
        if bound_role:
            mark_device_offline(bound_role)
        await hub.broadcast("disconnect")