from fastapi import APIRouter
from pydantic import BaseModel

from midi_service import midi_service

router = APIRouter(prefix="/api/midi", tags=["midi"])


class MidiSettingsBody(BaseModel):
    enabled: bool | None = None
    inputName: str | None = None
    outputName: str | None = None
    filterEnabled: bool | None = None
    filterChannel: int | None = None
    mapping: list[dict] | None = None


class TestNoteBody(BaseModel):
    note: int | None = None
    velocity: int | None = None
    channel: int | None = None
    durationMs: int | None = None


@router.get("/status")
def midi_status():
    return midi_service.status()


@router.get("/ports")
def midi_ports():
    return midi_service.list_ports()


@router.post("/settings")
def midi_settings(body: MidiSettingsBody):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return {"ok": True, "settings": midi_service.apply_settings(patch)}


@router.post("/reopen")
def midi_reopen():
    ok = midi_service.open_input()
    return {"ok": ok, "status": midi_service.status()}


@router.post("/test-note")
async def midi_test_note(body: TestNoteBody):
    ok = await midi_service.send_test_note(
        note=body.note, velocity=body.velocity,
        channel=body.channel, duration_ms=body.durationMs,
    )
    return {"ok": ok}


class SimulateBody(BaseModel):
    note: int
    channel: int | None = None


@router.post("/simulate")
async def midi_simulate(body: SimulateBody):
    """Прогон ноты через тот же путь, что и реальный вход. Для отладки без железа."""
    ch = body.channel or int(midi_service.settings.get("filterChannel", 2))
    await midi_service._handle({"channel": ch, "note": int(body.note), "velocity": 100})
    return {"ok": True}