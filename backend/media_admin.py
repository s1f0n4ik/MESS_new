"""Управление медиа из служебного меню: тексты (PDF) и настраиваемые звуки.

<base_dir>/pdfs/pdf1..pdf4.pdf       — тексты (уже отдаются как /pdfs/*)
<base_dir>/audio/circle1..4.<ext>    — звук начала волны N  (отдаётся как /audio/*)
<base_dir>/audio/vibro_final.<ext>   — вибро-финал
Нет файла звука — фронт играет встроенный из бандла.
"""
from __future__ import annotations

import inspect
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PDF_SLOTS = ("pdf1", "pdf2", "pdf3", "pdf4")
AUDIO_SLOTS = ("circle1", "circle2", "circle3", "circle4", "vibro_final")
AUDIO_EXTS = (".wav", ".mp3", ".ogg", ".flac", ".m4a")


class MediaAdmin:
    def __init__(self, base_dir, pdf_dir=None, on_change: Optional[Callable] = None):
        self.base_dir = Path(base_dir)
        self.pdf_dir = Path(pdf_dir) if pdf_dir else self.base_dir / "pdfs"
        self.audio_dir = self.base_dir / "audio"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self._sources_path = self.base_dir / "media_sources.json"
        self._sources = self._load_sources()
        self._on_change = on_change

    # ---------- служебное ----------
    def _load_sources(self) -> dict:
        try:
            return json.loads(self._sources_path.read_text("utf-8"))
        except Exception:
            return {}

    def _save_sources(self) -> None:
        try:
            self._sources_path.write_text(
                json.dumps(self._sources, ensure_ascii=False, indent=2), "utf-8"
            )
        except Exception as e:
            print(f"[media] sources save failed: {e}")

    async def changed(self) -> None:
        if not self._on_change:
            return
        try:
            r = self._on_change()
            if inspect.isawaitable(r):
                await r
        except Exception as e:
            print(f"[media] on_change failed: {e}")

    def _audio_file(self, slot: str) -> Optional[Path]:
        for p in self.audio_dir.glob(f"{slot}.*"):
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                return p
        return None

    def _target(self, kind: str, slot: str, ext: str) -> Path:
        ext = (ext or "").lower()
        if kind == "pdf":
            if slot not in PDF_SLOTS:
                raise HTTPException(400, f"неизвестный слот {slot}")
            if ext != ".pdf":
                raise HTTPException(400, "для текста нужен файл .pdf")
            return self.pdf_dir / f"{slot}.pdf"
        if kind == "audio":
            if slot not in AUDIO_SLOTS:
                raise HTTPException(400, f"неизвестный слот {slot}")
            if ext not in AUDIO_EXTS:
                raise HTTPException(400, f"аудио: {', '.join(AUDIO_EXTS)}")
            return self.audio_dir / f"{slot}{ext}"
        raise HTTPException(400, "kind должен быть pdf или audio")

    def _describe(self, p: Optional[Path]) -> Optional[dict]:
        if not p or not p.exists():
            return None
        st = p.stat()
        return {
            "file": p.name,
            "size": st.st_size,
            "mtime": int(st.st_mtime),
            "source": self._sources.get(p.stem),
        }

    def snapshot(self) -> dict:
        return {
            "pdfs": {s: self._describe(self.pdf_dir / f"{s}.pdf") for s in PDF_SLOTS},
            "audio": {s: self._describe(self._audio_file(s)) for s in AUDIO_SLOTS},
            "dirs": {"pdfs": str(self.pdf_dir), "audio": str(self.audio_dir)},
        }

    # ---------- запись: временный файл рядом + атомарная подмена ----------
    def _install(self, target: Path, write, source: str) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.stem}.", suffix=".tmp")
        os.close(fd)
        try:
            write(tmp)
            try:
                os.replace(tmp, target)
            except PermissionError:
                # Windows: файл сейчас отдаётся клиенту (206 Partial Content).
                raise HTTPException(409, "файл сейчас читает клиент — повтори через пару секунд")
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        if target.parent == self.audio_dir:
            # Один слот — один файл: убираем прежнюю версию с другим расширением.
            for p in self.audio_dir.glob(f"{target.stem}.*"):
                if p != target and p.suffix.lower() in AUDIO_EXTS:
                    try:
                        p.unlink()
                    except OSError:
                        pass
        self._sources[target.stem] = source
        self._save_sources()
        print(f"[media] {target.name} <- {source}")

    def import_path(self, kind: str, slot: str, path: str) -> None:
        src = Path(path)
        if not src.is_file():
            raise HTTPException(404, f"файл не найден: {path}")
        target = self._target(kind, slot, src.suffix)
        if target.exists() and src.resolve() == target.resolve():
            return  # выбрали уже стоящий файл
        self._install(target, lambda tmp: shutil.copyfile(src, tmp), str(src))

    def import_bytes(self, kind: str, slot: str, data: bytes, filename: str) -> None:
        if not data:
            raise HTTPException(400, "пустой файл")
        target = self._target(kind, slot, Path(filename or "").suffix)
        self._install(target, lambda tmp: Path(tmp).write_bytes(data), filename or "upload")

    def remove(self, kind: str, slot: str) -> None:
        if kind != "audio":
            raise HTTPException(400, "сбросить можно только звук — у текста нет встроенного варианта")
        p = self._audio_file(slot)
        if p:
            p.unlink()
        self._sources.pop(slot, None)
        self._save_sources()
        print(f"[media] {slot}: сброшен на встроенный")


class ImportBody(BaseModel):
    kind: str
    slot: str
    path: str


def create_router(admin: MediaAdmin) -> APIRouter:
    r = APIRouter(prefix="/api/media")

    @r.get("")
    async def get_media():
        return admin.snapshot()

    @r.post("/import")
    async def import_media(body: ImportBody):
        admin.import_path(body.kind, body.slot, body.path)
        await admin.changed()
        return admin.snapshot()

    @r.post("/upload/{kind}/{slot}")
    async def upload_media(kind: str, slot: str, request: Request, filename: str = ""):
        admin.import_bytes(kind, slot, await request.body(), filename)
        await admin.changed()
        return admin.snapshot()

    @r.delete("/{kind}/{slot}")
    async def delete_media(kind: str, slot: str):
        admin.remove(kind, slot)
        await admin.changed()
        return admin.snapshot()

    return r


def mount_static(app, admin: MediaAdmin) -> None:
    app.mount("/audio", StaticFiles(directory=str(admin.audio_dir)), name="audio")