import asyncio
import json
import time
from contextlib import asynccontextmanager
from copy import deepcopy

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROLES = ["pc1", "pc2", "pc3", "pc4"]
CLICK_THRESHOLD = 17

PHASE_IDLE = "idle"
PHASE_PENDULUM = "pendulum"
PHASE_DWELL = "dwell"
PHASE_FINAL_HOLD = "final_hold"
PHASE_FORCE_OPEN_ALL = "force_open_all"

PENDULUM_ROUTE = ["pc1", "pc2", "pc3", "pc4", "pc3", "pc2", "pc1"]

DEFAULT_DWELL_SECONDS = 120.0
DEFAULT_RETURN_DELAY_SECONDS = 0.0
SCENARIO_TICK_INTERVAL = 0.5

# --- EPIC A2: пороги живости устройств ---
DEVICE_STALE_SECONDS = 30.0      # не видели дольше -> online:false
DEVICE_SWEEP_INTERVAL = 5.0      # как часто фоновая задача проверяет


def now_ts() -> float:
    return time.time()


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
            "pendulumStep": None,
            "dwellStartedAt": None,
            "dwellNextAt": None,
            "finalHoldRole": "pc4",
            "returnDelaySeconds": DEFAULT_RETURN_DELAY_SECONDS,
            "dwellSeconds": DEFAULT_DWELL_SECONDS,
        },
        "pdfWindow": {
            "visible": False,
            "role": None,
            "pdfFile": None,
            "token": None,
        },
    }


STATE = initial_state()


def bump_version():
    STATE["stateVersion"] += 1


def clone_state():
    return deepcopy(STATE)


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


async def scenario_timer_loop():
    try:
        while True:
            await asyncio.sleep(SCENARIO_TICK_INTERVAL)

            s = STATE["scenario"]
            if not s["active"] or s["forceOpenAll"]:
                continue

            changed = False
            now = now_ts()

            # 1) конец pendulum -> старт dwell
            if s.get("phase") == PHASE_PENDULUM and s.get("pendulumStep") == len(PENDULUM_ROUTE) - 1:
                delay = float(s.get("returnDelaySeconds") or 0.0)
                due_at = s.get("dwellNextAt")

                if due_at is None:
                    s["dwellStartedAt"] = now
                    s["dwellNextAt"] = now + max(0.0, delay)
                    changed = True
                elif now >= due_at:
                    settle_into_dwell_wave1()
                    changed = True

            # 2) dwell timer
            elif s.get("phase") == PHASE_DWELL:
                due_at = s.get("dwellNextAt")
                if due_at is not None and now >= due_at:
                    prev_phase = s.get("phase")
                    prev_wave = s.get("waveIndex")
                    advance_wave({"type": "timer_dwell_advance", "waveIndex": prev_wave})
                    changed = True

            if changed:
                bump_version()
                await hub.broadcast("scenario_timer")
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

    phase = s.get("phase")

    if phase == PHASE_PENDULUM:
        step = s.get("pendulumStep")
        s["waveSettled"] = (step == len(PENDULUM_ROUTE) - 1)
        return

    if phase in (PHASE_DWELL, PHASE_FINAL_HOLD):
        n = int(s.get("waveIndex") or 0)
        if n < 1:
            s["waveSettled"] = False
            return
        expected = [f"pc{i + 1}" for i in range(n)]
        opened = [r for r in ROLES if s["openRoles"].get(r)]
        s["waveSettled"] = (
                len(opened) == n
                and all(s["openRoles"].get(r) is True for r in expected)
        )
        return

    s["waveSettled"] = False


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


def sync_pdf_window():
    s = STATE["scenario"]
    cur = s["currentRole"]

    if s.get("forceOpenAll"):
        STATE["pdfWindow"]["visible"] = True
        STATE["pdfWindow"]["role"] = "all"
        STATE["pdfWindow"]["pdfFile"] = None
        STATE["pdfWindow"]["token"] = f'{s["popupEpoch"]}:all'
        return

    if cur in ROLES and s["openRoles"].get(cur):
        STATE["pdfWindow"]["visible"] = True
        STATE["pdfWindow"]["role"] = cur
        STATE["pdfWindow"]["pdfFile"] = STATE["pdfsByRole"][cur]
        STATE["pdfWindow"]["token"] = f'{s["popupEpoch"]}:{cur}'
    else:
        STATE["pdfWindow"]["visible"] = False
        STATE["pdfWindow"]["role"] = None
        STATE["pdfWindow"]["pdfFile"] = None
        STATE["pdfWindow"]["token"] = None


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
        settle_into_dwell_wave1()
        return

    s["pendulumStep"] = next_step
    s["popupEpoch"] += 1
    set_only_open_role(get_pendulum_role(next_step))
    recompute_wave_settled()
    sync_pdf_window()

    if next_step == len(PENDULUM_ROUTE) - 1:
        # Осели на pc1; следующая логика уже через dwell-таймер.
        settle_into_dwell_wave1()


def start_scenario(trigger: dict, role: str = "pc1"):
    start_pendulum(trigger)


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
        close_scenario({**source, "type": "launch_close_final_hold"})
        return

    if phase != PHASE_DWELL:
        return

    prev = int(s.get("waveIndex") or 1)
    if prev >= 4:
        s["phase"] = PHASE_FINAL_HOLD
        set_open_roles_prefix(4)
        clear_scenario_timers()
        recompute_wave_settled()
        sync_pdf_window()
        return

    s["waveIndex"] = prev + 1
    s["popupEpoch"] += 1
    set_open_roles_prefix(s["waveIndex"])

    if s["waveIndex"] >= 4:
        s["phase"] = PHASE_FINAL_HOLD
        clear_scenario_timers()
    else:
        s["phase"] = PHASE_DWELL
        arm_dwell_timer()

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
    return {"ok": False, "error": f"Unknown action: {t}"}


class ActionBody(BaseModel):
    type: str
    payload: dict = {}


@app.post("/api/action")
async def action(body: ActionBody):
    return await apply_action(body.type, body.payload or {})


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