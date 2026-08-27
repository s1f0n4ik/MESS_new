"""Разрешение путей к изменяемым данным.

Dev: папка backend/. Собранный .exe на Windows: %LOCALAPPDATA%\\Postcards —
Program Files защищён от записи, а onefile-бандл распаковывается в TEMP
и удаляется при выходе. POSTCARDS_BASE_DIR остаётся как переопределение.
"""
import os
import sys
from pathlib import Path


def base_dir() -> Path:
    env = os.environ.get("POSTCARDS_BASE_DIR")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
            return Path(os.environ["LOCALAPPDATA"]) / "Postcards"
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR = base_dir()
DATA_DIR = BASE_DIR / "data"
PDFS_DIR = DATA_DIR / "pdfs"
SETTINGS_DIR = DATA_DIR / "settings"

for _d in (DATA_DIR, PDFS_DIR, SETTINGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

GLOBAL_SETTINGS_FILE = SETTINGS_DIR / "global-settings.json"
MIDI_SETTINGS_FILE = SETTINGS_DIR / "midi-settings.json"