import asyncio
import json
from copy import deepcopy
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pathlib import Path
ROLES = ["pc1", "pc2", "pc3", "pc4"]
CLICK_THRESHOLD = 17

app = FastAPI(title="Postcards Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PDF_DIR = Path(__file__).parent / "pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/pdfs", StaticFiles(directory=str(PDF_DIR)), name="pdfs")


def initial_state():
    return {
        "stateVersion": 1,
        "clicksByRole": {r: 0 for r in ROLES},
        "clickScenarioLockedByRole": {r: False for r in ROLES},
        "flippedCardsByRole": {r: {str(i): False for i in range(8)} for r in ROLES},
        "pdfsByRole": {"pc1": "pc1.pdf", "pc2": "pc2.pdf", "pc3": "pc3.pdf", "pc4": "pc4.pdf"},
        "pdfWindow": {"visible": False, "role": "pc1", "pdfFile": "pc1.pdf", "token": ""},
        "scenario": {
            "active": False,
            "triggerRole": None,
            "currentRole": None,
            "openRoles": {r: False for r in ROLES},
            "popupEpoch": 0,
        },
    }


STATE = initial_state()
SUBSCRIBERS: set[asyncio.Queue] = set()


def clone_state():
    return deepcopy(STATE)


async def broadcast(reason: str):
    payload = {"type": "state", "reason": reason, "payload": clone_state()}
    dead = []
    for q in SUBSCRIBERS:
        try:
            q.put_nowait(payload)
        except Exception:
            dead.append(q)
    for q in dead:
        SUBSCRIBERS.discard(q)


def bump_version():
    STATE["stateVersion"] += 1


def open_role(role: str):
    STATE["scenario"]["openRoles"][role] = True
    STATE["scenario"]["currentRole"] = role
    STATE["pdfWindow"]["visible"] = True
    STATE["pdfWindow"]["role"] = role
    STATE["pdfWindow"]["pdfFile"] = STATE["pdfsByRole"][role]
    STATE["pdfWindow"]["token"] = f'{STATE["scenario"]["popupEpoch"]}:{role}'


def close_role(role: str):
    STATE["scenario"]["openRoles"][role] = False
    if role == STATE["scenario"]["currentRole"]:
        STATE["pdfWindow"]["visible"] = False


def start_scenario(trigger_role: str):
    STATE["scenario"]["active"] = True
    STATE["scenario"]["triggerRole"] = trigger_role
    STATE["scenario"]["popupEpoch"] += 1
    for r in ROLES:
        STATE["scenario"]["openRoles"][r] = False
    # как в исходной логике — старт всегда с pc1
    open_role("pc1")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/state")
def get_state():
    return clone_state()


@app.get("/api/stream")
async def stream(request: Request):
    q: asyncio.Queue = asyncio.Queue()
    SUBSCRIBERS.add(q)

    async def event_gen():
        # initial snapshot
        first = {"type": "state", "reason": "initial", "payload": clone_state()}
        yield f"data: {json.dumps(first, ensure_ascii=False)}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            SUBSCRIBERS.discard(q)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


class ActionBody(BaseModel):
    type: str
    payload: dict = {}


@app.post("/api/action")
async def action(body: ActionBody):
    t = body.type
    p = body.payload or {}
    role = p.get("role", "pc1")
    if role not in ROLES:
        role = "pc1"

    if t == "click_card":
        card_idx = str(int(p.get("cardIndex", 0)))
        current = STATE["flippedCardsByRole"][role].get(card_idx, False)
        STATE["flippedCardsByRole"][role][card_idx] = not current
        STATE["clicksByRole"][role] += 1

        if (
            not STATE["scenario"]["active"]
            and not STATE["clickScenarioLockedByRole"][role]
            and STATE["clicksByRole"][role] >= CLICK_THRESHOLD
        ):
            STATE["clickScenarioLockedByRole"][role] = True
            start_scenario(trigger_role=role)

        bump_version()
        await broadcast("click_card")
        return {"ok": True}

    if t == "open_role_popup":
        open_role(role)
        bump_version()
        await broadcast("open_role_popup")
        return {"ok": True}

    if t == "close_role_popup":
        close_role(role)
        bump_version()
        await broadcast("close_role_popup")
        return {"ok": True}

    if t == "launch":
        # переход по кругу
        cur = STATE["scenario"]["currentRole"] or "pc1"
        i = ROLES.index(cur)
        nxt = ROLES[(i + 1) % len(ROLES)]
        open_role(nxt)
        bump_version()
        await broadcast("launch")
        return {"ok": True}

    if t == "reset_all":
        STATE.clear()
        STATE.update(initial_state())
        await broadcast("reset_all")
        return {"ok": True}

    return {"ok": False, "error": f"Unknown action: {t}"}