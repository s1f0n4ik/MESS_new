"""Единый журнал стенда: MIDI, решения сценария, события клиентов.
Пишется в файл на координаторе и отдаётся любому клиенту через /api/log/tail."""
import json
from collections import deque
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request

from paths import BASE_DIR

LOG_DIR = BASE_DIR / "data" / "logs"
_mem = deque(maxlen=2000)
router = APIRouter()


def _file():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"scenario-{datetime.now():%Y-%m-%d}.log"


def write(src: str, tag: str, **kw):
    """src: midi | scenario | pc1..pc4 (клиент). Одна строка JSON на событие."""
    rec = {"at": datetime.now().isoformat(timespec="milliseconds"), "src": src, "tag": tag, **kw}
    _mem.appendleft(rec)
    try:
        with _file().open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"[log] write failed: {e}", flush=True)


@router.get("/api/log/tail")
def tail(n: int = 300):
    return list(_mem)[:max(1, min(n, 2000))]


@router.post("/api/log/client")
async def client_event(req: Request):
    """Клиент сообщает, что сделал со своим окном: opened/closed/recreated/ws_reconnect/visibility."""
    body = await req.json()
    write(body.get("role") or "client", body.get("tag") or "event",
          **{k: v for k, v in body.items() if k not in ("role", "tag")})
    return {"ok": True}