# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller postcards-backend.spec --noconfirm

block_cipher = None

# PyInstaller не находит эти модули статическим анализом:
# rtmidi подтягивается mido по имени бэкенда в рантайме,
# реализации uvicorn выбираются динамически по строке конфига.
hidden = [
    "rtmidi",
    "mido.backends.rtmidi",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "websockets.legacy",
    "websockets.legacy.server",
    "anyio._backends._asyncio",
]

a = Analysis(
    ["serve.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "PIL"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="postcards-backend",
    debug=False,
    strip=False,
    upx=False,
    # console=True обязательно: stderr нужен для проброса логов в Tauri.
    # Само окно консоли Tauri скрывает при спавне sidecar.
    console=True,
    onefile=True,
)