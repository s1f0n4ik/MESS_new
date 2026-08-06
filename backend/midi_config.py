"""MIDI-конфиг: legacy-маппинг из старого приложения, перенесён один-в-один.
Полевая сверка на месте установки (см. PROGRESS): channel=2, PC-10.
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MIDI_SETTINGS_PATH = BASE_DIR / "midi-settings.json"

LEGACY_CHANNEL = 2
LEGACY_OUTPUT_NOTE = 72
LEGACY_OUTPUT_VELOCITY = 100
LEGACY_OUTPUT_DURATION_MS = 180
LEGACY_PORT_HINT = "PC-10"
DEDUPE_WINDOW_MS = 180

MIDI_ACTIONS = [
    "launch", "toggle_force_open_all", "reset_scenario", "hard_reset",
    "minimize_all_windows",
    "open_pc1", "open_pc2", "open_pc3", "open_pc4",
    "close_pc1", "close_pc2", "close_pc3", "close_pc4",
]

LEGACY_MAPPING = [
    {"channel": 2, "note": 60, "action": "launch"},
    {"channel": 2, "note": 61, "action": "open_pc1"},
    {"channel": 2, "note": 62, "action": "close_pc1"},
    {"channel": 2, "note": 63, "action": "open_pc2"},
    {"channel": 2, "note": 64, "action": "close_pc2"},
    {"channel": 2, "note": 65, "action": "open_pc3"},
    {"channel": 2, "note": 66, "action": "close_pc3"},
    {"channel": 2, "note": 67, "action": "open_pc4"},
    {"channel": 2, "note": 68, "action": "close_pc4"},
    {"channel": 2, "note": 69, "action": "minimize_all_windows"},
]


def default_midi_settings():
    return {
        "enabled": True,
        "inputName": LEGACY_PORT_HINT,
        "outputName": LEGACY_PORT_HINT,
        "filterEnabled": True,
        "filterChannel": LEGACY_CHANNEL,
        "mapping": [dict(x) for x in LEGACY_MAPPING],
    }


def load_midi_settings():
    data = default_midi_settings()
    try:
        if MIDI_SETTINGS_PATH.exists():
            raw = json.loads(MIDI_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k in ("enabled", "filterEnabled"):
                    if k in raw:
                        data[k] = bool(raw[k])
                for k in ("inputName", "outputName"):
                    if k in raw and raw[k] is not None:
                        data[k] = str(raw[k])
                if "filterChannel" in raw:
                    data["filterChannel"] = int(raw["filterChannel"])
                if isinstance(raw.get("mapping"), list) and raw["mapping"]:
                    data["mapping"] = [dict(x) for x in raw["mapping"]]
    except Exception:
        pass
    return data


def save_midi_settings(data: dict):
    MIDI_SETTINGS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def match_action(mapping, channel, note):
    """Точное совпадение канал+нота, затем нота с channel=None (любой канал)."""
    for m in mapping:
        if m.get("note") == note and m.get("channel") == channel:
            return m
    for m in mapping:
        if m.get("note") == note and m.get("channel") is None:
            return m
    return None


def action_to_spec(action: str):
    """Порт actionToSendSpec из midiMapping.js."""
    simple = {
        "launch": "launch",
        "toggle_force_open_all": "toggle_force_open_all",
        "reset_scenario": "reset_scenario",
        "hard_reset": "hard_reset",
        "minimize_all_windows": "minimize_all_windows",
    }
    if action in simple:
        return {"type": simple[action], "payload": {}}
    for pc in ("pc1", "pc2", "pc3", "pc4"):
        if action == f"open_{pc}":
            return {"type": "open_role_popup", "payload": {"role": pc}}
        if action == f"close_{pc}":
            return {"type": "close_role_popup", "payload": {"role": pc}}
    return None