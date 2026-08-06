"""MIDI-listener на бэкенде. Заменяет Web MIDI (в WebKitGTK/WebView2 его нет).

Важно: rtmidi вызывает колбэк из своего потока. Прямой вызов apply_action оттуда —
гонка за STATE. Поэтому колбэк только кладёт сообщение в asyncio-очередь.
"""
import asyncio
import time
from collections import deque

import mido

from midi_config import (
    DEDUPE_WINDOW_MS,
    LEGACY_OUTPUT_DURATION_MS,
    LEGACY_OUTPUT_NOTE,
    LEGACY_OUTPUT_VELOCITY,
    action_to_spec,
    load_midi_settings,
    match_action,
    save_midi_settings,
)

LOG_LIMIT = 120


def _pick_port(names, hint):
    """Точное имя -> подстрока (rtmidi добавляет индексы вида 'PC-10 1') -> первый."""
    if not names:
        return None
    if hint:
        for n in names:
            if n == hint:
                return n
        low = hint.lower()
        for n in names:
            if low in n.lower():
                return n
    return names[0]


class MidiService:
    def __init__(self):
        self.settings = load_midi_settings()
        self.log = deque(maxlen=LOG_LIMIT)
        self.queue: asyncio.Queue | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self._in_port = None
        self._out_port = None
        self._dedupe: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._apply = None
        self._broadcast = None
        self.last_error = None

    # ---------- порты ----------
    def list_ports(self):
        try:
            return {
                "inputs": list(mido.get_input_names()),
                "outputs": list(mido.get_output_names()),
            }
        except Exception as e:
            self.last_error = f"list_ports: {e}"
            return {"inputs": [], "outputs": []}

    def _log(self, tag, **kw):
        entry = {"at": time.time(), "tag": tag, **kw}
        self.log.appendleft(entry)
        print(f"[midi] {tag} {kw}", flush=True)

    # ---------- жизненный цикл ----------
    async def start(self, apply_action, broadcast):
        self._apply = apply_action
        self._broadcast = broadcast
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue()
        self._task = asyncio.create_task(self._consume())
        self.open_input()

    async def stop(self):
        self.close_input()
        self.close_output()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def close_input(self):
        if self._in_port:
            try:
                self._in_port.close()
            except Exception:
                pass
            self._in_port = None

    def close_output(self):
        if self._out_port:
            try:
                self._out_port.close()
            except Exception:
                pass
            self._out_port = None

    def open_input(self):
        self.close_input()
        if not self.settings.get("enabled"):
            self._log("disabled")
            return False
        names = self.list_ports()["inputs"]
        target = _pick_port(names, self.settings.get("inputName"))
        if not target:
            self.last_error = "no MIDI inputs found"
            self._log("no_input", available=names)
            return False
        try:
            self._in_port = mido.open_input(target, callback=self._on_message)
            self.last_error = None
            self._log("input_open", port=target)
            return True
        except Exception as e:
            self.last_error = f"open_input({target}): {e}"
            self._log("input_error", error=str(e), port=target)
            return False

    def open_output(self):
        self.close_output()
        names = self.list_ports()["outputs"]
        target = _pick_port(names, self.settings.get("outputName"))
        if not target:
            return None
        try:
            self._out_port = mido.open_output(target)
            self._log("output_open", port=target)
            return self._out_port
        except Exception as e:
            self.last_error = f"open_output({target}): {e}"
            self._log("output_error", error=str(e))
            return None

    # ---------- приём ----------
    def _on_message(self, msg):
        """Вызывается из потока rtmidi. Только кладём в очередь."""
        if msg.type != "note_on" or msg.velocity == 0:
            return
        if self.loop and self.queue:
            self.loop.call_soon_threadsafe(
                self.queue.put_nowait,
                {"channel": msg.channel + 1, "note": msg.note, "velocity": msg.velocity},
            )

    async def _consume(self):
        try:
            while True:
                item = await self.queue.get()
                try:
                    await self._handle(item)
                except Exception as e:
                    self._log("handle_error", error=str(e))
        except asyncio.CancelledError:
            pass

    async def _handle(self, m):
        ch, note = m["channel"], m["note"]

        key = f"{ch}:{note}"
        now = time.time() * 1000.0
        last = self._dedupe.get(key, 0.0)
        if now - last < DEDUPE_WINDOW_MS:
            self._log("deduped", channel=ch, note=note)
            return
        self._dedupe[key] = now

        if self.settings.get("filterEnabled") and ch != int(self.settings.get("filterChannel", 2)):
            self._log("filtered", channel=ch, note=note)
            return

        hit = match_action(self.settings.get("mapping") or [], ch, note)
        if not hit:
            self._log("unmapped", channel=ch, note=note)
            return

        spec = action_to_spec(hit["action"])
        if not spec:
            self._log("no_spec", action=hit["action"])
            return

        payload = dict(spec.get("payload") or {})
        if spec["type"] == "launch":
            if "role" not in payload:
                payload["role"] = self.final_hold_role() or "pc4"
            if not self.in_final_hold():
                self._log("launch_ignored", channel=ch, note=note,
                          reason="not in final_hold")
                return

        self._log("dispatch", channel=ch, note=note, action=hit["action"], type=spec["type"])
        await self._apply(spec["type"], payload)
        if self._broadcast:
            await self._broadcast("midi_action")

    def in_final_hold(self):
        return True

    # переопределяется из роутера, чтобы не тянуть STATE в этот модуль
    def final_hold_role(self):
        return None

    # ---------- отправка ----------
    async def send_test_note(self, note=None, velocity=None, channel=None, duration_ms=None):
        out = self._out_port or self.open_output()
        if not out:
            return False
        note = LEGACY_OUTPUT_NOTE if note is None else int(note)
        velocity = LEGACY_OUTPUT_VELOCITY if velocity is None else int(velocity)
        channel = int(self.settings.get("filterChannel", 2)) if channel is None else int(channel)
        duration = (LEGACY_OUTPUT_DURATION_MS if duration_ms is None else int(duration_ms)) / 1000.0
        try:
            out.send(mido.Message("note_on", channel=channel - 1, note=note, velocity=velocity))
            await asyncio.sleep(duration)
            out.send(mido.Message("note_off", channel=channel - 1, note=note, velocity=0))
            self._log("output_test_sent", note=note, channel=channel)
            return True
        except Exception as e:
            self._log("output_test_failed", error=str(e))
            return False

    def apply_settings(self, patch: dict):
        for k in ("enabled", "filterEnabled"):
            if k in patch:
                self.settings[k] = bool(patch[k])
        for k in ("inputName", "outputName"):
            if k in patch:
                self.settings[k] = str(patch[k] or "")
        if "filterChannel" in patch:
            self.settings["filterChannel"] = int(patch["filterChannel"])
        if isinstance(patch.get("mapping"), list):
            self.settings["mapping"] = [dict(x) for x in patch["mapping"]]
        save_midi_settings(self.settings)
        self.open_input()
        return self.settings

    def status(self):
        ports = self.list_ports()
        return {
            "enabled": bool(self.settings.get("enabled")),
            "inputOpen": self._in_port is not None,
            "inputPort": getattr(self._in_port, "name", None),
            "outputPort": getattr(self._out_port, "name", None),
            "lastError": self.last_error,
            "ports": ports,
            "settings": self.settings,
            "log": list(self.log)[:60],
        }


midi_service = MidiService()