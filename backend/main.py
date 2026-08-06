import asyncio
import json
import time
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from midi_router import router as midi_router
from midi_service import midi_service

from paths import PDFS_DIR
# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------
ROLES = ["pc1", "pc2", "pc3", "pc4"]
CLICK_THRESHOLD = 17

PHASE_IDLE = "idle"
PHASE_CYCLE_OPEN = "cycle_open"      # sweep открытия слева-направо
PHASE_CYCLE_HOLD = "cycle_hold"      # держим все открытыми n сек
PHASE_CYCLE_CLOSE = "cycle_close"    # sweep закрытия справа-налево
PHASE_CYCLE_SETTLE = "cycle_settle"  # осела накопительная раскладка с вкладками
PHASE_FINAL_HOLD = "final_hold"
PHASE_FORCE_OPEN_ALL = "force_open_all"
PHASE_MANUAL = "manual_midi"

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

BASE_DIR = Path(__file__).resolve().parent
GLOBAL_SETTINGS_PATH = BASE_DIR / "global-settings.json"


def now_ts() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Глобальные настройки (persist)
# ---------------------------------------------------------------------------
def default_global_settings():
    return {
        "stepSeconds": DEFAULT_STEP_SECONDS,
        "holdSeconds": DEFAULT_HOLD_SECONDS,
        "gapSeconds": DEFAULT_GAP_SECONDS,
    }


def load_global_settings():
    data = default_global_settings()
    try:
        if GLOBAL_SETTINGS_PATH.exists():
            raw = json.loads(GLOBAL_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k in ("stepSeconds", "holdSeconds", "gapSeconds"):
                    if k in raw:
                        data[k] = float(raw[k])
    except Exception:
        pass
    return data


def save_global_settings(data: dict):
    payload = {
        "stepSeconds": float(data.get("stepSeconds", DEFAULT_STEP_SECONDS) or 0),
        "holdSeconds": float(data.get("holdSeconds", DEFAULT_HOLD_SECONDS) or 0),
        "gapSeconds": float(data.get("gapSeconds", DEFAULT_GAP_SECONDS) or 0),
    }
    GLOBAL_SETTINGS_PATH.write_text(
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
    return deepcopy(STATE)


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


# ---------------------------------------------------------------------------
# Тайминги (боевые vs тест)
# ---------------------------------------------------------------------------
def step_seconds(s):
    return float(s["testStepSeconds"] if s.get("testMode") else s.get("stepSeconds") or DEFAULT_STEP_SECONDS)


def hold_seconds(s):
    return float(s["testHoldSeconds"] if s.get("testMode") else s.get("holdSeconds") or DEFAULT_HOLD_SECONDS)


def gap_seconds(s):
    return float(s["testGapSeconds"] if s.get("testMode") else s.get("gapSeconds") or DEFAULT_GAP_SECONDS)


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
    """Старт первого круга. Роли круга — ВСЕГДА pc1..pc4 (свойство сценария).
    Онлайн влияет только на то, где реально откроется окно."""
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
    s["testRoles"] = get_online_roles()      # теперь это ИНФО: где видно
    s["cyclePhaseRoles"] = active
    s["finalHoldRole"] = active[-1]          # pc4

    s["waveIndex"] = 1
    s["phase"] = PHASE_CYCLE_OPEN
    s["cycleStep"] = 0
    clear_scenario_timers()

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
            s["phase"] = PHASE_FINAL_HOLD
            s["popupEpoch"] += 1
            set_windows_settled(active[:total], total)
            _set_open_flags(active[:total])
            if s.get("testMode"):
                arm_cycle_timer(gap_seconds(s))  # тест закроется сам
            else:
                clear_scenario_timers()  # бой ждёт MIDI-ноту
            recompute_wave_settled()
            sync_pdf_window()
            return True
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

        # -------- FINAL_HOLD --------
    if phase == PHASE_FINAL_HOLD:
        if s.get("testMode"):
            close_scenario({"type": "test_run_auto_close"})
            return True
        return False

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
    device_task = asyncio.create_task(device_sweeper())
    scenario_task = asyncio.create_task(scenario_timer_loop())
    try:
        midi_service.final_hold_role = lambda: STATE["scenario"].get("finalHoldRole")
        midi_service.in_final_hold = lambda: STATE["scenario"].get("phase") == PHASE_FINAL_HOLD
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
PDF_DIR = BASE_DIR / "pdfs"
PDF_DIR.mkdir(exist_ok=True)
app.mount("/pdfs", StaticFiles(directory=str(PDFS_DIR)), name="pdfs")


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
        s["phase"] = PHASE_FINAL_HOLD
        s["cycleStep"] = None
        s["finalHoldRole"] = active[-1]
        s["popupEpoch"] += 1
        clear_scenario_timers()
        set_windows_settled(active, len(active))
        _set_open_flags(active)
        recompute_wave_settled()
        sync_pdf_window()
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
    save_global_settings(GLOBAL_SETTINGS)

    STATE["scenario"]["stepSeconds"] = GLOBAL_SETTINGS["stepSeconds"]
    STATE["scenario"]["holdSeconds"] = GLOBAL_SETTINGS["holdSeconds"]
    STATE["scenario"]["gapSeconds"] = GLOBAL_SETTINGS["gapSeconds"]

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