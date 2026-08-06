"""Точка входа для собранного бэкенда (PyInstaller onefile)."""
import multiprocessing
import os
import sys

import uvicorn

from paths import BASE_DIR


def main() -> None:
    # Обязательно первым делом: без этого onefile-бинарник при любом
    # обращении к multiprocessing перезапускает себя же в бесконечном цикле.
    multiprocessing.freeze_support()

    os.environ.setdefault("POSTCARDS_BASE_DIR", str(BASE_DIR))
    port = int(os.environ.get("POSTCARDS_PORT", "8787"))

    from main import app

    print(f"[serve] base_dir={BASE_DIR} port={port}", flush=True)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        # Явно фиксируем реализации: PyInstaller не видит их динамический
        # выбор и без этого WebSocket отваливается в собранном виде.
        ws="websockets",
        http="h11",
        lifespan="on",
        access_log=True,
    )


if __name__ == "__main__":
    sys.exit(main())