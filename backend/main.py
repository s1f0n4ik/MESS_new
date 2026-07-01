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
    n = int(s.get("waveIndex") or 0)
    if not s["active"] or s["forceOpenAll"] or n < 1:
        s["waveSettled"] = False
        return
    expected = [f"pc{i + 1}" for i in range(n)]
    opened = [r for r in ROLES if s["openRoles"].get(r)]
    s["waveSettled"] = (
        len(opened) == n
        and all(s["openRoles"].get(r) is True for r in expected)
    )


def reset_open_roles():
    STATE["scenario"]["openRoles"] = {r: False for r in ROLES}


def sync_pdf_window():
    s = STATE["scenario"]
    cur = s["currentRole"]
    if cur in ROLES and s["openRoles"].get(cur):
        STATE["pdfWindow"]["visible"] = True
        STATE["pdfWindow"]["role"] = cur
        STATE["pdfWindow"]["pdfFile"] = STATE["pdfsByRole"][cur]
        STATE["pdfWindow"]["token"] = f'{s["popupEpoch"]}:{cur}'
    else:
        STATE["pdfWindow"]["visible"] = False


def start_scenario(trigger: dict, role: str = "pc1"):
    open_role_name = sanitize_role(role)
    if trigger and trigger.get("type") == "click_threshold" and trigger.get("role"):
        STATE["clickScenarioLockedByRole"][sanitize_role(trigger["role"])] = True
    s = STATE["scenario"]
    s["active"] = True
    s["trigger"] = trigger
    s["phase"] = "manual_midi"
    s["currentRole"] = open_role_name
    reset_open_roles()
    s["openRoles"][open_role_name] = True
    s["popupEpoch"] += 1
    s["popupPage"] = 0
    s["startedAt"] = None
    s["forceOpenAll"] = False
    s["restoreAfterForce"] = None
    s["waveIndex"] = 1
    s["waveSettled"] = False
    recompute_wave_settled()
    sync_pdf_window()


def open_role(role: str, source: dict | None = None):
    target = sanitize_role(role)
    s = STATE["scenario"]
    source = source or {}
    if not s["active"]:
        start_scenario({"type": "open", "role": target, "source": source}, target)
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
    recompute_wave_settled()
    sync_pdf_window()


def advance_wave(source: dict | None = None):
    s = STATE["scenario"]
    source = source or {}
    if not s["active"] or s["forceOpenAll"]:
        return
    prev = int(s.get("waveIndex") or 1)
    if prev >= 4:
        close_scenario({**source, "type": "launch_close"})
        return
    s["waveIndex"] = prev + 1
    s["waveSettled"] = False
    s["popupEpoch"] += 1
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
    task = asyncio.create_task(device_sweeper())
    try:
        yield
    finally:
        task.cancel()
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