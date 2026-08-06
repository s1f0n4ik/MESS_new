"""Разрешение путей к изменяемым данным.

В dev это папка backend/. В собранном .exe — папка рядом с .exe,
потому что onefile-бандл распаковывается в TEMP и удаляется при выходе:
всё, что должно переживать перезапуск (настройки, PDF), обязано лежать вне него.
"""
import os
import sys
from pathlib import Path


def base_dir() -> Path:
    env = os.environ.get("POSTCARDS_BASE_DIR")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
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