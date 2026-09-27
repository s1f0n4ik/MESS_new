"""Редактируемый слой поверх исходных PDF с датированной историей версий."""
from __future__ import annotations

import inspect
import json
import mimetypes
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


PDF_SLOTS = ("pdf1", "pdf2", "pdf3", "pdf4")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 25 * 1024 * 1024


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%d-%H%M%S-%f")


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    try:
        Path(tmp).write_text(json.dumps(value, ensure_ascii=False, indent=2), "utf-8")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _num(value, default=0.0, low=0.0, high=1.0) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        n = default
    return max(low, min(high, n))


class SaveBody(BaseModel):
    baseRevision: int = 0
    updatedBy: str = "unknown"
    pages: dict = {}


class ArchiveConfigBody(BaseModel):
    path: str = ""


class PdfEditorStore:
    def __init__(self, data_dir: Path, on_change: Optional[Callable] = None):
        self.root = Path(data_dir) / "pdf-editor"
        self.docs_dir = self.root / "documents"
        self.assets_dir = self.root / "assets"
        self.history_dir = self.root / "history"
        self.config_path = self.root / "config.json"
        archive = os.environ.get("POSTCARDS_EDITOR_ARCHIVE_DIR")
        self.archive_from_environment = bool(archive)
        if not archive:
            try:
                archive = str(json.loads(self.config_path.read_text("utf-8")).get("archiveDir") or "")
            except Exception:
                archive = ""
        self.archive_dir = Path(archive) if archive else None
        for folder in (self.docs_dir, self.assets_dir, self.history_dir):
            folder.mkdir(parents=True, exist_ok=True)
        self._on_change = on_change

    def _check_slot(self, slot: str) -> str:
        if slot not in PDF_SLOTS:
            raise HTTPException(404, f"неизвестный документ {slot}")
        return slot

    def _current_path(self, slot: str) -> Path:
        return self.docs_dir / f"{slot}.json"

    @staticmethod
    def _empty(slot: str) -> dict:
        return {"schemaVersion": 1, "slot": slot, "revision": 0,
                "updatedAt": None, "updatedBy": None, "pages": {}}

    def load(self, slot: str) -> dict:
        slot = self._check_slot(slot)
        try:
            value = json.loads(self._current_path(slot).read_text("utf-8"))
            if isinstance(value, dict) and value.get("slot") == slot:
                return value
        except Exception:
            pass
        return self._empty(slot)

    def _clean_element(self, slot: str, raw: dict) -> dict | None:
        if not isinstance(raw, dict) or raw.get("type") not in ("text", "image", "cover"):
            return None
        kind = raw["type"]
        item = {
            "id": re.sub(r"[^a-zA-Z0-9_-]", "", str(raw.get("id") or uuid.uuid4().hex))[:80],
            "type": kind,
            "x": _num(raw.get("x"), 0.1), "y": _num(raw.get("y"), 0.1),
            "w": _num(raw.get("w"), 0.3, 0.01, 1.0),
            "h": _num(raw.get("h"), 0.1, 0.01, 1.0),
        }
        if kind == "text":
            item.update({
                "text": str(raw.get("text") or "")[:20000],
                "fontSize": _num(raw.get("fontSize"), 28, 6, 240),
                "color": str(raw.get("color") or "#111111")[:32],
                "background": str(raw.get("background") or "transparent")[:32],
                "align": raw.get("align") if raw.get("align") in ("left", "center", "right") else "left",
                "bold": bool(raw.get("bold")),
            })
        elif kind == "image":
            src = str(raw.get("src") or "")
            if not src.startswith(f"/pdf-editor-assets/{slot}/"):
                return None
            item.update({"src": src[:500], "fit": "contain" if raw.get("fit") == "contain" else "cover"})
        else:
            item["color"] = str(raw.get("color") or "#ffffff")[:32]
        return item

    def _clean_pages(self, slot: str, raw_pages: dict) -> dict:
        pages = {}
        if not isinstance(raw_pages, dict):
            return pages
        for raw_num, raw_items in raw_pages.items():
            try:
                page_num = int(raw_num)
            except (TypeError, ValueError):
                continue
            if not 1 <= page_num <= 500 or not isinstance(raw_items, list):
                continue
            items = [clean for raw in raw_items[:500]
                     if (clean := self._clean_element(slot, raw))]
            if items:
                pages[str(page_num)] = items
        return pages

    async def changed(self) -> None:
        if not self._on_change:
            return
        result = self._on_change()
        if inspect.isawaitable(result):
            await result

    def save(self, slot: str, body: SaveBody) -> dict:
        slot = self._check_slot(slot)
        current = self.load(slot)
        if int(body.baseRevision) != int(current.get("revision") or 0):
            raise HTTPException(409, detail={
                "message": "документ уже изменён на другом компьютере",
                "current": current,
            })
        now = _utc_now()
        value = {
            "schemaVersion": 1, "slot": slot,
            "revision": int(current.get("revision") or 0) + 1,
            "updatedAt": now.isoformat(timespec="milliseconds"),
            "updatedBy": str(body.updatedBy or "unknown")[:100],
            "pages": self._clean_pages(slot, body.pages),
        }
        if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise HTTPException(413, "документ слишком большой")
        _atomic_json(self._current_path(slot), value)
        history = self.history_dir / slot / f"{_stamp(now)}-r{value['revision']}.json"
        _atomic_json(history, value)
        self._mirror(history, slot, "history")
        return value

    def _mirror(self, source: Path, slot: str, kind: str) -> None:
        if not self.archive_dir:
            return
        try:
            target = self.archive_dir / slot / kind / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        except Exception as exc:
            print(f"[pdf-editor] archive mirror failed: {exc}", flush=True)

    def archive_config(self) -> dict:
        return {
            "path": str(self.archive_dir or ""),
            "effectivePath": str(self.archive_dir or self.history_dir),
            "source": "environment" if self.archive_from_environment else ("config" if self.archive_dir else "local"),
        }

    def set_archive(self, raw_path: str) -> dict:
        if self.archive_from_environment:
            raise HTTPException(409, "путь задан переменной POSTCARDS_EDITOR_ARCHIVE_DIR")
        value = str(raw_path or "").strip().strip('"')
        target = Path(value) if value else None
        if target:
            try:
                target.mkdir(parents=True, exist_ok=True)
                probe = target / ".postcards-write-test"
                probe.write_text("ok", "utf-8")
                probe.unlink()
            except Exception as exc:
                raise HTTPException(400, f"нет доступа к папке архива: {exc}") from exc
        self.archive_dir = target
        _atomic_json(self.config_path, {"archiveDir": value})
        return self.archive_config()

    def save_asset(self, slot: str, data: bytes, filename: str) -> dict:
        slot = self._check_slot(slot)
        if not data:
            raise HTTPException(400, "пустое изображение")
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "изображение больше 25 МБ")
        ext = Path(filename or "").suffix.lower()
        if ext not in IMAGE_EXTS:
            raise HTTPException(400, "поддерживаются PNG, JPG, WEBP и GIF")
        name = f"{_stamp(_utc_now())}-{uuid.uuid4().hex[:10]}{ext}"
        target = self.assets_dir / slot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self._mirror(target, slot, "assets")
        return {"url": f"/pdf-editor-assets/{slot}/{name}", "name": name,
                "size": len(data), "contentType": mimetypes.guess_type(name)[0] or "application/octet-stream"}

    def history(self, slot: str) -> list[dict]:
        slot = self._check_slot(slot)
        result = []
        for path in sorted((self.history_dir / slot).glob("*.json"), reverse=True):
            try:
                doc = json.loads(path.read_text("utf-8"))
                result.append({"revision": int(doc.get("revision") or 0),
                               "updatedAt": doc.get("updatedAt"), "updatedBy": doc.get("updatedBy")})
            except Exception:
                continue
        return result[:200]

    def load_history(self, slot: str, revision: int) -> dict:
        slot = self._check_slot(slot)
        matches = list((self.history_dir / slot).glob(f"*-r{int(revision)}.json"))
        if not matches:
            raise HTTPException(404, "ревизия не найдена")
        return json.loads(matches[-1].read_text("utf-8"))

    def snapshot(self) -> dict:
        result = {}
        for slot in PDF_SLOTS:
            doc = self.load(slot)
            result[slot] = {"revision": int(doc.get("revision") or 0),
                            "updatedAt": doc.get("updatedAt"), "updatedBy": doc.get("updatedBy"),
                            "hasEdits": bool(doc.get("pages"))}
        return result


def create_router(store: PdfEditorStore) -> APIRouter:
    router = APIRouter(prefix="/api/pdf-editor")

    # Статические пути обязаны регистрироваться раньше /{slot}.
    @router.get("/config")
    def get_config():
        return store.archive_config()

    @router.put("/config")
    def set_config(body: ArchiveConfigBody):
        return store.set_archive(body.path)

    @router.get("/{slot}")
    def get_document(slot: str):
        return store.load(slot)

    @router.put("/{slot}")
    async def save_document(slot: str, body: SaveBody):
        result = store.save(slot, body)
        await store.changed()
        return result

    @router.post("/{slot}/assets")
    async def upload_asset(slot: str, request: Request, filename: str = "image.png"):
        return store.save_asset(slot, await request.body(), filename)

    @router.get("/{slot}/history")
    def get_history(slot: str):
        return {"items": store.history(slot),
                "archiveDir": str(store.archive_dir or store.history_dir),
                "archiveSource": store.archive_config()["source"]}

    @router.get("/{slot}/history/{revision}")
    def get_history_document(slot: str, revision: int):
        return store.load_history(slot, revision)

    return router


def mount_static(app, store: PdfEditorStore) -> None:
    app.mount("/pdf-editor-assets", StaticFiles(directory=str(store.assets_dir)),
              name="pdf-editor-assets")
